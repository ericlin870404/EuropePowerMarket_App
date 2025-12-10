# ui/pages.py
import streamlit as st
from config.settings import SUPPORTED_COUNTRIES

def render_fetch_da_price_page():
    st.header("資料獲取｜電能現貨市場 - 日前市場價格")

    start_date = st.date_input("開始日期")
    end_date = st.date_input("結束日期")

    country = st.selectbox(
        "選擇國家",
        options=list(SUPPORTED_COUNTRIES.keys()),
        format_func=lambda c: f"{c} - {SUPPORTED_COUNTRIES[c]}",
    )

    if st.button("下載原始資料（Excel）"):
        st.info("之後會在這裡接 ENTSO-E 日前市場 API，產出檔案。")


def render_fetch_afrr_capacity_page():
    st.header("資料獲取｜平衡服務市場 - aFRR 容量價格")
    st.warning("目前僅保留位置，之後再接 aFRR 容量價格 API。")


def render_data_processing_page():
    st.header("資料處理")
    st.write("之後會放補值、解析度轉換等功能。")


def render_plot_page():
    st.header("繪圖區")
    st.write("之後會放電價曲線、多國比較等圖表。")
