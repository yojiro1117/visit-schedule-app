import streamlit as st
import datetime
import requests
import urllib.parse

# タイトル部分（英語表記だけ英語 + 小さめに）
st.set_page_config(page_title="訪問スケジュール作成アプリ", layout="centered")
st.title("📅 訪問スケジュール作成アプリ")
st.caption("API-Enabled + Debug Mode")

# 背景（世界地図）
st.markdown(
    """
    <style>
    .stApp {
        background-image: url("https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/BlankMap-World.svg/2000px-BlankMap-World.svg.png");
        background-size: cover;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# 出発地候補リスト（最大10）
preset_departures = ["自宅", "事務所", "福岡空港", "博多駅", "天神", "薬院駅", "大橋駅", "北九州空港", "久留米", "小倉駅"]

# 出発地選択 or 自由入力
selected_departure = st.selectbox("出発地（住所）", options=preset_departures + ["その他"])
if selected_departure == "その他":
    origin = st.text_input("出発地を入力してください", "")
else:
    origin = selected_departure

# 移動手段の選択
mode = st.radio("移動手段（Transportation Mode）", ["Driving", "Walking", "Transit"], horizontal=True)
avoid_tolls = False
if mode == "Driving":
    avoid_tolls = st.checkbox("有料道路を回避")

# 出発日時の選択
departure_date = st.date_input("出発日 (Departure Date)", datetime.date.today())
departure_time = st.time_input("出発時刻 (Departure Time)", datetime.datetime.now().time())

# 訪問先入力
st.markdown("### 訪問先の追加")
name = st.text_input("訪問先名称", placeholder="例：○○株式会社")
address = st.text_input("住所", placeholder="例：福岡市南筑区～")
stay_time = st.number_input("滞在時間（分）", min_value=0, max_value=300, value=20, step=5)
note = st.text_area("備考（任意）")

# スケジュール保存用ステート
if "schedule" not in st.session_state:
    st.session_state.schedule = []

# Google Maps API呼び出し（移動時間取得）
def get_travel_time(origin, destination, mode, avoid_tolls):
    base_url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "mode": mode.lower(),
        "departure_time": "now",
        "key": st.secrets["google_api"]["GOOGLE_API_KEY"]
    }
    if mode == "Driving" and avoid_tolls:
        params["avoid"] = "tolls"

    res = requests.get(base_url, params=params)
    data = res.json()
    try:
        duration = data["routes"][0]["legs"][0]["duration"]["text"]
        return duration
    except:
        st.warning("🚧 移動時間の取得に失敗しました")
        return "取得失敗"

# 「追加」ボタン押下時の処理
if st.button("追加する"):
    if origin and name and address:
        duration = get_travel_time(origin, address, mode, avoid_tolls)
        gmap_url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(origin)}&destination={urllib.parse.quote(address)}&travelmode={mode.lower()}"

        st.session_state.schedule.append({
            "訪問先": name,
            "住所": address,
            "移動時間": duration,
            "滞在時間": f"{stay_time}分",
            "備考": note,
            "地図リンク": gmap_url
        })
        st.success("✅ 訪問先を追加しました")
    else:
        st.warning("⚠️ 入力が不足しています（出発地・名称・住所すべてが必要です）")

# 右側にスケジュール表示
if st.session_state.schedule:
    st.markdown("---")
    st.markdown("### 📋 現在のスケジュール")
    for i, row in enumerate(st.session_state.schedule, 1):
        st.markdown(f"**{i}. {row['訪問先']}** → **{row['住所']}**")
        st.markdown(f"🕒 移動時間：{row['移動時間']} ／ 滞在：{row['滞在時間']}")
        st.markdown(f"🔗 [Googleマップで表示]({row['地図リンク']})")
        if row['備考']:
            st.markdown(f"✏️ 備考：{row['備考']}")
        st.markdown("---")
