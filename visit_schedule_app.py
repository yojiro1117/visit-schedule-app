from datetime import datetime
import streamlit as st
import requests

st.set_page_config(
    page_title="Visit Scheduler App",
    layout="centered",
    page_icon="🗓️",
)

# 背景画像（世界地図）をCSSで設定
st.markdown(
    """
    <style>
    .stApp {
        background-image: url("https://upload.wikimedia.org/wikipedia/commons/6/6e/Physical_world_map_blank_without_borders.svg");
        background-size: cover;
        background-attachment: fixed;
        background-position: center;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🗓️ Visit Schedule App")
st.caption("API-Enabled + Debug Mode")

# よく使う出発地（最大10件）
common_origins = [
    "自宅", "事務所", "福岡空港", "南筑駅", "天神", "薬院駅", "西新", "福岡市役所", "福岡ドーム", "百道浜"
]
origin_choice = st.selectbox("Departure Location", common_origins + ["Other"])
origin = st.text_input("Enter departure manually", "") if origin_choice == "Other" else origin_choice

# 移動手段
mode = st.radio("Transportation Mode", ["Driving", "Walking", "Transit"], horizontal=True)

if mode == "Driving":
    avoid_tolls = st.checkbox("Avoid toll roads", value=False)
else:
    avoid_tolls = False

# 出発日時
departure_time = st.date_input("Departure Date", datetime.now().date())
departure_hour = st.time_input("Departure Time", datetime.now().time())

# 訪問先入力
st.subheader("Add a Destination")
with st.form("destination_form"):
    name = st.text_input("Destination Name", placeholder="例：OO株式会社")
    address = st.text_input("Address", placeholder="例：福岡市南筑区～")
    stay_time = st.number_input("Stay Time (minutes)", min_value=0, value=20, step=5)
    note = st.text_area("Note (optional)", height=70)
    submit = st.form_submit_button("Add")

# セッション初期化
if "schedule" not in st.session_state:
    st.session_state.schedule = []

# 移動時間取得（Google Directions API）
def get_travel_time(origin, destination, mode, avoid_tolls):
    api_key = st.secrets["google_api"]["GOOGLE_API_KEY"]
    endpoint = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode.lower(),
        "key": api_key,
        "language": "ja"
    }
    if avoid_tolls:
        params["avoid"] = "tolls"

    res = requests.get(endpoint, params=params)
    data = res.json()
    try:
        return data["routes"][0]["legs"][0]["duration"]["text"]
    except:
        return "不明"

# 追加処理
if submit:
    if origin and name and address:
        travel_time = get_travel_time(origin, address, mode, avoid_tolls)
        google_map_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={address}&travelmode={mode.lower()}"
        if avoid_tolls and mode == "Driving":
            google_map_url += "&avoid=tolls"

        st.session_state.schedule.append({
            "name": name,
            "address": address,
            "stay": stay_time,
            "note": note,
            "move_time": travel_time,
            "url": google_map_url
        })
        st.success("✅ Added successfully")
    else:
        st.warning("⚠️ Missing input. Please enter all required fields.")

# スケジュール表示
if st.session_state.schedule:
    st.subheader("📂 Schedule Overview")
    for i, item in enumerate(st.session_state.schedule):
        st.markdown(f"**{i+1}. {item['name']}**")
        st.markdown(f"- 📍 Address: {item['address']}")
        st.markdown(f"- 🚗 Travel Time: {item['move_time']}")
        st.markdown(f"- 🕒 Stay Time: {item['stay']} min")
        if item["note"]:
            st.markdown(f"- 📝 Note: {item['note']}")
        st.markdown(f"[🌐 Open in Google Maps]({item['url']})")
        st.markdown("---")
