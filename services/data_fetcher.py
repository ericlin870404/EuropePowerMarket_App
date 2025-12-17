# services/data_fetcher.py

"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義 HTTP 請求工具 (safe_get)：封裝 requests 與重試邏輯
3. 定義 XML 過濾工具 (_filter_timeseries_by_delivery_window)：依據實際交割日篩選 TimeSeries
4. 定義主功能 (fetch_da_price_xml_bytes)：
   4-1. 參數驗證與初始化 XML Root
   4-2. 日期分段迴圈 (處理 API 天數限制)
   4-3. API 分頁迴圈 (處理 offset 與資料擷取)
   4-4. XML 解析與去重 (mRID + StartTime)
   4-5. 最終交割日過濾與 Bytes 輸出
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Set, Tuple
import xml.etree.ElementTree as ET

import requests

from config.settings import (
    ENTSOE_API_BASE_URL,
    ENTSOE_DOC_TYPE_DA_PRICE,
    ENTSOE_EIC_BY_COUNTRY,
    MAX_DAYS_PER_REQUEST_DA,
)

from utils.timezone_helper import get_da_delivery_date_from_timeseries


# =========================== #
# 2 🔹 定義 HTTP 請求工具
# =========================== #
def safe_get(
    url: str,
    params: dict,
    max_retries: int = 5,
    timeout: tuple[int, int] = (10, 60),
    sleep_seconds: float = 3.0,
) -> requests.Response:
    """
    對 ENTSO-E API 發送 GET 請求，內建重試機制。
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                print(f"[ENTSO-E 重試] 第 {attempt} 次失敗：{e}")
                time.sleep(sleep_seconds)
            else:
                raise


# =========================== #
# 3 🔹 定義 XML 過濾工具
# =========================== #
def _filter_timeseries_by_delivery_window(
    root: ET.Element,
    country_code: str,
    start_date: date,
    end_date: date,
) -> None:
    """
    依照使用者指定的 [start_date, end_date] 交割日範圍，
    將超出範圍的 TimeSeries 從 XML root 中移除。
    """
    ns = root.tag.split("}")[0].strip("{")

    # 先抓出所有 TimeSeries（用 list() 複製，避免迭代時修改）
    all_ts = list(root.findall(f".//{{{ns}}}TimeSeries"))
    print(f"[交割日過濾] 原始 TimeSeries 數量：{len(all_ts)}")

    removed = 0
    for ts in all_ts:
        try:
            # 使用外部 Helper 判斷交割日，保持邏輯一致性
            delivery_day = get_da_delivery_date_from_timeseries(ts)
        except Exception as e:
            print(f"[交割日過濾] 解析 TimeSeries 交割日失敗，跳過此筆：{e}")
            continue

        if not (start_date <= delivery_day <= end_date):
            root.remove(ts)
            removed += 1

    kept = len(all_ts) - removed
    print(f"[交割日過濾] 保留 {kept} 筆，移除 {removed} 筆。")


# =========================== #
# 4 🔹 定義主功能：下載日前電價 XML
# =========================== #
def fetch_da_price_xml_bytes(
    start_date: date,
    end_date: date,
    country_code: str,
    token: str,
) -> Tuple[str, bytes]:
    """
    從 ENTSO-E 抓取「日前電能現貨價格」的原始 XML，並依交割日範圍過濾。
    回傳：(建議檔名, XML bytes)
    """
    
    # 4-1 🔹 參數驗證與初始化
    if start_date > end_date:
        raise ValueError("start_date 不能晚於 end_date。")

    if country_code not in ENTSOE_EIC_BY_COUNTRY:
        raise ValueError(f"未支援的國家代碼：{country_code}")

    if not token:
        raise ValueError("必須提供 ENTSO-E API Token。")

    out_domain = in_domain = ENTSOE_EIC_BY_COUNTRY[country_code]

    # 建立 XML root
    ns_url = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
    ET.register_namespace("", ns_url)
    
    root = ET.Element(f"{{{ns_url}}}Publication_MarketDocument")

    current_start = start_date

    # 4-2 🔹 日期分段迴圈 (處理 MAX_DAYS 限制)
    while current_start <= end_date:
        current_end = min(
            current_start + timedelta(days=MAX_DAYS_PER_REQUEST_DA - 1),
            end_date,
        )
        print(f"[ENTSO-E] 分段抓取：{current_start} ~ {current_end}")

        # 🔸 每一個「日期分段」各自有自己的去重集合
        seen_mrids_segment: Set[str] = set()

        # 注意：這裡用 end_date + 1 天，是為了確保不漏資料；
        # 真正決定保留哪幾天會在後面的「交割日過濾」處理。
        period_start_str = current_start.strftime("%Y%m%d") + "0000"
        period_end_str = (current_end + timedelta(days=1)).strftime("%Y%m%d") + "0000"

        base_params = {
            "documentType": ENTSOE_DOC_TYPE_DA_PRICE,
            "in_Domain": in_domain,
            "out_Domain": out_domain,
            "periodStart": period_start_str,
            "periodEnd": period_end_str,
            "securityToken": token,
        }

        offset = 0
        page = 1

        # 4-3 🔹 API 分頁迴圈 (處理 offset)
        while True:
            params = dict(base_params)
            params["offset"] = str(offset)

            print(f"[ENTSO-E] 呼叫 API：offset={offset} (第 {page} 頁)")
            resp = safe_get(ENTSOE_API_BASE_URL, params=params)
            resp.encoding = "utf-8"

            try:
                page_root = ET.fromstring(resp.text)
            except ET.ParseError as e:
                raise RuntimeError(f"解析 ENTSO-E 回傳 XML 失敗：{e}")

            time_series_list = page_root.findall(f".//{{{ns_url}}}TimeSeries")

            if not time_series_list:
                print("[ENTSO-E] 本分段已無 TimeSeries，停止分頁。")
                break

            # 4-4 🔹 XML 解析與去重 (mRID + StartTime)
            new_ts_found = False
            for ts in time_series_list:
                # 取得 mRID
                mrid_elem = ts.find(f"./{{{ns_url}}}mRID")
                mrid = mrid_elem.text if mrid_elem is not None else "UNKNOWN"

                # 取得 Start Time (增加唯一性判斷)
                period_start_elem = ts.find(f"./{{{ns_url}}}Period/{{{ns_url}}}timeInterval/{{{ns_url}}}start")
                period_start_val = period_start_elem.text if period_start_elem is not None else "UNKNOWN"

                # 組合唯一的 Key (mRID + StartTime)
                unique_key = (mrid, period_start_val)

                # 使用組合 Key 進行去重
                if unique_key not in seen_mrids_segment:
                    seen_mrids_segment.add(unique_key)  # 加入 Set
                    root.append(ts)
                    new_ts_found = True

            if not new_ts_found:
                print("[ENTSO-E] 本分段分頁沒有新 TimeSeries（依據 mRID+Time 判斷），停止分頁。")
                break

            offset += 100
            page += 1
            time.sleep(1.0)

        current_start = current_end + timedelta(days=1)

    # 4-5 🔹 最終交割日過濾與 Bytes 輸出
    # 依交割日（當地日期）過濾掉多出來的日子
    _filter_timeseries_by_delivery_window(
        root=root,
        country_code=country_code,
        start_date=start_date,
        end_date=end_date,
    )

    # 組合檔名
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    file_name = f"EnergyPrice_DA_{country_code}_{start_str}_{end_str}.xml"

    # 轉 bytes（給 Streamlit download_button）
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    return file_name, xml_bytes