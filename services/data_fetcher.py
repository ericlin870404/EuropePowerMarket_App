# services/data_fetcher.py

from __future__ import annotations

import time
from datetime import date, timedelta, datetime, timezone
from typing import Set, Tuple

import requests
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo  # Python 3.9+ 標準庫

from config.settings import (
    ENTSOE_API_BASE_URL,
    ENTSOE_DOC_TYPE_DA_PRICE,
    ENTSOE_EIC_BY_COUNTRY,
    MAX_DAYS_PER_REQUEST_DA,
)

# 各國時區（用來把 UTC 轉成本地時間，取得交割日）
TZ_BY_COUNTRY = {
    "FR": "Europe/Paris",
    "BE": "Europe/Brussels",
    "NL": "Europe/Amsterdam",
    "ES": "Europe/Madrid",
    "PT": "Europe/Lisbon",
    "IT-North": "Europe/Rome",
    "IT-South": "Europe/Rome",
    "GB": "Europe/London",
    "CZ": "Europe/Prague",
    "CH": "Europe/Zurich",
}


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


# ====== 交割日判斷相關工具 ======

def _parse_utc_datetime(dt_str: str) -> datetime:
    """
    將類似 '2024-12-31T23:00Z' 的字串轉成 UTC datetime。
    """
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _get_timezone_for_country(country_code: str) -> ZoneInfo:
    """
    根據國家代碼取得時區，若查不到則回傳 UTC。
    """
    tz_name = TZ_BY_COUNTRY.get(country_code, "UTC")
    return ZoneInfo(tz_name)


def get_delivery_date_from_timeseries(
    ts: ET.Element,
    country_code: str,
) -> date:
    """
    由單一 TimeSeries 判斷「交割日」（當地日期）。

    作法：
    - 讀取 Period/timeInterval/start (UTC)
    - 轉換成對應國家的本地時間
    - 取 local datetime 的 .date() 當成交割日
    例如：
    - 2024-12-31T23:00Z → 2025-01-01 00:00 (Europe/Paris) → 2025-01-01
    """
    ns = ts.tag.split("}")[0].strip("{")

    period = ts.find(f"{{{ns}}}Period")
    if period is None:
        raise ValueError("TimeSeries 缺少 Period 元素。")

    time_interval = period.find(f"{{{ns}}}timeInterval")
    if time_interval is None:
        raise ValueError("Period 缺少 timeInterval 元素。")

    start_elem = time_interval.find(f"{{{ns}}}start")
    if start_elem is None or not (start_elem.text and start_elem.text.strip()):
        raise ValueError("timeInterval 缺少 start 元素或內容。")

    utc_start = _parse_utc_datetime(start_elem.text)
    tz = _get_timezone_for_country(country_code)
    local_start = utc_start.astimezone(tz)

    return local_start.date()


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
            delivery_day = get_delivery_date_from_timeseries(ts, country_code)
        except Exception as e:
            # 如遇到格式問題，不直接中斷，可視情況改成 raise
            print(f"[交割日過濾] 解析 TimeSeries 交割日失敗，跳過此筆：{e}")
            continue

        if not (start_date <= delivery_day <= end_date):
            root.remove(ts)
            removed += 1

    kept = len(all_ts) - removed
    print(f"[交割日過濾] 保留 {kept} 筆，移除 {removed} 筆。")


# ====== 主功能：下載日前電價 XML（並依交割日篩選） ======

def fetch_da_price_xml_bytes(
    start_date: date,
    end_date: date,
    country_code: str,
    token: str,
) -> Tuple[str, bytes]:
    """
    從 ENTSO-E 抓取「日前電能現貨價格」的原始 XML，並依交割日範圍過濾。

    步驟：
    1. 以使用者輸入的 [start_date, end_date] 轉成 API 的 periodStart/periodEnd
       （這裡仍使用 end_date + 1 天，確保不漏資料）
    2. 依 MAX_DAYS_PER_REQUEST_DA 切段呼叫 API，並處理 offset 分頁
    3. 以 TimeSeries 的 mRID 去重，合併到一個 Publication_MarketDocument
    4. 依各 TimeSeries 的交割日（本地日期）過濾，只保留
       start_date <= 交割日 <= end_date 的 TimeSeries
    5. 回傳建議檔名 + XML bytes（供 Streamlit download_button 使用）
    """
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

    seen_mrids: Set[str] = set()
    current_start = start_date

    while current_start <= end_date:
        current_end = min(
            current_start + timedelta(days=MAX_DAYS_PER_REQUEST_DA - 1),
            end_date,
        )
        print(f"[ENTSO-E] 分段抓取：{current_start} ~ {current_end}")

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

            new_ts_found = False
            for ts in time_series_list:
                mrid_elem = ts.find(f"./{{{ns_url}}}mRID")
                mrid = mrid_elem.text if mrid_elem is not None else None

                if mrid and mrid not in seen_mrids:
                    seen_mrids.add(mrid)
                    root.append(ts)
                    new_ts_found = True

            if not new_ts_found:
                print("[ENTSO-E] 本分段分頁沒有新 TimeSeries，停止分頁。")
                break

            offset += 100
            page += 1
            time.sleep(1.0)  # 避免對 API 造成過大壓力

        current_start = current_end + timedelta(days=1)

    # 依交割日（當地日期）過濾掉多出來的日子（例如 2025-01-04）
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
