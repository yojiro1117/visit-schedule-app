
import streamlit as st
import requests

# APIキーをここに設定（セキュリティのため本番では環境変数管理を推奨）
API_KEY = "AIzaSyCLNwG_rr1xvUhEwrkAcDKKc8XFdXgUpz8"

st.set_page_config(page_title="訪問先スケジュール入力", layout="centered")

st.title("🗓️ 訪問スケジュール作成アプリ（API対応）")

# 出発地入力
origin = st.text_input("出発地（住所）", placeholder="例：福岡市中央区天神")

# 入力フォーム
with st.form(key="visit_form"):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("訪問先名称", placeholder="例：〇〇株式会社")
    with col2:
        address = st.text_input("住所", placeholder="例：福岡市博多区〜")

    stay_time = st.number_input("滞在時間（分）", min_value=0, max_value=600, step=10)
    note = st.text_area("備考（任意）", height=50)

    submit = st.form_submit_button("追加する")

# データ保存用セッション
if "schedule" not in st.session_state:
    st.session_state.schedule = []

# APIで所要時間を取得
def get_travel_time(origin, destination):
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": origin,
        "destination": destination,
        "key": API_KEY,
        "language": "ja"
    }
    res = requests.get(url, params=params)
    data = res.json()
    try:
        return data["routes"][0]["legs"][0]["duration"]["text"]
    except:
        return "取得失敗"

# 追加処理
if submit and origin and name and address:
    duration = get_travel_time(origin, address)
    google_map_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={address}&travelmode=driving"

    st.session_state.schedule.append({
        "訪問先": name,
        "住所": address,
        "所要時間": duration,
        "滞在時間": f"{stay_time}分",
        "備考": note,
        "地図リンク": google_map_url
    })
    st.success("訪問先を追加しました")

# 表示
if st.session_state.schedule:
    st.subheader("📋 入力済みスケジュール")
    for i, row in enumerate(st.session_state.schedule, 1):
        st.markdown(f"### {i}. {row['訪問先']}")
        st.write(f"📍 住所：{row['住所']}")
        st.write(f"🚗 出発地からの所要時間：{row['所要時間']}")
        st.write(f"🕒 滞在時間：{row['滞在時間']}")
        if row["備考"]:
            st.write(f"📝 備考：{row['備考']}")
        st.markdown(f"[🗺️ Googleマップで表示]({row['地図リンク']})")
        st.markdown("---")
