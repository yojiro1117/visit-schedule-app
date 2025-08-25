import streamlit as st
from datetime import datetime, timedelta

# 背景画像（世界地図）を適用
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background-image: url("https://upload.wikimedia.org/wikipedia/commons/8/80/World_map_-_low_resolution_gray_blue.png");
    background-size: cover;
    background-position: center;
}
</style>
""", unsafe_allow_html=True)

# タイトル
st.title("🗓️ 訪問スケジュール作成アプリ")
st.caption("API-Enabled + Debug Mode")

# スケジュール保存用セッション
if "schedule" not in st.session_state:
    st.session_state.schedule = []

# 出発地選択
st.text_input("出発地（住所）", key="origin", value="職場")
st.button("出発地登録")

# 移動手段
mode = st.radio("移動手段", ["車(Driving)", "徒歩(Walking)", "公共交通機関(Transit)"], horizontal=True)
avoid_tolls = False
if mode == "車(Driving)":
    avoid_tolls = st.checkbox("有料道路を避ける")

# 日時選択
date = st.date_input("出発日 (Departure Date)", value=datetime.now())
time = st.time_input("出発時刻 (Departure Time)", value=datetime.now().time())

# 訪問先入力
st.subheader("訪問先の追加 ➰")
with st.form("add_destination"):
    name = st.text_input("訪問先名称 (Name of destination)")
    address = st.text_input("住所 (address)", placeholder="例：福岡市中央区薬院〜")
    stay_time = st.number_input("滞在時間（分・minutes）", min_value=5, step=5, value=20)
    note = st.text_area("備考（任意・Remarks）", height=80)
    submitted = st.form_submit_button("追加する")

    if submitted:
        if not name:
            st.warning("⚠️ 名称が必要です。")
        else:
            # Google Mapsリンク生成
            map_url = f"https://www.google.com/maps/dir/?api=1&origin={st.session_state.origin}&destination={address or name}&travelmode={mode.split('(')[-1][:-1].lower()}"

            # スケジュールに追加
            st.session_state.schedule.append({
                "name": name,
                "address": address,
                "stay_time": stay_time,
                "date": date.strftime("%Y-%m-%d"),
                "time": time.strftime("%H:%M"),
                "note": note,
                "map_url": map_url,
                "duration": "取得失敗"
            })
            st.success("✅ 訪問先を追加しました")

# サイドバーにスケジュール一覧表示
with st.sidebar:
    st.header("📋 スケジュール一覧")
    if not st.session_state.schedule:
        st.info("訪問先はまだ登録されていません")
    for i, dest in enumerate(st.session_state.schedule, 1):
        st.markdown(f"**{i}. {dest['name']}**")
        st.markdown(f"📍 住所：{dest['address'] or '未入力'}")
        st.markdown(f"📅 出発日時：{dest['date']} {dest['time']}")
        st.markdown(f"🕓 滞在時間：{dest['stay_time']} 分")
        st.markdown(f"[🌐 Googleマップを開く]({dest['map_url']})")
        st.markdown("---")
