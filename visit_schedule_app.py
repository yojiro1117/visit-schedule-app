# -*- coding: utf-8 -*-
import streamlit as st
import requests
from datetime import datetime, date, time, timedelta
import urllib.parse
import math

# ------------------------------------------------------------
# ページ設定 & スタイル（背景地図 / サイドバー幅拡大 / 余白調整）
# ------------------------------------------------------------
st.set_page_config(page_title="訪問スケジュール作成アプリ", layout="wide")
st.markdown("""
<style>
/* 背景に落ち着いた世界地図 */
[data-testid="stAppViewContainer"] {
    background-image: url("https://upload.wikimedia.org/wikipedia/commons/8/80/World_map_-_low_resolution_gray_blue.png");
    background-size: cover;
    background-position: center;
}
/* サイドバー幅を拡大（おおよそ2倍相当） */
[data-testid="stSidebar"] {
    min-width: 430px;
    max-width: 430px;
}
/* サイドバー内コンテンツの読みやすさ向上 */
[data-testid="stSidebar"] .block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# タイトル
# ------------------------------------------------------------
st.markdown("<h1>🗓️ 訪問スケジュール作成アプリ</h1>", unsafe_allow_html=True)
st.caption("API-Enabled + Debug Mode")

# ------------------------------------------------------------
# セッション状態の初期化
# ------------------------------------------------------------
if "schedule" not in st.session_state:
    # 各要素: {name, address, stay_min, note}
    st.session_state.schedule = []
if "saved_origins" not in st.session_state:
    st.session_state.saved_origins = []
if "base_depart_date" not in st.session_state:
    st.session_state.base_depart_date = date.today()
if "base_depart_time_str" not in st.session_state:
    # "09:00" のような文字列で管理（プルダウン）
    st.session_state.base_depart_time_str = "09:00"
if "selected_origin" not in st.session_state:
    st.session_state.selected_origin = ""

# ------------------------------------------------------------
# 共通関数
# ------------------------------------------------------------
def get_api_key():
    try:
        return st.secrets["google_api"]["GOOGLE_API_KEY"]
    except Exception:
        return None  # 未設定でも動くように

def to_datetime(d: date, time_str: str) -> datetime:
    hh, mm = [int(x) for x in time_str.split(":")]
    return datetime(d.year, d.month, d.day, hh, mm)

def unix_seconds(dt: datetime) -> int:
    return int(dt.timestamp())

def maps_url(origin: str, dest: str, mode: str, depart_dt: datetime):
    """
    GoogleマップURLを生成。出発時刻(departure_time)をUNIX秒で付与。
    api=1 の URL 仕様は正式には departure_time をドキュメント化していませんが、
    実地で反映されるケースが多いため付与します（将来仕様変更の可能性あり）。
    """
    params = {
        "api": "1",
        "origin": origin,
        "destination": dest,
        "travelmode": mode,  # "driving" | "walking" | "transit"
        "departure_time": str(unix_seconds(depart_dt)),
    }
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params, safe=":")

def get_directions_duration_seconds(origin: str, dest: str, mode: str, depart_dt: datetime, avoid_tolls: bool):
    """
    Google Directions API でルート所要時間（秒）を取得。
    """
    key = get_api_key()
    if not key:
        return None  # APIキーなし
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": dest,
        "mode": mode,  # "driving" | "walking" | "transit"
        "departure_time": unix_seconds(depart_dt),
        "language": "ja",
        "key": key,
    }
    if mode == "driving" and avoid_tolls:
        params["avoid"] = "tolls"

    try:
        res = requests.get(url, params=params, timeout=20)
        data = res.json()
        # デバッグしたい時:
        # st.write("API:", data)
        legs = data["routes"][0]["legs"][0]
        return int(legs["duration"]["value"])  # 秒
    except Exception:
        return None

def recalc_timeline(origin: str, base_depart_dt: datetime, mode: str, avoid_tolls: bool):
    """
    先頭から順に、出発 -> 到着 -> 滞在 -> 次の出発 を累積計算し、
    schedule各要素に到着時刻・出発時刻・マップURL・所要時間を付与して返す。
    """
    timeline = []
    cursor_depart = base_depart_dt
    current_origin = origin

    for item in st.session_state.schedule:
        name = item["name"]
        address = item["address"]
        stay_min = int(item["stay_min"])

        dest_for_api = address if address.strip() else name  # 住所が空でも名称で検索
        # 所要時間（秒）
        secs = get_directions_duration_seconds(current_origin, dest_for_api, mode, cursor_depart, avoid_tolls)
        duration_text = "取得失敗"
        if secs is None:
            secs = 0
        else:
            # 「xx分」などの日本語表現
            mins = math.ceil(secs / 60)
            if mins < 60:
                duration_text = f"{mins} 分"
            else:
                h = mins // 60
                m = mins % 60
                duration_text = f"{h} 時間 {m} 分" if m else f"{h} 時間"

        arrive_dt = cursor_depart + timedelta(seconds=secs)
        leave_dt  = arrive_dt + timedelta(minutes=stay_min)

        # GoogleマップURL（この訪問の出発時刻cursor_departを反映）
        url = maps_url(current_origin, dest_for_api, mode, cursor_depart)

        timeline.append({
            "name": name,
            "address": address,
            "stay_min": stay_min,
            "note": item["note"],
            "depart_at": cursor_depart,
            "arrive_at": arrive_dt,
            "leave_at": leave_dt,
            "duration_text": duration_text,
            "map_url": url,
        })

        # 次の訪問に向けてカーソルと現在地を更新
        cursor_depart = leave_dt
        current_origin = dest_for_api

    return timeline

# ------------------------------------------------------------
# 左：メイン入力、右：スケジュール表示（幅広）
# ------------------------------------------------------------
left, right = st.columns([6, 6])  # サイドバー拡大につきメインも広め

with left:
    # 1) 出発地（登録＋選択）
    st.subheader("出発地")
    col_o1, col_o2 = st.columns([4, 1])
    with col_o1:
        origin_input = st.text_input("出発地（住所）", value=st.session_state.selected_origin or "")
    with col_o2:
        if st.button("出発地登録", use_container_width=True):
            if origin_input and (origin_input not in st.session_state.saved_origins):
                st.session_state.saved_origins.insert(0, origin_input)
                st.session_state.saved_origins = st.session_state.saved_origins[:10]  # 最大10件
                st.success("出発地を登録しました")

    if st.session_state.saved_origins:
        st.session_state.selected_origin = st.selectbox(
            "登録済み出発地", 
            options=["（選択してください）"] + st.session_state.saved_origins,
            index=0 if not st.session_state.selected_origin else
                  (st.session_state.saved_origins.index(st.session_state.selected_origin) + 1),
        )
        if st.session_state.selected_origin == "（選択してください）":
            st.session_state.selected_origin = origin_input
    else:
        st.session_state.selected_origin = origin_input

    # 2) 移動手段＋（車の時のみ有料道路回避）
    st.subheader("移動手段")
    mode_label = st.radio("選択", ["車(Driving)", "徒歩(Walking)", "公共交通機関(Transit)"], horizontal=True)
    mode_map = {"車(Driving)": "driving", "徒歩(Walking)": "walking", "公共交通機関(Transit)": "transit"}
    mode = mode_map[mode_label]
    avoid_tolls = False
    if mode == "driving":
        avoid_tolls = st.checkbox("有料道路を避ける")

    # 3) 出発日時（プルダウン：5分刻み）
    st.subheader("出発日時")
    st.session_state.base_depart_date = st.date_input("出発日 (Departure Date)", value=st.session_state.base_depart_date)

    # 5分刻みの時刻リスト
    times = [f"{h:02d}:{m:02d}" for h in range(0, 24) for m in range(0, 60, 5)]
    # 選択肢にない場合は近い5分へ
    if st.session_state.base_depart_time_str not in times:
        st.session_state.base_depart_time_str = "09:00"
    st.session_state.base_depart_time_str = st.selectbox(
        "出発時刻 (Departure Time)", options=times, index=times.index(st.session_state.base_depart_time_str)
    )

    # 4) 訪問先の追加フォーム
    st.subheader("訪問先の追加")
    with st.form("add_destination"):
        name = st.text_input("訪問先名称 (Name of destination)")
        address = st.text_input("住所 (address)", placeholder="例：福岡市中央区薬院〜（名称だけでもOK）")
        stay_min = st.number_input("滞在時間（分・minutes）", min_value=0, step=5, value=20)
        note = st.text_area("備考（任意・Remarks）", height=80)
        submitted = st.form_submit_button("追加する")
        if submitted:
            if not name:
                st.warning("⚠️ 名称が必要です")
            else:
                st.session_state.schedule.append({
                    "name": name.strip(),
                    "address": address.strip(),
                    "stay_min": int(stay_min),
                    "note": note.strip()
                })
                st.success("✅ 訪問先を追加しました")

    # 5) スケジュールの再計算ボタン（出発地や時刻・交通手段を変えた場合に押下）
    st.button("スケジュールを再計算", type="secondary")

with right:
    st.subheader("📋 スケジュール一覧（到着時刻を自動計算）")
    if not st.session_state.schedule:
        st.info("訪問先はまだ登録されていません")
    else:
        # 入力済みの全体タイムラインを計算して表示
        base_depart_dt = to_datetime(st.session_state.base_depart_date, st.session_state.base_depart_time_str)
        origin = st.session_state.selected_origin or ""
        tl = recalc_timeline(origin=origin, base_depart_dt=base_depart_dt, mode=mode, avoid_tolls=avoid_tolls)

        for idx, row in enumerate(tl):
            with st.container(border=True):
                st.markdown(f"**{idx+1}. {row['name']}**")
                st.write(f"📍 住所：{row['address'] or '（名称検索）'}")
                st.write(
                    f"🚶 出発：{row['depart_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"→ 🚌 到着：{row['arrive_at'].strftime('%Y-%m-%d %H:%M')} "
                    f"（所要：{row['duration_text']}）"
                )
                st.write(f"⏱ 滞在：{row['stay_min']} 分 → 次出発：{row['leave_at'].strftime('%Y-%m-%d %H:%M')}")
                if row["note"]:
                    st.write(f"📝 備考：{row['note']}")
                st.markdown(f"[🌐 Googleマップを開く]({row['map_url']})")

                # 個別削除ボタン
                cols = st.columns([1, 3])
                with cols[0]:
                    if st.button("削除", key=f"del_{idx}", type="secondary"):
                        # schedule から idx を削除
                        st.session_state.schedule.pop(idx)
                        st.experimental_rerun()

        # まとめ: 最終到着・終了時刻を表示
        if tl:
            final_leave = tl[-1]["leave_at"]
            st.markdown("---")
            st.success(f"🟢 すべての訪問が終了する時刻：**{final_leave.strftime('%Y-%m-%d %H:%M')}**")

# ------------------------------------------------------------
# 使い方メモ（必要なら）
# ------------------------------------------------------------
with st.sidebar:
    st.header("📎 使い方")
    st.markdown("- 出発地を入力して「出発地登録」で保存、またはドロップダウンから再利用できます。")
    st.markdown("- 出発日・出発時刻・移動手段を選んでください。")
    st.markdown("- 訪問先は「名称だけ」でも追加できます（地図・経路は名称検索）。")
    st.markdown("- 右側に到着時刻・滞在・次出発時刻が自動計算されます。")
    st.markdown("- 各行の「削除」でその訪問先のみ削除できます。")
