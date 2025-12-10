# services/data_processor.py

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import datetime, date, timezone
from typing import List, Tuple

import pandas as pd
from zoneinfo import ZoneInfo

from config.settings import SUPPORTED_COUNTRIES  # 只是為了方便知道有哪些代碼


# === 時區對照表：和 data_fetcher 裡的邏輯保持一致 ===
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


def _parse_utc_datetime(dt_str: str) -> datetime:
    """將 '2025-01-05T23:00Z' 之類字串轉成 UTC datetime。"""
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _get_timezone_for_country(country_code: str) -> ZoneInfo:
    tz_name = TZ_BY_COUNTRY.get(country_code, "UTC")
    return ZoneInfo(tz_name)


def _get_delivery_date(ts: ET.Element, country_code: str) -> date:
    """
    從單一 TimeSeries 取得交割日（當地日期）：
    timeInterval.start (UTC) → 轉當地時區 → 取日期。
    """
    ns = ts.tag.split("}")[0].strip("{")

    period = ts.find(f"{{{ns}}}Period")
    if period is None:
        raise ValueError("TimeSeries 缺少 Period 元素。")

    ti = period.find(f"{{{ns}}}timeInterval")
    if ti is None:
        raise ValueError("Period 缺少 timeInterval 元素。")

    start_elem = ti.find(f"{{{ns}}}start")
    if start_elem is None or not (start_elem.text and start_elem.text.strip()):
        raise ValueError("timeInterval 缺少 start。")

    utc_start = _parse_utc_datetime(start_elem.text)
    tz = _get_timezone_for_country(country_code)
    local_start = utc_start.astimezone(tz)
    return local_start.date()


def _resolution_to_expected_points(resolution: str) -> int:
    """
    將 'PT60M' 等解析成一天應有的點數。
    目前假設 resolution 皆為「以分鐘為單位」：
    - PT60M → 24
    - PT30M → 48
    - PT15M → 96
    若遇到其他格式，會拋出錯誤，之後再視情況擴充。
    """
    res = resolution.strip().upper()
    if not res.startswith("PT") or not res.endswith("M"):
        raise ValueError(f"暫不支援的 resolution 格式：{resolution}")

    minutes_str = res[2:-1]  # 去掉 'PT' 和 'M'
    try:
        minutes = int(minutes_str)
    except ValueError:
        raise ValueError(f"解析 resolution 分鐘數失敗：{resolution}")

    if minutes <= 0:
        raise ValueError(f"resolution 分鐘數需 > 0：{resolution}")

    # 一天 1440 分鐘
    expected = 1440 // minutes
    return expected


def _expand_points_with_fill(
    points: List[Tuple[int, float]],
    expected_points: int,
) -> List[Tuple[int, float]]:
    """
    根據 ENTSO-E 的「相同價格省略後續點」規則補值。

    - points: 已按 position 排序好的 (position, price) 列表。
    - expected_points: 一天應有的點數（如 24 / 48 / 96）。

    規則：
    - 若 position 有跳號，例如 4 → 6，則補上 5，價格 = position 4 的價格。
    - 若最後一筆 position < expected_points，例如 23/24，則 24 的價格 = position 23 的價格。
    """
    if not points:
        return []

    points = sorted(points, key=lambda x: x[0])
    expanded: List[Tuple[int, float]] = []

    prev_pos, prev_price = points[0]
    if prev_pos != 1:
        # 理論上第一個 position 應為 1，若不是就報錯，避免亂填。
        raise ValueError(f"第一個 position 不是 1，而是 {prev_pos}，資料格式可能異常。")

    expanded.append((prev_pos, prev_price))

    for pos, price in points[1:]:
        if pos <= prev_pos:
            # 非遞增代表資料有問題，先跳過或 raise；這裡選擇 raise 讓問題浮現
            raise ValueError(f"position 非遞增：{prev_pos} → {pos}")

        # 若中間有缺值，例如 prev_pos=4, pos=6，則補上 5
        if pos > prev_pos + 1:
            for missing_pos in range(prev_pos + 1, pos):
                expanded.append((missing_pos, prev_price))

        expanded.append((pos, price))
        prev_pos, prev_price = pos, price

    # 若最後一筆 position 還沒到 expected_points，補到尾端
    if prev_pos < expected_points:
        for missing_pos in range(prev_pos + 1, expected_points + 1):
            expanded.append((missing_pos, prev_price))

    # 若實際比 expected 還多，也先保留但提醒一下
    # （實務上不太可能發生，若發生代表 resolution 計算邏輯要檢查）
    if prev_pos > expected_points:
        print(
            f"[警告] 此 TimeSeries 最後 position={prev_pos}，"
            f"大於預期 {expected_points}，請檢查 resolution 配置。"
        )

    return expanded


def parse_da_xml_to_raw_csv_bytes(
    xml_bytes: bytes,
    country_code: str,
) -> bytes:
    """
    將日前電價 XML 解析為「原始」CSV：

    欄位：
    - Date: 交割日（當地日期，格式 YYYY/MM/DD）
    - Market Time Unit (MTU): position（補值後 1..N）
    - Day-ahead Price (EUR/MWh): 對應價格，依 ENTSO-E 規則補值

    額外規則：
    - 若 TimeSeries 中存在
      <classificationSequence_AttributeInstanceComponent.position>
      且其值不為 "1"，則視為其他分類序列，整條 TimeSeries 直接略過。
    """
    root = ET.fromstring(xml_bytes)
    ns = root.tag.split("}")[0].strip("{")

    rows = []

    for ts in root.findall(f".//{{{ns}}}TimeSeries"):

        # === (1) classificationSequence 過濾 ===
        cls_elem = ts.find(
            f"{{{ns}}}classificationSequence_AttributeInstanceComponent.position"
        )
        if cls_elem is not None and cls_elem.text and cls_elem.text.strip():
            cls_val = cls_elem.text.strip()
            # 目前策略：只有 "1" 或未標註者保留，其餘 (2, 3, ...) 一律略過
            if cls_val != "1":
                print(
                    "[分類序號] 跳過 TimeSeries："
                    f"classificationSequence_AttributeInstanceComponent.position = {cls_val}"
                )
                continue

        # === (2) 正常解析流程 ===
        delivery_day = _get_delivery_date(ts, country_code)

        period = ts.find(f"{{{ns}}}Period")
        if period is None:
            continue

        res_elem = period.find(f"{{{ns}}}resolution")
        if res_elem is None or not (res_elem.text and res_elem.text.strip()):
            raise ValueError("Period 缺少 resolution。")

        resolution_str = res_elem.text.strip()
        expected_points = _resolution_to_expected_points(resolution_str)

        # 收集原始 Point
        raw_points: List[Tuple[int, float]] = []
        for pt in period.findall(f"{{{ns}}}Point"):
            pos_elem = pt.find(f"{{{ns}}}position")
            price_elem = pt.find(f"{{{ns}}}price.amount")

            if (
                pos_elem is None
                or not (pos_elem.text and pos_elem.text.strip())
                or price_elem is None
                or not (price_elem.text and price_elem.text.strip())
            ):
                continue

            pos = int(pos_elem.text.strip())
            price = float(price_elem.text.strip())
            raw_points.append((pos, price))

        if not raw_points:
            print("[警告] 某一個 TimeSeries 完全沒有 Point，已略過。")
            continue

        # 依 ENTSO-E 規則補足缺漏 position
        expanded_points = _expand_points_with_fill(raw_points, expected_points)

        date_str = delivery_day.strftime("%Y/%m/%d")

        for pos, price in expanded_points:
            rows.append(
                {
                    "Date": date_str,
                    "Market Time Unit (MTU)": pos,
                    "Day-ahead Price (EUR/MWh)": price,
                }
            )

    if not rows:
        raise ValueError("解析後沒有任何資料，請檢查 XML 內容。")

    df = pd.DataFrame(rows)
    df.sort_values(by=["Date", "Market Time Unit (MTU)"], inplace=True)

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    return csv_bytes

def convert_raw_mtu_csv_to_hourly_csv_bytes(raw_csv_bytes: bytes) -> bytes:
    """
    將「原始 MTU CSV」轉換為「每小時」CSV。

    輸入 CSV 欄位（已由 parse_da_xml_to_raw_csv_bytes 產生）：
    - Date
    - Market Time Unit (MTU)
    - Day-ahead Price (EUR/MWh)

    輸出 CSV 欄位：
    - Date
    - Hour  (1..24)
    - Day-ahead Price (EUR/MWh)

    規則：
    - 若某日 MTU 數量為 24  → 視為 60 分鐘解析度，價格直接沿用（Hour = MTU）。
    - 若某日 MTU 數量為 48  → 視為 30 分鐘解析度，每 2 個 MTU 平均為 1 小時。
    - 若某日 MTU 數量為 96  → 視為 15 分鐘解析度，每 4 個 MTU 平均為 1 小時。
    """
    # 讀入原始 CSV
    buf = io.StringIO(raw_csv_bytes.decode("utf-8"))
    df = pd.read_csv(buf)

    required_cols = {
        "Date",
        "Market Time Unit (MTU)",
        "Day-ahead Price (EUR/MWh)",
    }
    if not required_cols.issubset(df.columns):
        raise ValueError(
            f"原始 CSV 欄位缺少必要欄位：{required_cols - set(df.columns)}"
        )

    df = df.copy()
    df.sort_values(by=["Date", "Market Time Unit (MTU)"], inplace=True)

    all_hourly_rows = []

    # 逐日處理
    for date_value, df_day in df.groupby("Date"):
        df_day = df_day.copy()
        n_points = len(df_day)

        if n_points == 24:
            # 60 分鐘解析度：一個 MTU 對應一個小時，價格直接沿用
            df_day["Hour"] = df_day["Market Time Unit (MTU)"].astype(int)
            hourly = df_day[["Hour", "Day-ahead Price (EUR/MWh)"]].copy()
        elif n_points == 48:
            # 30 分鐘解析度：每 2 個 MTU 平均成 1 小時
            df_day["Hour"] = (df_day["Market Time Unit (MTU)"].astype(int) - 1) // 2 + 1
            hourly = (
                df_day.groupby("Hour", as_index=False)["Day-ahead Price (EUR/MWh)"]
                .mean()
            )
        elif n_points == 96:
            # 15 分鐘解析度：每 4 個 MTU 平均成 1 小時
            df_day["Hour"] = (df_day["Market Time Unit (MTU)"].astype(int) - 1) // 4 + 1
            hourly = (
                df_day.groupby("Hour", as_index=False)["Day-ahead Price (EUR/MWh)"]
                .mean()
            )
        else:
            # 其他情況代表資料格式不在預期範圍，先明確拋錯讓問題浮現
            raise ValueError(
                f"日期 {date_value} 的 MTU 筆數為 {n_points}，"
                "目前僅支援 24 / 48 / 96 筆對應 60 / 30 / 15 分鐘解析度。"
            )

        hourly.sort_values(by="Hour", inplace=True)

        # 補上 Date 欄位
        hourly.insert(0, "Date", date_value)

        all_hourly_rows.append(hourly)

    if not all_hourly_rows:
        raise ValueError("轉換後沒有任何資料，請檢查原始 CSV。")

    df_hourly = pd.concat(all_hourly_rows, ignore_index=True)

    # 欄位順序調整為指定格式
    df_hourly = df_hourly[["Date", "Hour", "Day-ahead Price (EUR/MWh)"]]

    # 轉回 CSV bytes
    out_buf = io.StringIO()
    df_hourly.to_csv(out_buf, index=False)
    hourly_csv_bytes = out_buf.getvalue().encode("utf-8")

    return hourly_csv_bytes
