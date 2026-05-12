# services/afrr_fetcher.py

"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義月分段工具 (_build_monthly_segments)：將查詢區間切為不跨月的段落
3. 定義 XML 解析工具 (_parse_afrr_xml_content)：ZIP→XML→原始資料列（不補值）
4. 定義補值工具 (_expand_afrr_points_with_fill)：依 ENTSO-E 省略規則前向填充 ISP
5. 定義主功能 fetch_afrr_capacity_raw_csv_bytes：依月抓取並回傳原始 CSV
6. 定義主功能 fill_afrr_capacity_csv_bytes：讀取原始 CSV 並補齊所有 ISP 位置
"""

from __future__ import annotations

import io
import time
import zipfile
from datetime import date, timedelta
from typing import List, Tuple

import pandas as pd
import xml.etree.ElementTree as ET

from config.settings import (
    ENTSOE_API_BASE_URL,
    ENTSOE_EIC_BY_COUNTRY,
    ENTSOE_DOC_TYPE_BALANCING_CAPACITY,
    BALANCING_CAPACITY_BUSINESS_TYPE,
    BALANCING_CAPACITY_PROCESS_TYPE_AFRR,
    BALANCING_CAPACITY_MARKET_AGREEMENT_TYPE,
)
from services.data_fetcher import safe_get


# =========================== #
# 2 🔹 月分段工具
# =========================== #
def _build_monthly_segments(start_date: date, end_date: date) -> List[Tuple[date, date]]:
    """
    📌 整體流程：
    1. 從 start_date 開始，每次取到月底（或 end_date）為一段
    2. 依序推進至下個月首，直到超過 end_date
    """
    segments = []
    seg_start = start_date
    while seg_start <= end_date:
        # 2-1 🔹 計算本段結束日（月底或使用者指定的 end_date）
        if seg_start.month == 12:
            next_month_first = date(seg_start.year + 1, 1, 1)
        else:
            next_month_first = date(seg_start.year, seg_start.month + 1, 1)
        seg_end = min(end_date, next_month_first - timedelta(days=1))
        segments.append((seg_start, seg_end))
        seg_start = next_month_first
    return segments


# =========================== #
# 3 🔹 XML 解析工具
# =========================== #
_AFRR_NS_URL = "urn:iec62325.351:tc57wg16:451-6:balancingdocument:4:4"
_DIRECTION_MAP = {"A01": "Up", "A02": "Down", "A03": "Symmetric"}
_TIME_HORIZON_MAP = {
    "A01": "Daily", "A02": "Weekly", "A03": "Monthly",
    "A04": "Yearly", "A06": "Long term", "A13": "Hourly",
}
_SOURCE_MAP = {"A03": "Mixed", "A04": "Generation", "A05": "Load"}


def _resolution_to_expected_points(resolution: str) -> int:
    """將解析度字串轉為一天應有的 ISP 總筆數。P1D 回傳 1（無需補值）。"""
    if resolution == "P1D":
        return 1
    res = resolution.strip().upper()
    if res.startswith("PT") and res.endswith("M"):
        minutes = int(res[2:-1])
        return 1440 // minutes
    raise ValueError(f"不支援的解析度格式：{resolution}")


def _parse_afrr_xml_content(
    xml_content: str,
    seg_start: date,
    seg_end: date,
) -> List[dict]:
    """
    📌 整體流程：
    1. 解析 XML 取出所有 TimeSeries
    2. 從每個 TimeSeries 讀取方向、時間期限、來源等屬性
    3. 從 Period 取得交割日（timeInterval/end 的日期部分）與解析度
    4. 只保留交割日在 [seg_start, seg_end] 的 Point，不補值
    """
    ns = {"ns": _AFRR_NS_URL}
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"[aFRR] XML 解析失敗：{e}")
        return []

    rows = []
    for ts in root.findall("ns:TimeSeries", ns):
        # 3-1 🔹 讀取 TimeSeries 屬性
        direction_elem = ts.find("ns:flowDirection.direction", ns)
        market_type_elem = ts.find("ns:type_MarketAgreement.type", ns)
        psr_type_elem = ts.find("ns:mktPSRType.psrType", ns)
        if any(e is None or not e.text for e in [direction_elem, market_type_elem, psr_type_elem]):
            continue

        direction = _DIRECTION_MAP.get(direction_elem.text, direction_elem.text)
        time_horizon = _TIME_HORIZON_MAP.get(market_type_elem.text, market_type_elem.text)
        source = _SOURCE_MAP.get(psr_type_elem.text, psr_type_elem.text)

        for period in ts.findall("ns:Period", ns):
            # 3-2 🔹 取得交割日（timeInterval/end 的日期部分）
            end_elem = period.find("ns:timeInterval/ns:end", ns)
            if end_elem is None or not end_elem.text:
                continue
            try:
                delivery_date = date.fromisoformat(end_elem.text.split("T")[0])
            except ValueError:
                continue

            # 只保留使用者查詢區間內的資料（過濾 API 超出範圍的日期）
            if not (seg_start <= delivery_date <= seg_end):
                continue

            # 3-3 🔹 讀取解析度
            res_elem = period.find("ns:resolution", ns)
            if res_elem is None or not res_elem.text:
                continue
            resolution = res_elem.text.strip()

            delivery_str = delivery_date.strftime("%Y/%m/%d")

            # 3-4 🔹 逐筆讀取 Point（不補值，只保留 API 實際回傳的 position）
            for point in period.findall("ns:Point", ns):
                pos_elem = point.find("ns:position", ns)
                qty_elem = point.find("ns:quantity", ns)
                price_elem = point.find("ns:procurement_Price.amount", ns)

                if any(
                    e is None or not (e.text and e.text.strip())
                    for e in [pos_elem, qty_elem, price_elem]
                ):
                    continue

                rows.append({
                    "Delivery Period": delivery_str,
                    "ISP Index": int(pos_elem.text),
                    "Resolution": resolution,
                    "Reserve Type": "aFRR",
                    "Time Horizon": time_horizon,
                    "Source": source,
                    "Volume (MW)": float(qty_elem.text),
                    "Price (EUR/MW/ISP)": float(price_elem.text),
                    "Price Type": "Average",
                    "Direction": direction,
                })

    return rows


# =========================== #
# 4 🔹 補值工具
# =========================== #
def _expand_afrr_points_with_fill(
    points: List[Tuple[int, float, float]],
    expected_points: int,
) -> List[Tuple[int, float, float]]:
    """
    📌 整體流程：
    1. 排序 points，確認第一個 position 為 1
    2. 若中間有跳號，插入缺漏的 position 並沿用前一個 (qty, price)
    3. 若最後一筆 position < expected_points，補齊尾端

    points 格式：List of (position, quantity, price)
    """
    if not points:
        return []

    points = sorted(points, key=lambda x: x[0])
    expanded: List[Tuple[int, float, float]] = []

    prev_pos, prev_qty, prev_price = points[0]
    if prev_pos != 1:
        raise ValueError(f"第一個 position 不是 1，而是 {prev_pos}，資料格式可能異常。")
    expanded.append((prev_pos, prev_qty, prev_price))

    # 4-1 🔹 處理中間跳號
    for pos, qty, price in points[1:]:
        if pos <= prev_pos:
            raise ValueError(f"position 非遞增：{prev_pos} → {pos}")
        for missing in range(prev_pos + 1, pos):
            expanded.append((missing, prev_qty, prev_price))
        expanded.append((pos, qty, price))
        prev_pos, prev_qty, prev_price = pos, qty, price

    # 4-2 🔹 補齊尾端缺漏
    for missing in range(prev_pos + 1, expected_points + 1):
        expanded.append((missing, prev_qty, prev_price))

    return expanded


# =========================== #
# 5 🔹 主功能：取得原始 CSV
# =========================== #
def fetch_afrr_capacity_raw_csv_bytes(
    start_date: date,
    end_date: date,
    country_code: str,
    token: str,
) -> Tuple[str, bytes]:
    """
    📌 整體流程：
    1. 驗證參數，建立月分段清單
    2. 依序對每個月分段呼叫 ENTSO-E API，取得 ZIP → 解析 XML → 收集資料列
    3. 合併去重後輸出原始 CSV（不補值）
    回傳：(建議檔名, raw_csv_bytes)
    """
    # 5-1 🔹 參數驗證
    if start_date > end_date:
        raise ValueError("start_date 不能晚於 end_date。")
    if country_code not in ENTSOE_EIC_BY_COUNTRY:
        raise ValueError(f"未支援的國家代碼：{country_code}")

    control_area = ENTSOE_EIC_BY_COUNTRY[country_code]
    segments = _build_monthly_segments(start_date, end_date)
    all_rows: List[dict] = []

    # 5-2 🔹 依月分段呼叫 API
    for i, (seg_start, seg_end) in enumerate(segments, 1):
        # ENTSO-E aFRR API 的時間格式：{YYYYMMDD}2300 (UTC+0 23:00)
        period_start_str = (seg_start - timedelta(days=1)).strftime("%Y%m%d") + "2300"
        period_end_str = seg_end.strftime("%Y%m%d") + "2300"

        print(
            f"[aFRR] 第 {i}/{len(segments)} 段：{seg_start} ~ {seg_end} "
            f"(API: {period_start_str} → {period_end_str})"
        )

        params = {
            "documentType": ENTSOE_DOC_TYPE_BALANCING_CAPACITY,
            "businessType": BALANCING_CAPACITY_BUSINESS_TYPE,
            "processType": BALANCING_CAPACITY_PROCESS_TYPE_AFRR,
            "Type_MarketAgreement.Type": BALANCING_CAPACITY_MARKET_AGREEMENT_TYPE,
            "controlArea_Domain": control_area,
            "periodStart": period_start_str,
            "periodEnd": period_end_str,
            "securityToken": token,
        }

        try:
            resp = safe_get(ENTSOE_API_BASE_URL, params=params)
        except Exception as e:
            print(f"[aFRR] 第 {i} 段請求失敗：{e}，略過此段。")
            continue

        # 5-3 🔹 解壓 ZIP 並解析 XML
        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    with zf.open(name) as f:
                        xml_content = f.read().decode("utf-8")
                    rows = _parse_afrr_xml_content(xml_content, seg_start, seg_end)
                    all_rows.extend(rows)
        except zipfile.BadZipFile:
            print(f"[aFRR] 第 {i} 段回傳內容非 ZIP 格式，略過。")
            continue

        if i < len(segments):
            time.sleep(1.0)

    if not all_rows:
        raise ValueError(
            "未取得任何 aFRR 容量市場資料，"
            "請確認查詢區間、國家選擇或 API Token 是否正確。"
        )

    # 5-4 🔹 合併去重並輸出 CSV
    df = pd.DataFrame(all_rows)
    df.drop_duplicates(inplace=True)
    df.sort_values(
        by=["Delivery Period", "Direction", "Time Horizon", "Source", "ISP Index"],
        inplace=True,
    )

    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    file_name = f"aFRR_Capacity_{country_code}_{start_str}_{end_str}_raw.csv"

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return file_name, buf.getvalue().encode("utf-8")


# =========================== #
# 6 🔹 主功能：補值後輸出 CSV
# =========================== #
def fill_afrr_capacity_csv_bytes(raw_csv_bytes: bytes) -> bytes:
    """
    📌 整體流程：
    1. 讀取原始 CSV 並驗證欄位
    2. 依 (交割日, 方向, 時間期限, 來源) 分群組
    3. 對每個群組：依 Resolution 計算 expected_points，呼叫補值工具
    4. 合併所有群組並輸出補值後的 CSV bytes
    """
    # 6-1 🔹 讀取並驗證
    df = pd.read_csv(io.StringIO(raw_csv_bytes.decode("utf-8")))
    required_cols = {"Delivery Period", "ISP Index", "Resolution", "Direction", "Time Horizon", "Source"}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        raise ValueError(f"原始 CSV 缺少必要欄位：{missing_cols}")

    df["ISP Index"] = pd.to_numeric(df["ISP Index"], errors="coerce")
    df.dropna(subset=["ISP Index"], inplace=True)
    df["ISP Index"] = df["ISP Index"].astype(int)

    group_keys = ["Delivery Period", "Direction", "Time Horizon", "Source"]
    df.dropna(subset=group_keys, inplace=True)

    # 6-2 🔹 依群組補值
    filled_frames: List[pd.DataFrame] = []

    for _, group in df.groupby(group_keys, sort=False):
        group = group.copy().sort_values("ISP Index").drop_duplicates(subset=["ISP Index"])
        resolution = group["Resolution"].iloc[0]

        try:
            expected = _resolution_to_expected_points(resolution)
        except ValueError as e:
            print(f"[aFRR 補值] 無法判斷解析度：{e}，保留原始資料。")
            filled_frames.append(group)
            continue

        # P1D 或資料已完整，直接保留
        if expected == 1 or len(group) >= expected:
            filled_frames.append(group)
            continue

        # 6-3 🔹 執行補值
        raw_points = list(zip(
            group["ISP Index"].tolist(),
            group["Volume (MW)"].tolist(),
            group["Price (EUR/MW/ISP)"].tolist(),
        ))

        try:
            filled_pts = _expand_afrr_points_with_fill(raw_points, expected)
        except ValueError as e:
            print(f"[aFRR 補值] 補值失敗（{e}），保留原始資料。")
            filled_frames.append(group)
            continue

        template = group.iloc[0].to_dict()
        new_rows = []
        for pos, qty, price in filled_pts:
            r = dict(template)
            r["ISP Index"] = pos
            r["Volume (MW)"] = qty
            r["Price (EUR/MW/ISP)"] = price
            new_rows.append(r)
        filled_frames.append(pd.DataFrame(new_rows))

    if not filled_frames:
        raise ValueError("補值後無任何資料。")

    # 6-4 🔹 合併並輸出
    df_filled = pd.concat(filled_frames, ignore_index=True)
    df_filled.sort_values(
        by=["Delivery Period", "Direction", "Time Horizon", "Source", "ISP Index"],
        inplace=True,
    )

    buf = io.StringIO()
    df_filled.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# =========================== #
# 7 🔹 主功能：補值後轉為小時 CSV
# =========================== #
def convert_afrr_filled_to_hourly_csv_bytes(filled_csv_bytes: bytes) -> bytes:
    """
    📌 整體流程：
    1. 讀取補值後 CSV，驗證必要欄位
    2. 依 Resolution 計算每小時含幾個 ISP（PT15M→4, PT30M→2, PT60M→1）
    3. 依 (Delivery Period, Direction) 分組，彙總每小時價格加總
    4. 輸出僅含 Date / Hour / Price (EUR/MW/h) / Direction 的 CSV bytes
    """
    import math

    # 7-1 🔹 讀取並驗證
    df = pd.read_csv(io.StringIO(filled_csv_bytes.decode("utf-8")))
    required_cols = {"Delivery Period", "ISP Index", "Resolution", "Price (EUR/MW/ISP)", "Direction"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"補值 CSV 缺少必要欄位：{missing}")

    df["ISP Index"] = pd.to_numeric(df["ISP Index"], errors="coerce")
    df["Price (EUR/MW/ISP)"] = pd.to_numeric(df["Price (EUR/MW/ISP)"], errors="coerce")
    df.dropna(subset=["ISP Index", "Price (EUR/MW/ISP)"], inplace=True)
    df["ISP Index"] = df["ISP Index"].astype(int)

    # 7-2 🔹 依解析度計算每小時的 ISP 數
    def _isp_per_hour(resolution: str) -> int:
        res = resolution.strip().upper()
        if res == "P1D":
            return 24
        if res.startswith("PT") and res.endswith("M"):
            return 60 // int(res[2:-1])
        raise ValueError(f"不支援的解析度：{resolution}")

    # 7-3 🔹 逐列計算所屬小時（依各列自身 Resolution）
    def _compute_hour(row):
        isp_per_h = _isp_per_hour(row["Resolution"])
        return math.ceil(row["ISP Index"] / isp_per_h)

    df["Hour"] = df.apply(_compute_hour, axis=1)

    # 7-4 🔹 依 (日期, Hour, Direction) 加總 ISP 價格
    hourly = (
        df.groupby(["Delivery Period", "Hour", "Direction"], sort=True)["Price (EUR/MW/ISP)"]
        .sum()
        .reset_index()
    )
    hourly.rename(columns={
        "Delivery Period": "Date",
        "Price (EUR/MW/ISP)": "Price (EUR/MW/h)",
    }, inplace=True)
    hourly = hourly[["Date", "Hour", "Price (EUR/MW/h)", "Direction"]]

    buf = io.StringIO()
    hourly.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")
