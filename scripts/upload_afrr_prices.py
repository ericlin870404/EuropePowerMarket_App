# scripts/upload_afrr_prices.py

"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義 Supabase 寫入工具 (upsert_rows)
3. 定義主流程 (upload_country_range)：
   3-1. 從 ENTSO-E 抓取 aFRR 容量市場 ZIP/XML
   3-2. 解析 XML → 原始資料列（不補值）
   3-3. 補值至完整 96 ISP/天
   3-4. 批次 upsert 至 afrr_capacity_prices
4. 執行進入點：依國家清單依序上傳
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client, Client

from config.settings import DEFAULT_ENTSOE_TOKEN, ENTSOE_EIC_BY_COUNTRY
from services.afrr_fetcher import (
    fetch_afrr_capacity_raw_csv_bytes,
    fill_afrr_capacity_csv_bytes,
)

import pandas as pd


# =========================== #
# 1 🔹 連線設定與常數
# =========================== #
SUPABASE_URL: str        = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
ENTSOE_TOKEN: str        = os.environ.get("ENTSOE_TOKEN", DEFAULT_ENTSOE_TOKEN)

BATCH_SIZE = 500  # 每次 upsert 的最大筆數


# =========================== #
# 2 🔹 Supabase 寫入工具
# =========================== #
def upsert_rows(client: Client, rows: List[Dict]) -> int:
    """
    將 rows 分批 upsert 至 afrr_capacity_prices。
    衝突時（相同 country_code + delivery_date + isp_index + direction）以新資料覆蓋。
    回傳實際寫入筆數。
    """
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("afrr_capacity_prices").upsert(
            batch,
            on_conflict="country_code,delivery_date,isp_index,direction",
        ).execute()
        total += len(batch)
        print(f"  [Supabase] upsert {total}/{len(rows)} 筆")
    return total


# =========================== #
# 3 🔹 主流程
# =========================== #
def filled_csv_to_rows(filled_csv_bytes: bytes, country_code: str) -> List[Dict]:
    """
    將補值後的 CSV bytes 轉為 Supabase row 格式。
    只保留 Direction 為 Up 或 Down 的資料（略過 Symmetric）。
    """
    df = pd.read_csv(pd.io.common.BytesIO(filled_csv_bytes))

    # 只保留 Up / Down
    df = df[df["Direction"].isin(["Up", "Down"])].copy()

    # 正規化日期格式 YYYY/MM/DD → YYYY-MM-DD
    df["delivery_date"] = pd.to_datetime(
        df["Delivery Period"], format="%Y/%m/%d"
    ).dt.strftime("%Y-%m-%d")

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "country_code":     country_code,
            "delivery_date":    row["delivery_date"],
            "isp_index":        int(row["ISP Index"]),
            "direction":        row["Direction"],
            "price_eur_mw_isp": round(float(row["Price (EUR/MW/ISP)"]), 4),
            "volume_mw":        round(float(row["Volume (MW)"]), 2) if pd.notna(row["Volume (MW)"]) else None,
            "resolution":       row["Resolution"],
            "time_horizon":     row.get("Time Horizon") or None,
            "source":           row.get("Source") or None,
        })
    return rows


def upload_country_range(
    client: Client,
    country_code: str,
    start_date: date,
    end_date: date,
) -> None:
    """
    抓取指定 country_code 在 [start_date, end_date] 的 aFRR 容量市場資料並寫入 Supabase。
    以月為單位分段（afrr_fetcher 內部已處理），一次最多 31 天。
    """
    print(f"\n{'='*50}")
    print(f"[上傳] {country_code}  {start_date} ~ {end_date}")
    print(f"{'='*50}")

    try:
        # 3-1 🔹 抓取原始 CSV（afrr_fetcher 內部已按月分段）
        _, raw_csv_bytes = fetch_afrr_capacity_raw_csv_bytes(
            start_date=start_date,
            end_date=end_date,
            country_code=country_code,
            token=ENTSOE_TOKEN,
        )
        print(f"  [抓取] 原始資料完成")

        # 3-2 🔹 補值至完整 ISP
        filled_csv_bytes = fill_afrr_capacity_csv_bytes(raw_csv_bytes)
        print(f"  [補值] 完成")

        # 3-3 🔹 轉換為 Supabase row 格式
        rows = filled_csv_to_rows(filled_csv_bytes, country_code)
        print(f"  [解析] 共 {len(rows)} 筆")

        if not rows:
            print(f"  [警告] {country_code} {start_date}~{end_date} 無資料，略過。")
            return

        # 3-4 🔹 批次 upsert
        inserted = upsert_rows(client, rows)
        print(f"  [完成] 寫入 {inserted} 筆")

    except Exception as e:
        print(f"  [錯誤] {country_code} {start_date}~{end_date} 失敗：{e}")
        raise


# =========================== #
# 4 🔹 執行進入點
# =========================== #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="上傳 aFRR 容量市場價格至 Supabase")
    parser.add_argument("--start",    required=True,  help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end",      required=True,  help="結束日期 YYYY-MM-DD")
    parser.add_argument(
        "--countries",
        nargs="+",
        default=["FR", "ES", "PT"],
        help="要上傳的國家代碼清單（預設 FR ES PT）",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date   = date.fromisoformat(args.end)

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    for country in args.countries:
        if country not in ENTSOE_EIC_BY_COUNTRY:
            print(f"[略過] {country} 不在 EIC 對照表中")
            continue
        try:
            upload_country_range(supabase, country, start_date, end_date)
        except Exception as e:
            print(f"[錯誤] {country} 上傳失敗：{e}")
            continue

    print("\n[完成] 全部上傳完成")
