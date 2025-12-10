import streamlit as st
from datetime import date

from config.settings import SUPPORTED_COUNTRIES, DEFAULT_ENTSOE_TOKEN
from services.data_fetcher import fetch_da_price_xml_bytes
from services.data_processor import parse_da_xml_to_raw_csv_bytes  # ★ 新增

def render_fetch_da_price_page() -> None:
    st.header("資料獲取｜電能現貨市場 - 日前市場價格")

    st.markdown(
        """
        目前這個頁面只實作 **Step 1：下載 ENTSO-E 回傳的原始 XML**，
        並提供「原始 MTU」格式的 CSV 檔案下載。
        之後會再增加「每小時補值」等進階處理。
        """
    )

    with st.form("fetch_da_price_form"):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日期", value=date(2025, 1, 1))
        with col2:
            end_date = st.date_input("結束日期", value=date.today())

        country_code = st.selectbox(
            "選擇國家 / 區域",
            options=list(SUPPORTED_COUNTRIES.keys()),
            format_func=lambda c: SUPPORTED_COUNTRIES[c],
        )

        submitted = st.form_submit_button("向 ENTSO-E 下載原始 XML")

    if not submitted:
        return

    if start_date > end_date:
        st.error("開始日期不能晚於結束日期。")
        return

    token = DEFAULT_ENTSOE_TOKEN
    if not token:
        st.error("系統尚未設定 ENTSO-E API Token，請聯絡維護人員。")
        return

    try:
        with st.spinner("正在從 ENTSO-E 取得日前價格資料（原始 XML）…"):
            file_name_xml, xml_bytes = fetch_da_price_xml_bytes(
                start_date=start_date,
                end_date=end_date,
                country_code=country_code,
                token=token,
            )

        # ★ 取得「原始 MTU」CSV
        csv_bytes_raw = parse_da_xml_to_raw_csv_bytes(
            xml_bytes=xml_bytes,
            country_code=country_code,
        )

        st.success("下載準備完成！請選擇要下載的檔案格式：")

        col_xml, col_csv_raw = st.columns(2)

        with col_xml:
            st.download_button(
                label="下載原始 XML 檔案",
                data=xml_bytes,
                file_name=file_name_xml,
                mime="application/xml",
            )

        with col_csv_raw:
            csv_name = file_name_xml.replace(".xml", "_raw.csv")
            st.download_button(
                label="下載 CSV 檔案 (原始)",
                data=csv_bytes_raw,
                file_name=csv_name,
                mime="text/csv",
            )

        st.caption(
            "＊「原始」CSV 以 MTU 序列 (1..N) 表示時間，"
            "已依 ENTSO-E 規則補回省略的相同價格區間。"
        )

    except Exception as e:
        st.error(f"下載或解析失敗：{e}")



# ⭐ 加回這個函式避免 ImportError
def render_fetch_afrr_capacity_page():
    st.header("資料獲取｜平衡服務市場 - aFRR 容量價格")
    st.info("此功能尚未實作。")


def render_data_processing_page():
    st.header("資料處理")
    st.info("此功能將處理 XML → CSV、解析度、時區等問題。")


def render_plot_page():
    st.header("繪圖區")
    st.info("此功能尚未實作。")
