"""
📌 整體流程：
1. 引入必要套件、設定與服務層函式
2. 定義 render_fetch_da_price_page()：日前市場價格頁面
   2-1. 建立搜尋表單 (日期、國家)
   2-2. 執行輸入驗證 (日期順序、Token)
   2-3. 呼叫 API 取得原始 XML 資料
   2-4. 執行資料處理 (依設定檔決定是否解析 CSV/Hourly)
   2-5. 渲染下載按鈕 (依設定檔動態排版)
3. 定義其他功能頁面 (aFRR、資料處理、繪圖)
"""

# =========================== #
# 1 🔹 引入必要套件與設定
# =========================== #
import streamlit as st
from datetime import date

from config.settings import (
    SUPPORTED_COUNTRIES, 
    DEFAULT_ENTSOE_TOKEN, 
    DA_SUPPORTED_COUNTRIES,
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

    # 2-1 🔹 建立搜尋表單 (日期、國家)
    with st.form("fetch_da_price_form"):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日期", value=date(2025, 1, 1))
        with col2:
            end_date = st.date_input("結束日期", value=date.today())

        # 修改這裡的 options
        country_code = st.selectbox(
            "選擇國家 / 區域",
            # 只使用 DA 市場支援的國家列表
            options=DA_SUPPORTED_COUNTRIES,  
            
            # format_func 保持不變，它會拿 options 裡的代碼 (如 "FR") 
            # 去 SUPPORTED_COUNTRIES 字典查對應的中文名稱 (如 "法國")
            format_func=lambda c: SUPPORTED_COUNTRIES[c], 
        )

        submitted = st.form_submit_button("向 ENTSO-E 發送請求")

    if not submitted:
        return

    # 2-2 🔹 執行輸入驗證 (日期順序、Token)
    if start_date > end_date:
        st.error("開始日期不能晚於結束日期。")
        return

    token = DEFAULT_ENTSOE_TOKEN
    if not token:
        st.error("系統尚未設定 ENTSO-E API Token，請聯絡維護人員。")
        return

    try:
        # 2-3 🔹 呼叫 API 取得原始 XML 資料
        with st.spinner("正在向 ENTSO-E 取得日前市場價格數據…"):
            file_name_xml, xml_bytes = fetch_da_price_xml_bytes(
                start_date=start_date,
                end_date=end_date,
                country_code=country_code,
                token=token,
            )

        # 2-4 🔹 執行資料處理 (依設定檔決定是否解析 CSV/Hourly)
        # 準備資料：只在對應功能開啟時才進行轉換
        csv_bytes_raw = None
        csv_bytes_hourly = None
        
        # 僅在至少一個 CSV 下載功能開啟時，才執行 XML 解析為原始 CSV 的步驟
        if DA_DOWNLOAD_OPTIONS["csv_raw_mtu"] or DA_DOWNLOAD_OPTIONS["csv_hourly"]:
            # ① 取得「原始 MTU」CSV
            csv_bytes_raw = parse_da_xml_to_raw_csv_bytes(
                xml_bytes=xml_bytes,
                country_code=country_code,
            )

        # 僅在「每小時 CSV」下載功能開啟時，才執行轉換步驟
        if DA_DOWNLOAD_OPTIONS["csv_hourly"]:
            # ② 由「原始 MTU」CSV 轉成「每小時」CSV
            # 注意：這裡需要 csv_bytes_raw，所以會隱含觸發上面的判斷
            if csv_bytes_raw is None:
                # 為了穩健性，如果沒拿到 raw 但 hourly 開啟，再試著解析一次
                csv_bytes_raw = parse_da_xml_to_raw_csv_bytes(
                    xml_bytes=xml_bytes,
                    country_code=country_code,
                )
            csv_bytes_hourly = convert_raw_mtu_csv_to_hourly_csv_bytes(csv_bytes_raw)
        

        st.success("下載準備完成！請選擇要下載的檔案格式：")

        # 2-5 🔹 渲染下載按鈕 (依設定檔動態排版)
        # 計算需要多少欄位來排版
        active_download_options = [k for k, v in DA_DOWNLOAD_OPTIONS.items() if v]
        num_buttons = len(active_download_options)
        
        if num_buttons > 0:
            # 🔧 排版優化 (修正版)：
            # 改為 [2] * num_buttons -> 給每個按鈕 2 份寬度 (增加空間)
            # + [5]                 -> 右側維持 5 份空白緩衝
            # 這樣比例變成 2:2:5，按鈕空間變大，文字不會跑版，且依然靠左
            cols = st.columns([2] * num_buttons + [5])
            col_idx = 0

            # 根據 settings 決定是否顯示按鈕
            
            # 1. 原始 XML 檔案
            if DA_DOWNLOAD_OPTIONS["xml_original"]:
                with cols[col_idx]:
                    st.download_button(
                        label="下載 XML 檔案 (原始)",  # 文字精簡
                        data=xml_bytes,
                        file_name=file_name_xml,
                        mime="application/xml",
                        use_container_width=True, # 讓按鈕撐滿欄位
                    )
                col_idx += 1

            # 2. 原始 MTU CSV 檔案
            if DA_DOWNLOAD_OPTIONS["csv_raw_mtu"] and csv_bytes_raw is not None:
                with cols[col_idx]:
                    csv_name_raw = file_name_xml.replace(".xml", "_raw.csv")
                    st.download_button(
                        label="下載 CSV 檔案 (原始)",  # 文字精簡
                        data=csv_bytes_raw,
                        file_name=csv_name_raw,
                        mime="text/csv",
                        use_container_width=True, # 讓按鈕撐滿欄位
                    )
                col_idx += 1

            # 3. 每小時 CSV 檔案
            if DA_DOWNLOAD_OPTIONS["csv_hourly"] and csv_bytes_hourly is not None:
                with cols[col_idx]:
                    csv_name_hourly = file_name_xml.replace(".xml", "_hourly.csv")
                    st.download_button(
                        label="下載 CSV 檔案 (每小時)",  # 文字精簡
                        data=csv_bytes_hourly,
                        file_name=csv_name_hourly,
                        mime="text/csv",
                        use_container_width=True, # 讓按鈕撐滿欄位
                    )
                col_idx += 1


            st.caption(
                "＊ 「原始 CSV」為 ENTSO-E 呈現的數據；"
                "「每小時 CSV」則是依每天的解析度 (60/30/15 分鐘) 聚合為每小時平均價格。"
            )

            # ========================================== #
            # 🆕 新增功能：進階統計與分析區塊
            # ========================================== #
            # 只有當「每小時 CSV」存在時，我們才能進行每日統計運算
            if csv_bytes_hourly is not None:
                st.divider()  # 畫一條分隔線
                
                st.markdown("### 📊 進階分析結果")
                
                # 🟢 修改：expanded=False (預設收合，使用者想看再點開)
                with st.expander("每日平均電價與價差統計", expanded=False):
                    
                    # 呼叫 Processor 計算
                    stats_csv_bytes, summary = calculate_daily_stats(csv_bytes_hourly)
                    
                    # 🟢 修改：加入「平均電價」的顯示資訊
                    st.info(
                        f"**📅 資料區間**：{summary['start_date']} ~ {summary['end_date']}\n\n"
                        f"**⚡ 平均電價**： $\\large {summary['avg_price']}$ `EUR/MWh`\n\n"
                        f"**📉 平均電價差**： $\\large {summary['avg_spread']}$ `EUR/MWh`\n\n"
                        f"**🚀 最大電價差**： $\\large {summary['max_spread']}$ `EUR/MWh` "
                        f"(發生在 {summary['max_spread_date']})"
                    )

                    # 下載按鈕排版 (維持靠左)
                    stats_cols = st.columns([2, 5]) 
                    with stats_cols[0]:
                        stats_file_name = file_name_xml.replace(".xml", "_daily_stats.csv")
                        st.download_button(
                            label="下載每日統計數據",
                            data=stats_csv_bytes,
                            file_name=stats_file_name,
                            mime="text/csv",
                            type="primary",
                            use_container_width=True
                        )
        else:
            st.warning("所有下載功能皆已關閉。")


    except Exception as e:
        st.error(f"下載或解析失敗：{e}")


# =========================== #
# 3 🔹 定義其他功能頁面
# =========================== #
def render_fetch_afrr_capacity_page():
    st.header("資料獲取｜平衡服務市場 - aFRR 容量價格")
    st.info("此功能尚未實作。")


def render_data_processing_page():
    st.header("資料處理")
    st.info("此功能將處理 XML → CSV、解析度、時區等問題。")


def render_plot_page():
    st.header("繪圖區")
    st.info("此功能尚未實作。")