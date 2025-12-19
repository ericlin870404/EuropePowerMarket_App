# services/data_processor.py

"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義輔助工具 (解析度計算、補值邏輯)
3. 定義主功能：XML 轉 Raw CSV (parse_da_xml_to_raw_csv_bytes)
   3-1. 讀取 XML 並過濾 classificationSequence
   3-2. 透過 Helper 取得交割日並去重
   3-3. 解析 Point 並依 ENTSO-E 規則補值
   3-4. 輸出 Raw CSV Bytes
4. 定義主功能：Raw CSV 轉 Hourly CSV (convert_raw_mtu_csv_to_hourly_csv_bytes)
   4-1. 讀取 Raw CSV 並檢查欄位
   4-2. 依 settings 設定檢查每日資料筆數 (24/48/96)
   4-3. 聚合運算 (平均值) 轉換為小時資料
   4-4. 輸出 Hourly CSV Bytes
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import date
from typing import List, Tuple, Set

import pandas as pd

from config.settings import (
    DA_SUPPORTED_RESOLUTION_MINUTES,
    DA_SKIP_UNSUPPORTED_MTU_DAYS,
)
from utils.timezone_helper import get_da_delivery_date_from_timeseries


# =========================== #
# 2 🔹 定義輔助工具
# =========================== #
def _resolution_to_expected_points(resolution: str) -> int:
    """
    將 'PT60M' 等解析成一天應有的點數。
    目前假設 resolution 皆為「以分鐘為單位」：
    - PT60M → 24
    - PT30M → 48
    - PT15M → 96
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
    1. 若 position 有跳號，例如 4 → 6，則補上 5，價格 = position 4 的價格。
    2. 若最後一筆 position < expected_points，則後續價格皆沿用最後一筆價格。
    """
    if not points:
        return []

    points = sorted(points, key=lambda x: x[0])
    expanded: List[Tuple[int, float]] = []

    prev_pos, prev_price = points[0]
    if prev_pos != 1:
        # 理論上第一個 position 應為 1
        raise ValueError(f"第一個 position 不是 1，而是 {prev_pos}，資料格式可能異常。")

    expanded.append((prev_pos, prev_price))

    for pos, price in points[1:]:
        if pos <= prev_pos:
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

    if prev_pos > expected_points:
        print(
            f"[警告] 此 TimeSeries 最後 position={prev_pos}，"
            f"大於預期 {expected_points}，請檢查 resolution 配置。"
        )

    return expanded


# =========================== #
# 3 🔹 定義主功能：XML 轉 Raw CSV
# =========================== #
def parse_da_xml_to_raw_csv_bytes(
    xml_bytes: bytes,
    country_code: str,
) -> bytes:
    """
    將日前電價 XML 解析為「原始」CSV。
    """
    root = ET.fromstring(xml_bytes)
    ns = root.tag.split("}")[0].strip("{")

    rows = []
    seen_delivery_days: Set[date] = set()

    for ts in root.findall(f".//{{{ns}}}TimeSeries"):

        # 3-1 🔹 classificationSequence 過濾 (跳過特殊序列)
        cls_elem = ts.find(
            f"{{{ns}}}classificationSequence_AttributeInstanceComponent.position"
        )
        if cls_elem is not None and cls_elem.text and cls_elem.text.strip():
            cls_val = cls_elem.text.strip()
            print(f"[分類序號] 跳過 TimeSeries (Seq={cls_val})")
            continue

        # 3-2 🔹 取得交割日並去重
        # 這裡直接使用 timezone_helper，確保邏輯統一
        delivery_day = get_da_delivery_date_from_timeseries(ts)

        if delivery_day in seen_delivery_days:
            print(
                f"[交割日去重] 跳過 TimeSeries：交割日 {delivery_day} 已存在有效序列。"
            )
            continue
        else:
            seen_delivery_days.add(delivery_day)

        period = ts.find(f"{{{ns}}}Period")
        if period is None:
            continue

        res_elem = period.find(f"{{{ns}}}resolution")
        if res_elem is None or not (res_elem.text and res_elem.text.strip()):
            raise ValueError("Period 缺少 resolution。")

        resolution_str = res_elem.text.strip()
        expected_points = _resolution_to_expected_points(resolution_str)

        # 3-3 🔹 解析 Point 並依 ENTSO-E 規則補值
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

    # 3-4 🔹 輸出 Raw CSV Bytes
    if not rows:
        raise ValueError("解析後沒有任何資料，請檢查 XML 內容。")

    df = pd.DataFrame(rows)
    df.sort_values(by=["Date", "Market Time Unit (MTU)"], inplace=True)

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


# =========================== #
# 4 🔹 定義主功能：Raw CSV 轉 Hourly CSV
# =========================== #
def convert_raw_mtu_csv_to_hourly_csv_bytes(raw_csv_bytes: bytes) -> bytes:
    """
    將「原始 MTU CSV」轉換為「每小時」CSV。
    支援解析度：60min (24筆), 30min (48筆), 15min (96筆)。
    """
    # 4-1 🔹 讀取 Raw CSV 並檢查欄位
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

    # 允許的每日筆數集合（例如 60min -> 24, 30min -> 48, 15min -> 96）
    allowed_counts = {int(1440 / m) for m in DA_SUPPORTED_RESOLUTION_MINUTES}

    df = df.copy()
    df.sort_values(by=["Date", "Market Time Unit (MTU)"], inplace=True)

    all_hourly_rows = []

    # 4-2 🔹 依 settings 設定檢查每日資料筆數
    for date_value, df_day in df.groupby("Date"):
        df_day = df_day.copy()
        n_points = len(df_day)

        if n_points not in allowed_counts:
            msg = (
                f"日期 {date_value} 的 MTU 筆數為 {n_points}，"
                f"不符合目前支援的筆數 {sorted(allowed_counts)}。"
            )
            if DA_SKIP_UNSUPPORTED_MTU_DAYS:
                print(f"[警告] {msg} → 暫時跳過此日。")
                continue
            else:
                raise ValueError(msg)

        # 4-3 🔹 聚合運算 (平均值) 轉換為小時資料
        if n_points == 24:
            # 60 分鐘解析度
            df_day["Hour"] = df_day["Market Time Unit (MTU)"].astype(int)
            hourly = df_day[["Hour", "Day-ahead Price (EUR/MWh)"]].copy()

        elif n_points == 48:
            # 30 分鐘解析度
            df_day["Hour"] = (df_day["Market Time Unit (MTU)"].astype(int) - 1) // 2 + 1
            hourly = (
                df_day.groupby("Hour", as_index=False)["Day-ahead Price (EUR/MWh)"]
                .mean()
            )

        elif n_points == 96:
            # 15 分鐘解析度
            df_day["Hour"] = (df_day["Market Time Unit (MTU)"].astype(int) - 1) // 4 + 1
            hourly = (
                df_day.groupby("Hour", as_index=False)["Day-ahead Price (EUR/MWh)"]
                .mean()
            )
        else:
            # 理論上不會執行到此 (已由 allowed_counts 把關)
            continue

        hourly.sort_values(by="Hour", inplace=True)
        hourly.insert(0, "Date", date_value)
        all_hourly_rows.append(hourly)

    if not all_hourly_rows:
        raise ValueError("轉換後沒有任何資料，請檢查原始 CSV。")

    # 4-4 🔹 輸出 Hourly CSV Bytes
    df_hourly = pd.concat(all_hourly_rows, ignore_index=True)
    df_hourly = df_hourly[["Date", "Hour", "Day-ahead Price (EUR/MWh)"]]

    out_buf = io.StringIO()
    df_hourly.to_csv(out_buf, index=False)
    return out_buf.getvalue().encode("utf-8")

# =========================== #
# 5 🔹 定義進階分析工具
# =========================== #
def calculate_daily_stats(
    hourly_csv_bytes: bytes
) -> Tuple[bytes, dict]:
    """
    計算每日統計數據（平均電價、價差、標準差）。
    """
    buf = io.StringIO(hourly_csv_bytes.decode("utf-8"))
    df = pd.read_csv(buf)
    df["Date"] = pd.to_datetime(df["Date"])
    
    # 5-1 🔹 執行聚合運算 (新增 'std' 標準差計算)
    daily_stats = df.groupby("Date")["Day-ahead Price (EUR/MWh)"].agg(
        ["mean", "max", "min", "std"]
    ).reset_index()
    
    daily_stats["Spread"] = daily_stats["max"] - daily_stats["min"]
    
    # 重新命名欄位
    daily_stats.rename(columns={
        "mean": "Daily Average Price",
        "max": "Daily Max Price",
        "min": "Daily Min Price",
        "std": "Daily Volatility (SD)", # 新增波動率
        "Spread": "Daily Price Spread"
    }, inplace=True)
    
    daily_stats["Date_Str"] = daily_stats["Date"].dt.strftime("%Y/%m/%d")
    
    # 5-2 🔹 計算 UI 顯示用的摘要數據 (Summary Stats)
    if daily_stats.empty:
        raise ValueError("計算後的統計資料為空。")

    start_date = daily_stats["Date_Str"].iloc[0]
    end_date = daily_stats["Date_Str"].iloc[-1]
    
    # 計算各指標的區間平均
    avg_price = daily_stats["Daily Average Price"].mean()
    avg_spread = daily_stats["Daily Price Spread"].mean()
    avg_volatility = daily_stats["Daily Volatility (SD)"].mean() # 新增
    
    max_spread_idx = daily_stats["Daily Price Spread"].idxmax()
    max_spread_row = daily_stats.loc[max_spread_idx]
    
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "avg_price": round(avg_price, 2),   
        "avg_spread": round(avg_spread, 2),
        "avg_volatility": round(avg_volatility, 2), # 新增
        "max_spread": round(max_spread_row["Daily Price Spread"], 2),
        "max_spread_date": max_spread_row["Date_Str"]
    }
    
    # 5-3 🔹 輸出 CSV Bytes
    out_df = daily_stats[[
        "Date_Str", 
        "Daily Average Price", 
        "Daily Price Spread", 
        "Daily Volatility (SD)", # 匯出檔也加入此欄
        "Daily Max Price", 
        "Daily Min Price"
    ]].rename(columns={"Date_Str": "Date"})
    
    out_buf = io.StringIO()
    out_df.to_csv(out_buf, index=False, float_format="%.2f")
    
    return out_buf.getvalue().encode("utf-8"), summary