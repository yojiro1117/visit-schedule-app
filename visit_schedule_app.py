import streamlit as st
import requests
from datetime import datetime, time

st.set_page_config(page_title="訪問スケジュール作成アプリ", layout="centered")

st.markdown("<h1>🗓️ 訪問スケジュール作成アプリ</h1>", unsafe_allow_html=True)
st.caption("API-Enabled + Debug Mode")

if "schedule" not in st.session_state:
    st.session_state.schedule = []
if "saved_origins" not in st.session_state:
    st.session_state.saved_origins = []

col_o1, col_o2 = st.columns([4, 1])
with col_o1:
    origin = st.text_input("出発地（住所）", placeholder="例：福岡市中央区天神")
with col_o2:
    if st.button("出発地登録"):
        if origin and origin not in st.session_state.saved_origins:
            st.session_state.saved_origins.append(origin)

if st.session_state.saved_origins:
    st.selectbox("登録済み出発地", st.session_state.saved_origins)

st.radio("移動手段", ["車(Driving)", "徒歩(Walking)", "公共交通機関(Transit)"], key="mode", horizontal=True)
if st.session_state.mode == "車(Driving)":
    avoid_tolls = st.checkbox("有料道路を避ける")

date = st.date_input("出発日 (Departure Date)", datetime.today())
time_depart = st.time_input("出発時刻 (Departure Time)", time(9, 0))

st.subheader("訪問先の追加")

with st.form("visit_form"):
    name = st.text_input("訪問先名称 (Name of destination)", placeholder="例：薬院駅")
    address = st.text_input("住所 (address)", placeholder="例：福岡市南筑区〜")
    stay_time = st.number_input("滞在時間（分・minutes）", min_value=0, max_value=600, step=10)
    note = st.text_area("備考（任意・Remarks）", height=50)
    submitted = st.form_submit_button("追加する")

def get_travel_time(origin, destination, mode="driving", avoid_tolls=False):
    API_KEY = st.secrets["google_api"]["GOOGLE_API_KEY"]
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "key": API_KEY,
        "mode": mode,
        "language": "ja"
    }
    if mode == "driving" and avoid_tolls:
        params["avoid"] = "tolls"
    res = requests.get(url, params=params)
    data = res.json()
    try:
        return data["routes"][0]["legs"][0]["duration"]["text"]
    except:
        return "取得失敗"

if submitted:
    if origin and name and (address or name):
        mode = {"車(Driving)": "driving", "徒歩(Walking)": "walking", "公共交通機関(Transit)": "transit"}[st.session_state.mode]
        duration = get_travel_time(origin, address or name, mode, avoid_tolls if "avoid_tolls" in locals() else False)
        google_map_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={address or name}&travelmode={mode}"
        st.session_state.schedule.append({
            "訪問先": name,
            "住所": address,
            "出発日時": f"{date} {time_depart.strftime('%H:%M')}",
            "所要時間": duration,
            "滞在時間": f"{stay_time}分",
            "備考": note,
            "地図リンク": google_map_url
        })
        st.success("✅ 訪問先を追加しました")
    else:
        st.warning("⚠️ 入力が不足しています（出発地・名称・住所すべてが必要です）")

if st.session_state.schedule:
    st.subheader("📋 スケジュール一覧")
    for i, row in enumerate(st.session_state.schedule, 1):
        st.markdown(f"### {i}. {row['訪問先']}")
        st.write(f"📍 住所：{row['住所']}")
        st.write(f"🕓 出発日時：{row['出発日時']}")
        st.write(f"🚗 所要時間：{row['所要時間']}")
        st.write(f"⏱ 滞在時間：{row['滞在時間']}")
        if row["備考"]:
            st.write(f"📝 備考：{row['備考']}")
        st.markdown(f"[🗺️ Googleマップで表示]({row['地図リンク']})")
        st.markdown("---")

st.markdown("""
<style>
    body {
        background-image: url("https://upload.wikimedia.org/wikipedia/commons/7/7f/Mercator_projection_SW.jpg");
        background-size: cover;
        background-attachment: fixed;
        background-position: center;
    }
    .stApp {
        background-color: rgba(255,255,255,0.85);
        padding: 2rem;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)
