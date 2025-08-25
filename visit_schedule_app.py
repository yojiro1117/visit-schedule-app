# -*- coding: utf-8 -*-
import streamlit as st
import requests
from datetime import datetime, date, timedelta
import urllib.parse
import math

# =========================
#  ページ設定 & スタイル
# =========================
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

# =========================
#  セッション初期化
# =========================
if "schedule" not in st.session_state:
    st.session_state.schedule = []  # {name, address, stay_min, note}

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

# =========================
#  共通関数
# =========================
def get_api_key():
    try:
        return st.secrets["google_api"]["GOOGLE_API_KEY"]
    except Exception:
        return None

def unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())

def maps_url(origin: str, dest: str, mode: str, depart_dt: datetime, transit_pref: str = "fewer_transfers"):
    # 訪問先名称の直下に出すリンク用（出発時刻も含める）
    params = {
        "api": "1",
        "origin": origin,
        "destination": dest,
        "travelmode": mode,
        "departure_time": str(unix_seconds(depart_dt)),
    }
    if mode == "transit":
        params["transit_routing_preference"] = transit_pref  # fewer_transfers|less_walking
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params, safe=":")  # place_id: を壊さない

# ---- Places/Geocoding の強化：place_id 正規化 ----
def places_find_place_id(text: str):
    """Places API (Find Place) で place_id を取得。"""
    key = get_api_key()
    if not key or not text.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": text,
        "inputtype": "textquery",
        "fields": "place_id",
        "language": "ja",
        "region": "jp",
        "key": key
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        js = r.json()
        cands = js.get("candidates") or []
        if cands and cands[0].get("place_id"):
            return f"place_id:{cands[0]['place_id']}"
    except Exception:
        pass
    return None

def geocode_place_id(text: str):
    """Geocoding API で place_id を取得。"""
    key = get_api_key()
    if not key or not text.strip():
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": text, "language": "ja", "region": "jp", "key": key}
    try:
        r = requests.get(url, params=params, timeout=15)
        js = r.json()
        results = js.get("results") or []
        if results and results[0].get("place_id"):
            return f"place_id:{results[0]['place_id']}"
    except Exception:
        pass
    return None

def normalize_for_api(text: str):
    """
    Directions/Maps 用に place_id へ正規化。
    ① Geocoding → ② Places(FindPlace) → ③ そのまま文字列 の順にフォールバック。
    """
    # すでに place_id 形式ならそのまま
    if text.startswith("place_id:"):
        return text
    pid = geocode_place_id(text)
    if pid:
        return pid
    pid = places_find_place_id(text)
    if pid:
        return pid
    return text  # 最後の手段

def get_directions_duration_seconds(origin: str, dest: str, mode: str, depart_dt: datetime, avoid_tolls: bool, debug: dict | None = None):
    """
    Directions API で所要時間（秒）を取得。
    失敗時は複数のフォールバックを試す。
    debug に API のステータスなどを返す（UI の折りたたみで表示）。
    """
    key = get_api_key()
    if not key:
        if debug is not None:
            debug["note"] = "APIキー未設定"
        return None

    url = "https://maps.googleapis.com/maps/api/directions/json"

    def _call(o, d):
        params = {
            "origin": o,
            "destination": d,
            "mode": mode,
            "departure_time": unix_seconds(depart_dt),
            "language": "ja",
            "region": "jp",
            "key": key,
        }
        if mode == "driving" and avoid_tolls:
            params["avoid"] = "tolls"
        if mode == "transit":
            params["transit_routing_preference"] = "fewer_transfers"
        try:
            r = requests.get(url, params=params, timeout=20)
            js = r.json()
            if debug is not None:
                debug["last_status"] = js.get("status")
                debug["last_error"] = js.get("error_message")
            routes = js.get("routes") or []
            if routes:
                legs = routes[0].get("legs") or []
                if legs:
                    dur = legs[0].get("duration")
                    if dur and "value" in dur:
                        return int(dur["value"])
        except Exception as e:
            if debug is not None:
                debug["exception"] = str(e)
        return None

    # 1) place_id 正規化を使って呼ぶ
    secs = _call(origin, dest)
    if secs is not None:
        return secs

    # 2) place_id で失敗することが稀にあるため “元の文字列” 同士も試す
    o_raw = origin.split(":", 1)[1] if origin.startswith("place_id:") else origin
    d_raw = dest.split(":", 1)[1] if dest.startswith("place_id:") else dest
    secs = _call(o_raw, d_raw)
    if secs is not None:
        return secs

    # 3) 片側だけ place_id → 文字列のミックスも試す
    secs = _call(origin, d_raw)
    if secs is not None:
        return secs
    secs = _call(o_raw, dest)
    if secs is not None:
        return secs

    return None

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
        name = item.get("name") or item.get("訪問先名称") or item.get("訪問先") or ""
        address = item.get("address") or item.get("住所") or ""
        stay_min = safe_int(item.get("stay_min", item.get("滞在時間", item.get("stay_time", 0))), 0)
        note = item.get("note", item.get("備考", ""))

        dest_label = address if address.strip() else name
        dest_api = normalize_for_api(dest_label)

        dbg = {}
        secs = get_directions_duration_seconds(current_origin_api, dest_api, mode, cursor_depart, avoid_tolls, debug=dbg)
        duration_text = "取得失敗"
        if secs is None:
            secs = 0
        else:
            mins = math.ceil(secs / 60)
            duration_text = f"{mins} 分" if mins < 60 else f"{mins//60} 時間 {mins%60} 分" if mins % 60 else f"{mins//60} 時間"

        arrive_dt = cursor_depart + timedelta(seconds=secs)
        leave_dt  = arrive_dt + timedelta(minutes=stay_min)

        url = maps_url(current_origin_api, dest_api, mode, cursor_depart)

        timeline.append({
            "name": name,
            "address": address,
            "stay_min": stay_min,
            "note": note,
            "origin_label": current_origin_label,
            "depart_at": cursor_depart,
            "arrive_at": arrive_dt,
            "leave_at": leave_dt,
            "duration_text": duration_text,
            "map_url": url,
            "debug": dbg if show_debug else None
        })

        cursor_depart = leave_dt
        current_origin_label = dest_label
        current_origin_api = dest_api

    return timeline

# =========================
#  レイアウト
# =========================
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
    mode = {"車(Driving)": "driving", "徒歩(Walking)": "walking", "公共交通機関(Transit)": "transit"}[mode_label]
    avoid_tolls = st.checkbox("有料道路を避ける") if mode == "driving" else False

    # 出発日時（左右並び）
    st.subheader("出発日時")
    col_d, col_t = st.columns(2)
    with col_d:
        st.session_state.base_depart_date = st.date_input("出発日 (Departure Date)", value=st.session_state.base_depart_date)
    with col_t:
        times = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in range(0, 60, 5)]
        if st.session_state.base_depart_time_str not in times:
            st.session_state.base_depart_time_str = _nearest5_str_now()
        st.session_state.base_depart_time_str = st.selectbox(
            "出発時刻 (Departure Time)", options=times, index=times.index(st.session_state.base_depart_time_str)
        )

    st.divider()

    # 訪問先の追加
    st.subheader("訪問先の追加")
    with st.form("add_destination"):
        name = st.text_input("訪問先名称 (Name of destination)")
        address = st.text_input("住所 (address)", placeholder="例：福岡市中央区薬院〜（名称だけでもOK）")
        stay_min = st.number_input("滞在時間（分・minutes）", min_value=0, step=5, value=20)
        note = st.text_area("備考（任意・Remarks）", height=80)
        submitted = st.form_submit_button("追加する")
        if submitted:
            if not name.strip():
                st.warning("⚠️ 名称が必要です")
            else:
                st.session_state.schedule.append({
                    "name": name.strip(),
                    "address": address.strip(),
                    "stay_min": int(stay_min),
                    "note": note.strip()
                })
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
        current_origin_text = (
            st.session_state.origin_new.strip() if st.session_state.origin_select == "（新規入力…）"
            else st.session_state.origin_select
        )
        show_debug = st.checkbox("デバッグ情報を表示", value=False)
        tl = recalc_timeline(
            origin_text=current_origin_text or "",
            base_depart_dt=base_dt,
            mode=mode,
            avoid_tolls=avoid_tolls,
            show_debug=show_debug
        )

        for idx, row in enumerate(tl):
            with st.container(border=True):
                st.markdown(f"**{idx+1}. {row['name']}**")
                # ★ 訪問先名称の直下にマップリンク（出発時刻つき）
                st.markdown(f"[🌐 Googleマップを開く]({row['map_url']})")

                st.write(f"📍 住所：{row['address'] or '（名称検索）'}")
                st.write(
                    f"🚶 出発：{row['depart_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"→ 🚌 到着：{row['arrive_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"（所要：{row['duration_text']}）"
                )
                st.write(f"⏱ 滞在：{row['stay_min']} 分 → 次出発：{row['leave_at'].strftime('%Y-%m-%d %H:%M')}")
                if row["note"]:
                    st.write(f"📝 備考：{row['note']}")

                # デバッグ情報（APIレスポンスのステータスなど）
                if show_debug and row.get("debug"):
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

# サイドバー（任意）
with st.sidebar:
    st.header("📎 使い方")
    st.markdown("- 出発地はプルダウンで選択、または「新規入力…」を選んで保存します。保存するとプルダウンに直ちに反映されます。")
    st.markdown("- 出発日と出発時刻は左右に並べて選択します（初期値は現在時刻の5分切り上げ）。")
    st.markdown("- 訪問先は名称だけでも追加可能（地図・経路は名称検索または place_id 正規化で算出）。")
    st.markdown("- 各訪問先のカード直下に **Googleマップリンク** を置いています（出発時刻が反映）。")
    st.markdown("- 取得に失敗する場合は「デバッグ情報を表示」を ON にして、APIの status/error を確認してください。")
