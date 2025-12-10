# app.py
import streamlit as st
from streamlit_option_menu import option_menu

from config.settings import APP_TITLE
from ui.pages import (
    render_fetch_da_price_page,
    render_fetch_afrr_capacity_page,
    render_data_processing_page,
    render_plot_page,
)
from ui.ui_theme import MINIMAL_MAIN_MENU_STYLES, MINIMAL_SUB_MENU_STYLES


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")

    # === Sidebar 導覽列 ===
    with st.sidebar:
        st.markdown("### 歐洲電力市場工具")

        # 第一層：三大區塊（Notion 風格）
        main_choice = option_menu(
            menu_title=None,
            options=["資料獲取", "資料處理", "繪圖區"],
            icons=["cloud-download", "arrow-repeat", "bar-chart"],  # 可之後再微調
            default_index=0,
            styles=MINIMAL_MAIN_MENU_STYLES,
        )

        # 第二層：依主選單顯示子項目（Notion 風格）
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

    # === 主畫面依選項顯示內容 ===
    if main_choice == "資料獲取":
        if sub_choice == "電能現貨市場 - 日前市場價格":
            render_fetch_da_price_page()
        elif sub_choice == "平衡服務市場 - aFRR容量價格":
            render_fetch_afrr_capacity_page()

    elif main_choice == "資料處理":
        render_data_processing_page()

    elif main_choice == "繪圖區":
        render_plot_page()


if __name__ == "__main__":
    main()
