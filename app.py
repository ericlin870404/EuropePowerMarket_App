# app.py
"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義 show_login_page()：處理使用者登入與 Session 驗證
3. 定義 show_main_app()：建構主畫面架構
   3-1. 側邊欄：第一層主選單 (資料獲取/處理/繪圖)
   3-2. 側邊欄：第二層子選單 (動態顯示)
   3-3. 路由判斷：依據選單呼叫對應頁面函式
4. 定義 main()：程式入口與登入狀態檢查
"""

# =========================== #
# 1 🔹 引入必要套件與設定
# =========================== #
import streamlit as st
from streamlit_option_menu import option_menu

from config.settings import APP_TITLE, USERS
from ui.pages import (
    render_fetch_da_price_page,
    render_fetch_afrr_capacity_page,
    render_data_processing_page,
    render_plot_page,
)
from ui.ui_theme import MINIMAL_MAIN_MENU_STYLES, MINIMAL_SUB_MENU_STYLES

# =========================== #
# 2 🔹 定義 show_login_page()
# =========================== #
def show_login_page():
    """顯示登入頁，驗證成功後在 session_state 中記錄使用者資訊。"""
    st.title(APP_TITLE)
    st.subheader("登入")

    with st.form("login_form"):
        username = st.text_input("帳號")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入")

    if submitted:
        user = USERS.get(username)
        if user and password == user["password"]:
            # 登入成功：記錄在 session_state
            st.session_state["user"] = {
                "username": username,
                "role": user["role"],
                "display_name": user.get("display_name", username),
            }
            st.success("登入成功，正在進入系統…")
            st.rerun()
        else:
            st.error("帳號或密碼錯誤，請再試一次。")


# =========================== #
# 3 🔹 定義 show_main_app()
# =========================== #
def show_main_app():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    # === Sidebar 導覽列 ===
    with st.sidebar:
        st.markdown("### 歐洲電力市場工具")

        # 3-1 🔹 側邊欄：第一層主選單 (資料獲取/處理/繪圖)
        main_choice = option_menu(
            menu_title=None,
            options=["資料獲取", "資料處理", "繪圖區"],
            icons=["cloud-download", "arrow-repeat", "bar-chart"],  # 可之後再微調
            default_index=0,
            styles=MINIMAL_MAIN_MENU_STYLES,
        )

        # 3-2 🔹 側邊欄：第二層子選單 (動態顯示)
        sub_choice = None

        if main_choice == "資料獲取":
            sub_choice = option_menu(
                menu_title=None,
                options=[
                    "電能現貨市場 - 日前市場價格",
                    "平衡服務市場 - aFRR容量價格",
                ],
                icons=["graph-up", "activity"],
                default_index=0,
                styles=MINIMAL_SUB_MENU_STYLES,
            )

        elif main_choice == "資料處理":
            sub_choice = option_menu(
                menu_title=None,
                options=[
                    "（預留）時間序列處理",
                ],
                icons=["wrench"],
                default_index=0,
                styles=MINIMAL_SUB_MENU_STYLES,
            )

        elif main_choice == "繪圖區":
            sub_choice = option_menu(
                menu_title=None,
                options=[
                    "（預留）電價圖表",
                ],
                icons=["bar-chart"],
                default_index=0,
                styles=MINIMAL_SUB_MENU_STYLES,
            )

    # 3-3 🔹 路由判斷：依據選單呼叫對應頁面函式
    if main_choice == "資料獲取":
        if sub_choice == "電能現貨市場 - 日前市場價格":
            render_fetch_da_price_page()
        elif sub_choice == "平衡服務市場 - aFRR容量價格":
            render_fetch_afrr_capacity_page()

    elif main_choice == "資料處理":
        render_data_processing_page()

    elif main_choice == "繪圖區":
        render_plot_page()


# =========================== #
# 4 🔹 定義 main()
# =========================== #
def main():
    # 如果尚未登入 → 顯示登入頁
    if "user" not in st.session_state:
        show_login_page()
    else:
        show_main_app()


if __name__ == "__main__":
    main()