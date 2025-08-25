# -*- coding: utf-8 -*-
import streamlit as st
import requests
from datetime import datetime, date, timedelta
import urllib.parse
import math

# =========================================
# ページ設定 / スタイル
# =========================================
st.set_page_config(page_title="訪問スケジュール作成アプリ", layout="wide")
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
  background-image: url("https://upload.wikimedia.org/wikipedia/commons/8/80/World_map_-_low_resolution_gray_blue.png");
  background-size: cover;
  background-position: center;
}
[data-testid="stSidebar"] { min-width: 430px; max-width: 430px; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h1>🗓️ 訪問スケジュール作成アプリ</h1>", unsafe_allow_html=True)
st.caption("API-Enabled + Debug Mode")

# =========================================
# セッション初期化
# =========================================
if "schedule" not in st.session_state:
    # item: {name, address, stay_min, note, fixed_duration_sec(optional)}
    st.session_state.schedule = []

if "saved_origins" not in st.session_state:
    st.session_state.saved_origins = []

if "origin_select" not in st.session_state:
    st.session_state.origin_select = "（新規入力…）"

if "origin_new" not in st.session_state:
    st.session_state.origin_new = ""

if "base_depart_date" not in st.session_state:
    st.session_state.base_depart_date = date.today()

def _nearest5_str_now():
    now = datetime.now()
    add = (5 - (now.minute % 5)) % 5
    if add:
        now += timedelta(minutes=add)
    if now.minute == 60:
        now = now.replace(minute=0) + timedelta(hours=1)
    return f"{now.hour:02d}:{now.minute:02d}"

if "base_depart_time_str" not in st.session_state:
    st.session_state.base_depart_time_str = _nearest5_str_now()

# =========================================
# 共通 util
# =========================================
def get_api_key():
    try:
        return st.secrets["google_api"]["GOOGLE_API_KEY"]
    except Exception:
        return None

def unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())

def maps_url(origin: str, dest: str, mode: str, depart_dt: datetime, transit_pref: str = "fewer_transfers"):
    params = {
        "api": "1",
        "origin": origin,
        "destination": dest,
        "travelmode": mode,
        "departure_time": str(unix_seconds(depart_dt)),
    }
    if mode == "transit":
        params["transit_routing_preference"] = transit_pref
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params, safe=":")  # place_id: を壊さない

# ---- place_id 正規化（強化） ----
def places_find_place_id(text: str):
    key = get_api_key()
    if not key or not text.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": text, "inputtype": "textquery", "fields": "place_id",
        "language": "ja", "region": "jp", "key": key
    }
    try:
        js = requests.get(url, params=params, timeout=15).json()
        c = js.get("candidates") or []
        if c and c[0].get("place_id"):
            return f"place_id:{c[0]['place_id']}"
    except Exception:
        pass
    return None

def geocode_place_id(text: str):
    key = get_api_key()
    if not key or not text.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": text, "language": "ja", "region": "jp", "key": key}
    try:
        js = requests.get(url, params=params, timeout=15).json()
        res = js.get("results") or []
        if res and res[0].get("place_id"):
            return f"place_id:{res[0]['place_id']}"
    except Exception:
        pass
    return None

def normalize_for_api(text: str):
    if text.startswith("place_id:"):
        return text
    pid = geocode_place_id(text)
    if pid:
        return pid
    pid = places_find_place_id(text)
    if pid:
        return pid
    return text  # 最後のフォールバック

# ---- Directions / Distance Matrix のハイブリッド ----
def _directions_call(origin, dest, mode, depart_dt, avoid_tolls, key):
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin, "destination": dest, "mode": mode,
        "departure_time": unix_seconds(depart_dt), "language": "ja",
        "region": "jp", "key": key
    }
    if mode == "driving" and avoid_tolls:
        params["avoid"] = "tolls"
    if mode == "transit":
        params["transit_routing_preference"] = "fewer_transfers"
    r = requests.get(url, params=params, timeout=20)
    return r.json()

def get_duration_seconds(origin: str, dest: str, mode: str, depart_dt: datetime, avoid_tolls: bool, debug: dict | None = None):
    """
    Directions → 文字列/ミックス → Distance Matrix の順にフォールバック。
    """
    key = get_api_key()
    if not key:
        if debug is not None: debug["note"] = "APIキー未設定"
        return None

    def parse_dir(js):
        routes = js.get("routes") or []
        if routes:
            legs = routes[0].get("legs") or []
            if legs and legs[0].get("duration") and "value" in legs[0]["duration"]:
                return int(legs[0]["duration"]["value"])
        return None

    # 1) place_id 同士
    try:
        js = _directions_call(origin, dest, mode, depart_dt, avoid_tolls, key)
        if debug is not None:
            debug["dir_status"] = js.get("status"); debug["dir_error"] = js.get("error_message")
        v = parse_dir(js)
        if v is not None: return v
    except Exception as e:
        if debug is not None: debug["dir_exception"] = str(e)

    # 2) 生文字列同士
    try:
        o_raw = origin.split(":",1)[1] if origin.startswith("place_id:") else origin
        d_raw = dest.split(":",1)[1] if dest.startswith("place_id:") else dest
        js = _directions_call(o_raw, d_raw, mode, depart_dt, avoid_tolls, key)
        if debug is not None:
            debug["dir_status_raw"] = js.get("status"); debug["dir_error_raw"] = js.get("error_message")
        v = parse_dir(js);  # ここでも alternatives は使わず最短
        if v is not None: return v
    except Exception as e:
        if debug is not None: debug["dir_exception_raw"] = str(e)

    # 3) Distance Matrix フォールバック
    try:
        url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        params = {
            "origins": origin, "destinations": dest, "mode": mode,
            "departure_time": unix_seconds(depart_dt), "language": "ja",
            "region": "jp", "key": key
        }
        if mode == "driving" and avoid_tolls:
            params["avoid"] = "tolls"
        js = requests.get(url, params=params, timeout=20).json()
        if debug is not None:
            debug["dm_status"] = js.get("status")
        rows = js.get("rows") or []
        if rows and rows[0].get("elements"):
            elem = rows[0]["elements"][0]
            dur = elem.get("duration") or elem.get("duration_in_traffic")
            if dur and "value" in dur:
                return int(dur["value"])
    except Exception as e:
        if debug is not None: debug["dm_exception"] = str(e)

    return None

# ---- Transit 複数候補 ----
def get_transit_candidates(origin_text: str, dest_text: str, depart_dt: datetime, max_routes: int = 5):
    """
    Directions API (mode=transit, alternatives=true) で候補取得。
    返却: [{summary_text, duration_sec, depart_text, arrive_text, transfers_text}]
    """
    key = get_api_key()
    if not key:
        return []

    o = normalize_for_api(origin_text)
    d = normalize_for_api(dest_text)

    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": o, "destination": d, "mode": "transit",
        "alternatives": "true",
        "departure_time": unix_seconds(depart_dt),
        "language": "ja", "region": "jp",
        "transit_routing_preference": "fewer_transfers",
        "key": key,
    }
    try:
        js = requests.get(url, params=params, timeout=20).json()
        routes = js.get("routes") or []
        cands = []
        for r in routes[:max_routes]:
            legs = r.get("legs") or []
            if not legs: continue
            leg = legs[0]
            dur = leg.get("duration", {}).get("value")
            dep_txt = leg.get("departure_time", {}).get("text")
            arr_txt = leg.get("arrival_time", {}).get("text")

            # 乗換概要（簡易）
            transfers = 0
            details = []
            for step in (leg.get("steps") or []):
                td = step.get("transit_details")
                if td:
                    line = td.get("line", {})
                    vehicle = (line.get("vehicle") or {}).get("type")
                    short = (line.get("short_name") or line.get("name") or "")
                    details.append(f"{vehicle or ''}{short or ''}".strip())
                    transfers += 1
            transfers_text = f"乗換 {max(0, transfers-1)} 回" if transfers else "直通"

            mins = math.ceil((dur or 0)/60)
            summary_text = f"{dep_txt} → {arr_txt}（{mins}分, {transfers_text}）"
            cands.append({
                "summary_text": summary_text,
                "duration_sec": int(dur) if dur else None,
                "depart_text": dep_txt, "arrive_text": arr_txt,
                "transfers_text": transfers_text
            })
        return cands
    except Exception:
        return []

def safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def recalc_timeline(origin_text: str, base_depart_dt: datetime, mode: str, avoid_tolls: bool, show_debug: bool):
    current_origin_label = origin_text or ""
    current_origin_api = normalize_for_api(current_origin_label)

    timeline = []
    cursor_depart = base_depart_dt

    for item in st.session_state.schedule:
        name = item.get("name") or ""
        address = item.get("address") or ""
        stay_min = safe_int(item.get("stay_min", item.get("stay_time", 0)), 0)
        note = item.get("note", "")

        dest_label = address if address.strip() else name
        dest_api = normalize_for_api(dest_label)

        dbg = {}
        # ユーザが候補を採用して固定した場合はそれを優先
        secs = item.get("fixed_duration_sec")
        if secs is None:
            secs = get_duration_seconds(current_origin_api, dest_api, mode, cursor_depart, avoid_tolls, debug=dbg)

        if secs is None:
            duration_text = "取得失敗"
            secs = 0
        else:
            mins = math.ceil(secs/60)
            duration_text = f"{mins} 分" if mins < 60 else f"{mins//60} 時間 {mins%60} 分" if mins%60 else f"{mins//60} 時間"

        arrive_dt = cursor_depart + timedelta(seconds=secs)
        leave_dt  = arrive_dt + timedelta(minutes=stay_min)

        url = maps_url(current_origin_api, dest_api, mode, cursor_depart)

        timeline.append({
            "name": name, "address": address, "stay_min": stay_min, "note": note,
            "depart_at": cursor_depart, "arrive_at": arrive_dt, "leave_at": leave_dt,
            "duration_text": duration_text, "map_url": url,
            "debug": dbg if show_debug else None
        })

        cursor_depart = leave_dt
        current_origin_label = dest_label
        current_origin_api = dest_api

    return timeline

# =========================================
# UI
# =========================================
left, right = st.columns([6, 6])

with left:
    # 出発地（1段）
    st.subheader("出発地")
    row1 = st.columns([3, 3, 1.2])
    with row1[0]:
        origin_options = ["（新規入力…）"] + st.session_state.saved_origins
        st.session_state.origin_select = st.selectbox(
            "登録済み／新規入力の選択", options=origin_options,
            index=origin_options.index(st.session_state.origin_select) if st.session_state.origin_select in origin_options else 0
        )
    with row1[1]:
        if st.session_state.origin_select == "（新規入力…）":
            st.session_state.origin_new = st.text_input("出発地を入力", value=st.session_state.origin_new, placeholder="例：職場 / 福岡市中央区〜")
        else:
            st.text_input("出発地（選択中）", value=st.session_state.origin_select, disabled=True)
    with row1[2]:
        if st.button("保存", use_container_width=True):
            if st.session_state.origin_select == "（新規入力…）":
                v = (st.session_state.origin_new or "").strip()
                if v:
                    if v not in st.session_state.saved_origins:
                        st.session_state.saved_origins.insert(0, v)
                        st.session_state.saved_origins = st.session_state.saved_origins[:10]
                    st.session_state.origin_select = v
                    st.session_state.origin_new = ""
                    st.success("出発地を保存しました")
            else:
                st.info("選択中の出発地を使用します")

    # 移動手段
    st.subheader("移動手段")
    mode_label = st.radio("選択", ["車(Driving)", "徒歩(Walking)", "公共交通機関(Transit)"], horizontal=True)
    mode = {"車(Driving)":"driving", "徒歩(Walking)":"walking", "公共交通機関(Transit)":"transit"}[mode_label]
    avoid_tolls = st.checkbox("有料道路を避ける") if mode == "driving" else False

    # 出発日時（左右）
    st.subheader("出発日時")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.base_depart_date = st.date_input("出発日 (Departure Date)", value=st.session_state.base_depart_date)
    with c2:
        times = [f"{h:02d}:{m:02d}" for h in range(0,24) for m in range(0,60,5)]
        if st.session_state.base_depart_time_str not in times:
            st.session_state.base_depart_time_str = _nearest5_str_now()
        st.session_state.base_depart_time_str = st.selectbox("出発時刻 (Departure Time)", options=times,
                                                             index=times.index(st.session_state.base_depart_time_str))

    st.divider()

    # 訪問先の追加
    st.subheader("訪問先の追加")
    with st.form("add_destination"):
        name = st.text_input("訪問先名称 (Name of destination)")
        address = st.text_input("住所 (address)", placeholder="例：福岡市中央区薬院〜（名称だけでもOK）")
        stay_min = st.number_input("滞在時間（分・minutes）", min_value=0, step=5, value=20)
        note = st.text_area("備考（任意・Remarks）", height=80)

        # ★ Transit 候補取得（表示はフォーム内に）
        transit_pick = None
        cand_holder = st.empty()
        if mode == "transit":
            if st.form_submit_button("公共交通の候補を取得", use_container_width=True):
                origin_text = (st.session_state.origin_new.strip()
                               if st.session_state.origin_select == "（新規入力…）"
                               else st.session_state.origin_select)
                base_dt = datetime.combine(
                    st.session_state.base_depart_date,
                    datetime.strptime(st.session_state.base_depart_time_str, "%H:%M").time()
                )
                cands = get_transit_candidates(origin_text, address or name, base_dt, max_routes=5)
                if not cands:
                    cand_holder.warning("候補が取得できませんでした（APIデータ未対応 or 入力不備の可能性）。")
                else:
                    with cand_holder.container():
                        st.info("候補から選択してください（採用するとこの所要時間を固定します）。")
                        labels = [c["summary_text"] for c in cands]
                        idx = st.radio("候補", list(range(len(cands))), format_func=lambda i: labels[i], index=0, key="transit_pick_idx")
                        st.session_state["__last_transit_pick__"] = cands[idx]

        ok = st.form_submit_button("追加する", use_container_width=True)
        if ok:
            if not name.strip():
                st.warning("⚠️ 名称が必要です")
            else:
                item = {
                    "name": name.strip(),
                    "address": address.strip(),
                    "stay_min": int(stay_min),
                    "note": note.strip()
                }
                # 候補を採用していた場合は固定所要時間を格納
                if mode == "transit":
                    picked = st.session_state.get("__last_transit_pick__")
                    if picked and picked.get("duration_sec"):
                        item["fixed_duration_sec"] = int(picked["duration_sec"])
                st.session_state.schedule.append(item)
                # 使い回し抑止
                st.session_state["__last_transit_pick__"] = None
                st.success("✅ 訪問先を追加しました")

with right:
    st.subheader("🗒️ スケジュール一覧（到着時刻を自動計算）")
    if not st.session_state.schedule:
        st.info("訪問先はまだ登録されていません")
    else:
        base_dt = datetime.combine(
            st.session_state.base_depart_date,
            datetime.strptime(st.session_state.base_depart_time_str, "%H:%M").time()
        )
        origin_text = (st.session_state.origin_new.strip()
                       if st.session_state.origin_select == "（新規入力…）"
                       else st.session_state.origin_select)

        show_debug = st.checkbox("デバッグ情報を表示", value=False)
        tl = recalc_timeline(origin_text, base_dt, mode, avoid_tolls, show_debug)

        for idx, row in enumerate(tl):
            with st.container(border=True):
                st.markdown(f"**{idx+1}. {row['name']}**")
                # 訪問先名の直下に出発時刻付きマップリンク
                st.markdown(f"[🌐 Googleマップを開く]({row['map_url']})")
                st.write(f"📍 住所：{row['address'] or '（名称検索）'}")
                st.write(
                    f"🚶 出発：{row['depart_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"→ 🚌 到着：{row['arrive_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"（所要：{row['duration_text']}）"
                )
                st.write(f"⏱ 滞在：{row['stay_min']} 分 → 次出発：{row['leave_at'].strftime('%Y-%m-%d %H:%M')}")
                if row.get("debug") and show_debug:
                    with st.expander("デバッグ詳細"):
                        st.json(row["debug"])

                cols = st.columns([1, 3])
                with cols[0]:
                    if st.button("削除", key=f"del_{idx}", type="secondary"):
                        st.session_state.schedule.pop(idx)
                        st.experimental_rerun()

        if tl:
            st.divider()
            st.success(f"🟢 すべての訪問が終了する時刻：**{tl[-1]['leave_at'].strftime('%Y-%m-%d %H:%M')}**")

# サイドバー
with st.sidebar:
    st.header("📎 使い方")
    st.markdown("- 出発地はプルダウンまたは「新規入力…」から保存（保存すると即反映）。")
    st.markdown("- 出発日・出発時刻は左右に並列（初期時刻は現在時刻の5分切り上げ）。")
    st.markdown("- **公共交通機関**を選んだ状態で「訪問先の追加」→ **［公共交通の候補を取得］** → 候補を選んで **［追加する］**。")
    st.markdown("- 追加後は各行の **Googleマップを開く** で同じ出発時刻の案内を表示。")

