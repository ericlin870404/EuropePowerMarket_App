# ui/pages.py

"""
📌 整體流程：
1. 引入必要套件、設定與服務層函式
2. 定義 render_fetch_da_price_page()：日前市場價格頁面
   2-1. 建立搜尋表單 (日期、國家)
   2-2. 執行輸入驗證與 API 呼叫 (並存入 Session State)
   2-3. 執行資料處理 (從 Session State 讀取資料)
   2-4. 渲染按鈕區域 (包含 XML/Raw/Hourly 三種下載按鈕 + 進階分析)
   2-5. 渲染進階分析區塊 (呼叫 calculate_daily_stats，四欄排版)
3. 定義其他功能頁面 (Dashboard、aFRR、收益試算)
"""

# =========================== #
# 1 🔹 引入必要套件與設定
# =========================== #
import streamlit as st
from datetime import date

# 引入設定檔
from config.settings import (
    SUPPORTED_COUNTRIES,       # Dict: 代碼 -> 中文名稱
    DEFAULT_ENTSOE_TOKEN, 
    DA_SUPPORTED_COUNTRIES,    # List: ["FR", "NL", ...] 
    DA_DOWNLOAD_OPTIONS, 
)

from services.data_fetcher import fetch_da_price_xml_bytes
from services.data_processor import (
    parse_da_xml_to_raw_csv_bytes,
    convert_raw_mtu_csv_to_hourly_csv_bytes,  
    calculate_daily_stats,
)


# =========================== #
# 2 🔹 定義 render_fetch_da_price_page()
# =========================== #
def render_fetch_da_price_page() -> None:
    st.header("資料獲取｜電能現貨市場 - 日前市場價格")

    st.markdown(
        """
        數據來源為 **ENTSO-E Transparency Platform**
        """
    )

    # 初始化 Session State (確保按鈕點擊後資料不會消失)
    if "da_xml_bytes" not in st.session_state:
        st.session_state["da_xml_bytes"] = None
    if "da_file_name" not in st.session_state:
        st.session_state["da_file_name"] = ""
    if "show_analysis" not in st.session_state:
        st.session_state["show_analysis"] = False

    # 2-1 🔹 建立搜尋表單 (日期、國家)
    with st.form("fetch_da_price_form"):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日期", value=date(2025, 1, 1))
        with col2:
            end_date = st.date_input("結束日期", value=date.today())

        country_code = st.selectbox(
            "選擇國家 / 區域",
            options=DA_SUPPORTED_COUNTRIES,  # 使用 List
            format_func=lambda c: SUPPORTED_COUNTRIES[c], # 使用 Dict 查中文
        )

        submitted = st.form_submit_button("向 ENTSO-E 發送請求")

    # 2-2 🔹 執行輸入驗證與 API 呼叫
    if submitted:
        if start_date > end_date:
            st.error("開始日期不能晚於結束日期。")
            return

        token = DEFAULT_ENTSOE_TOKEN
        if not token:
            st.error("系統尚未設定 ENTSO-E API Token，請聯絡維護人員。")
            return

        try:
            with st.spinner("正在向 ENTSO-E 取得日前市場價格數據…"):
                # 呼叫 API
                file_name_xml, xml_bytes = fetch_da_price_xml_bytes(
                    start_date=start_date,
                    end_date=end_date,
                    country_code=country_code,
                    token=token,
                )
                
                # 成功獲取後，存入 Session State
                if xml_bytes:
                    st.session_state["da_xml_bytes"] = xml_bytes
                    st.session_state["da_file_name"] = file_name_xml
                    # 重置分析顯示狀態
                    st.session_state["show_analysis"] = False 
                else:
                    st.error("未取得數據，請檢查參數設定。")
                    return

        except Exception as e:
            st.error(f"API 請求失敗：{e}")
            return

    # ========================================== #
    # 以下邏輯依賴 Session State 中的資料
    # ========================================== #
    if st.session_state["da_xml_bytes"] is not None:
        
        xml_bytes = st.session_state["da_xml_bytes"]
        file_name_xml = st.session_state["da_file_name"]

        try:
            # 2-3 🔹 執行資料處理 (依設定檔決定是否解析 CSV/Hourly)
            csv_bytes_raw = None
            csv_bytes_hourly = None
            
            # 解析原始 CSV
            if DA_DOWNLOAD_OPTIONS["csv_raw_mtu"] or DA_DOWNLOAD_OPTIONS["csv_hourly"]:
                csv_bytes_raw = parse_da_xml_to_raw_csv_bytes(
                    xml_bytes=xml_bytes,
                    country_code=country_code,
                )

            # 解析 Hourly CSV
            if DA_DOWNLOAD_OPTIONS["csv_hourly"]:
                if csv_bytes_raw is None:
                    csv_bytes_raw = parse_da_xml_to_raw_csv_bytes(
                        xml_bytes=xml_bytes,
                        country_code=country_code,
                    )
                csv_bytes_hourly = convert_raw_mtu_csv_to_hourly_csv_bytes(csv_bytes_raw)

            st.success("數據準備完成！請選擇要下載的檔案格式：")

            # 2-4 🔹 渲染按鈕區域 (排版優化：支援 XML/Raw/Hourly 三種按鈕 + 進階分析)
            # ------------------------------------------------
            # 1. 判斷各個按鈕是否應顯示
            xml_ready = DA_DOWNLOAD_OPTIONS.get("xml_original", False) and xml_bytes is not None
            raw_ready = DA_DOWNLOAD_OPTIONS["csv_raw_mtu"] and csv_bytes_raw is not None
            hourly_ready = DA_DOWNLOAD_OPTIONS["csv_hourly"] and csv_bytes_hourly is not None
            
            # 2. 動態計算欄位比例
            # 每個下載按鈕佔 2 份寬度
            col_ratios = []
            if xml_ready: col_ratios.append(2)
            if raw_ready: col_ratios.append(2)
            if hourly_ready: col_ratios.append(2)
            
            # 3. 計算緩衝區寬度 (Spacer)
            analysis_btn_width = 1.5 
            current_used = sum(col_ratios)
            
            # 總寬度維持約 9 的比例
            spacer_width = 9 - current_used - analysis_btn_width
            
            # 安全防護：避免 spacer 過小
            if spacer_width < 0.1: spacer_width = 0.1
            
            col_ratios.append(spacer_width) 
            col_ratios.append(analysis_btn_width) 
            
            cols = st.columns(col_ratios)
            col_idx = 0

            # 按鈕 1: 原始 XML
            if xml_ready:
                with cols[col_idx]:
                    st.download_button(
                        label="下載 XML 檔案(原始)",
                        data=xml_bytes,
                        file_name=file_name_xml,
                        mime="application/xml",
                        use_container_width=True
                    )
                col_idx += 1

            # 按鈕 2: 原始 CSV
            if raw_ready:
                with cols[col_idx]:
                    st.download_button(
                        label="下載 CSV 檔案 (原始)",
                        data=csv_bytes_raw,
                        file_name=file_name_xml.replace(".xml", "_raw.csv"),
                        mime="text/csv",
                        use_container_width=True
                    )
                col_idx += 1

            # 按鈕 3: 每小時 CSV
            if hourly_ready:
                with cols[col_idx]:
                    st.download_button(
                        label="下載 CSV 檔案 (每小時)",
                        data=csv_bytes_hourly,
                        file_name=file_name_xml.replace(".xml", "_hourly.csv"),
                        mime="text/csv",
                        use_container_width=True
                    )
                col_idx += 1
            
            # 按鈕 4: 進階分析 (固定在 cols[-1])
            with cols[-1]:
                btn_disabled = (csv_bytes_hourly is None)
                if st.button("📊 進階分析", type="primary", use_container_width=True, disabled=btn_disabled):
                    st.session_state["show_analysis"] = not st.session_state["show_analysis"]

            st.caption("＊ 「原始」保留 MTU 解析度；「每小時」已聚合為小時均價。")

            # 2-5 🔹 渲染進階分析區塊
            # ------------------------------------------------
            if st.session_state["show_analysis"] and csv_bytes_hourly:
                st.divider()
                st.subheader("📊 進階市場分析結果")
                
                stats_csv_bytes, summary = calculate_daily_stats(csv_bytes_hourly)
                st.caption(f"統計區間：{summary['start_date']} ~ {summary['end_date']}")
                
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("平均電價", f"{summary['avg_price']} €")
                m2.metric("平均價差", f"{summary['avg_spread']} €")
                m3.metric(
                    "最大價差", 
                    f"{summary['max_spread']} €", 
                    delta=f"發生於 {summary['max_spread_date']}",
                    delta_color="off" # 灰色顯示
                )
                m4.metric(
                    "價格波動率(Volatility)", 
                    f"{summary['avg_volatility']} €",
                    delta=f"平均標準差",
                    delta_color="off" # 灰色顯示)
                )

                st.download_button(
                    label="📥 下載 CSV 檔案 (每日統計報表)",
                    data=stats_csv_bytes,
                    file_name=file_name_xml.replace(".xml", "_daily_stats.csv"),
                    mime="text/csv"
                )

        except Exception as e:
            st.error(f"資料處理或分析失敗：{e}")


# =========================== #
# 3 🔹 定義其他功能頁面
# =========================== #
def render_dashboard_page():
    st.header("Dashboard")
    st.info("此功能開發中。")


def render_fetch_afrr_capacity_page():
    st.header("資料下載｜平衡服務市場 - aFRR 容量價格")
    st.info("此功能尚未實作。")


def render_revenue_calc_page():
    st.header("收益試算")
    st.info("此功能尚未實作。")