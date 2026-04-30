"""
📌 整體流程：
1. 引入必要套件與設定
2. 定義 Supabase 寫入工具 (upsert_rows)
3. 定義主流程 (upload_country_range)：
   3-1. 從 ENTSO-E 抓取 XML
   3-2. 解析 XML → MTU rows
   3-3. 批次 upsert 至 Supabase
   3-4. 寫入 da_fetch_log
4. 執行進入點：依國家清單依序上傳
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import List, Dict

# 讓腳本可以從 scripts/ 資料夾直接執行，找到上層的 services / config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from supabase import create_client, Client

from config.settings import DEFAULT_ENTSOE_TOKEN, ENTSOE_EIC_BY_COUNTRY
from services.data_fetcher import fetch_da_price_xml_bytes
from utils.timezone_helper import get_da_delivery_date_from_timeseries


# =========================== #
# 1 🔹 Supabase 連線設定
# =========================== #
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
ENTSOE_TOKEN: str = os.environ.get("ENTSOE_TOKEN", DEFAULT_ENTSOE_TOKEN)

BATCH_SIZE = 500  # 每次 upsert 的最大筆數


# =========================== #
# 2 🔹 定義 Supabase 寫入工具
# =========================== #
def upsert_rows(client: Client, rows: List[Dict]) -> int:
    """
    將 rows 分批 upsert 至 da_prices。
    衝突時（相同 zone_key + delivery_date + mtu_position）以新資料覆蓋。
    回傳實際寫入筆數。
    """
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        client.table("da_prices").upsert(
            batch,
            on_conflict="zone_key,delivery_date,mtu_position",
        ).execute()
        total += len(batch)
        print(f"  [Supabase] upsert {total}/{len(rows)} 筆")
    return total


def log_fetch(client: Client, zone_key: str, start: date, end: date, rows_inserted: int) -> None:
    """寫入一筆 da_fetch_log 紀錄。"""
    client.table("da_fetch_log").insert({
        "zone_key": zone_key,
        "fetch_start": start.isoformat(),
        "fetch_end": end.isoformat(),
        "rows_inserted": rows_inserted,
    }).execute()


# =========================== #
# 3 🔹 定義主流程
# =========================== #
def _resolution_minutes(resolution_str: str) -> int:
    """'PT15M' → 15, 'PT60M' → 60"""
    s = resolution_str.strip().upper()
    if s.startswith("PT") and s.endswith("M"):
        return int(s[2:-1])
    raise ValueError(f"無法解析 resolution：{resolution_str}")


def _expand_points_with_fill(points, expected_points: int):
    """
    ENTSO-E 補值規則：position 跳號時沿用前一個價格。
    直接複用 data_processor 的邏輯（此處獨立實作以避免 CSV 中介步驟）。
    """
    if not points:
        return []
    points = sorted(points, key=lambda x: x[0])
    expanded = []
    prev_pos, prev_price = points[0]
    expanded.append((prev_pos, prev_price))
    for pos, price in points[1:]:
        for missing in range(prev_pos + 1, pos):
            expanded.append((missing, prev_price))
        expanded.append((pos, price))
        prev_pos, prev_price = pos, price
    for missing in range(prev_pos + 1, expected_points + 1):
        expanded.append((missing, prev_price))
    return expanded


def xml_to_rows(xml_bytes: bytes, zone_key: str) -> List[Dict]:
    """
    將 ENTSO-E XML bytes 直接解析成 Supabase row 格式，
    略過 CSV 中介步驟，減少記憶體使用。
    """
    root = ET.fromstring(xml_bytes)
    ns = root.tag.split("}")[0].strip("{")

    rows: List[Dict] = []
    seen_delivery_days = set()

    for ts in root.findall(f".//{{{ns}}}TimeSeries"):

        # 3-1 🔹 跳過 classificationSequence 特殊序列
        cls_elem = ts.find(
            f"{{{ns}}}classificationSequence_AttributeInstanceComponent.position"
        )
        if cls_elem is not None and cls_elem.text and cls_elem.text.strip():
            continue

        # 3-2 🔹 取得交割日並去重
        try:
            delivery_day = get_da_delivery_date_from_timeseries(ts)
        except Exception as e:
            print(f"  [警告] 解析交割日失敗，略過：{e}")
            continue

        if delivery_day in seen_delivery_days:
            continue
        seen_delivery_days.add(delivery_day)

        period = ts.find(f"{{{ns}}}Period")
        if period is None:
            continue

        res_elem = period.find(f"{{{ns}}}resolution")
        if res_elem is None or not res_elem.text:
            continue

        res_min = _resolution_minutes(res_elem.text.strip())
        expected_points = 1440 // res_min

        # 3-3 🔹 解析 Point
        raw_points = []
        for pt in period.findall(f"{{{ns}}}Point"):
            pos_e = pt.find(f"{{{ns}}}position")
            prc_e = pt.find(f"{{{ns}}}price.amount")
            if pos_e is None or prc_e is None:
                continue
            if not pos_e.text or not prc_e.text:
                continue
            raw_points.append((int(pos_e.text.strip()), float(prc_e.text.strip())))

        if not raw_points:
            continue

        expanded = _expand_points_with_fill(raw_points, expected_points)

        for pos, price in expanded:
            rows.append({
                "zone_key": zone_key,
                "delivery_date": delivery_day.isoformat(),
                "mtu_position": pos,
                "resolution_minutes": res_min,
                "price_eur_mwh": round(price, 4),
            })

    return rows


CHUNK_DAYS = 90  # 每段最多抓取的天數，避免單次 XML 過大


def upload_country_range(
    client: Client,
    zone_key: str,
    start_date: date,
    end_date: date,
) -> None:
    """
    抓取指定 zone_key 在 [start_date, end_date] 的日前電價並寫入 Supabase。
    以 CHUNK_DAYS 天為單位分段，避免單次 XML 過大導致記憶體或 API 問題。
    """
    print(f"\n{'='*50}")
    print(f"[上傳] {zone_key}  {start_date} ~ {end_date}")
    print(f"{'='*50}")

    chunk_start = start_date
    total_inserted = 0

    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS - 1), end_date)
        print(f"\n  [分段] {chunk_start} ~ {chunk_end}")

        try:
            _, xml_bytes = fetch_da_price_xml_bytes(
                start_date=chunk_start,
                end_date=chunk_end,
                country_code=zone_key,
                token=ENTSOE_TOKEN,
            )

            rows = xml_to_rows(xml_bytes, zone_key)
            print(f"  [解析] 共 {len(rows)} 筆 MTU rows")

            if not rows:
                print(f"  [警告] {zone_key} {chunk_start}~{chunk_end} 無資料，略過。")
            else:
                inserted = upsert_rows(client, rows)
                log_fetch(client, zone_key, chunk_start, chunk_end, inserted)
                total_inserted += inserted
                print(f"  [完成] 本段寫入 {inserted} 筆")

        except Exception as e:
            print(f"  [錯誤] {zone_key} {chunk_start}~{chunk_end} 失敗：{e}")

        chunk_start = chunk_end + timedelta(days=1)

    print(f"\n  [{zone_key}] 全區間共寫入 {total_inserted} 筆")


# =========================== #
# 4 🔹 執行進入點
# =========================== #
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="上傳日前電價至 Supabase")
    parser.add_argument("--start", required=True, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--end",   required=True, help="結束日期 YYYY-MM-DD")
    parser.add_argument(
        "--zones",
        nargs="+",
        default=["FR", "IT-North", "IT-Centre-North", "IT-Centre-South",
                 "IT-South", "IT-Calabria", "IT-Sicily", "IT-Sardinia",
                 "CH", "ES", "PT", "NL"],
        help="要上傳的 zone_key 清單（預設全部）",
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date   = date.fromisoformat(args.end)

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    for zone in args.zones:
        if zone not in ENTSOE_EIC_BY_COUNTRY:
            print(f"[略過] {zone} 不在 EIC 對照表中")
            continue
        try:
            upload_country_range(supabase, zone, start_date, end_date)
        except Exception as e:
            print(f"[錯誤] {zone} 上傳失敗：{e}")
            continue

    print("\n[完成] 全部上傳完成")
