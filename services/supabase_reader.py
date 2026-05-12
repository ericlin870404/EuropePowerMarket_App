# services/supabase_reader.py

"""
📌 整體流程：
1. 建立 Supabase 連線 (從 st.secrets 讀取憑證)
2. 定義 fetch_daily_avg_prices()：
   2-1. 呼叫 Supabase RPC 函式取得日均電價
   2-2. 轉換為 DataFrame 並確保欄位型別正確
3. 定義 fetch_negative_price_stats()：
   3-1. 從 da_prices 取得指定區間的每筆 MTU 電價
   3-2. 計算負電價天數與負電價小時數並回傳
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from supabase import Client, create_client


# =========================== #
# 1 🔹 建立 Supabase 連線
# =========================== #
@st.cache_resource
def _get_client() -> Client:
    """
    建立並快取 Supabase Client（整個 session 只建立一次）。
    憑證從 .streamlit/secrets.toml 讀取。
    """
    return create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["service_key"],
    )


# =========================== #
# 2 🔹 定義資料查詢函式
# =========================== #
@st.cache_data(ttl=3600)
def fetch_daily_avg_prices(
    zones: tuple[str, ...],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    📌 整體流程：
    1. 呼叫 Supabase RPC get_daily_avg_prices 取得伺服器端聚合後的日均電價
    2. 轉換為 DataFrame，確保欄位型別正確後回傳

    參數：
    - zones：zone_key 的 tuple（需為 tuple 才能被 @st.cache_data 快取）
    - start_date / end_date：'YYYY-MM-DD' 字串

    回傳欄位：zone_key, delivery_date, avg_price, max_price, min_price, spread, volatility
    """
    # 2-1 🔹 呼叫 Supabase RPC
    client = _get_client()
    result = client.rpc(
        "get_daily_avg_prices",
        {
            "p_zones": list(zones),
            "p_start": start_date,
            "p_end": end_date,
        },
    ).execute()

    if not result.data:
        return pd.DataFrame()

    # 2-2 🔹 轉換型別
    df = pd.DataFrame(result.data)
    df["delivery_date"] = pd.to_datetime(df["delivery_date"])
    for col in ["avg_price", "max_price", "min_price", "spread", "volatility"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# =========================== #
# 3 🔹 定義負電價統計查詢函式
# =========================== #
@st.cache_data(ttl=3600)
def fetch_negative_price_stats(
    zone: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """
    📌 整體流程：
    1. 從 da_prices 取得指定 zone 與日期區間的所有 MTU 電價紀錄
    2. 計算負電價天數（當天任一 MTU < 0 即計次）
    3. 計算負電價小時數（該小時內 4 個 MTU 中有任一 < 0 即計次，以 PT15M 為基準）
    4. 回傳每日彙總 DataFrame

    回傳欄位：
      delivery_date (date), neg_day (bool), neg_hours (int, 0–24)
    """
    # 3-1 🔹 從 Supabase 分頁拉取所有 MTU 資料（預設上限 1000 筆/頁）
    client = _get_client()
    PAGE_SIZE = 1000
    all_rows: list[dict] = []
    offset = 0
    while True:
        result = (
            client.table("da_prices")
            .select("delivery_date, mtu_position, resolution_minutes, price_eur_mwh")
            .eq("zone_key", zone)
            .gte("delivery_date", start_date)
            .lte("delivery_date", end_date)
            .order("delivery_date")
            .order("mtu_position")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = result.data or []
        all_rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    if not all_rows:
        return pd.DataFrame(columns=["delivery_date", "neg_day", "neg_hours"])

    # 3-2 🔹 建立 DataFrame 並確保型別
    df = pd.DataFrame(all_rows)
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.date
    df["mtu_position"]  = pd.to_numeric(df["mtu_position"],  errors="coerce")
    df["price_eur_mwh"] = pd.to_numeric(df["price_eur_mwh"], errors="coerce")
    df["is_negative"]   = df["price_eur_mwh"] < 0

    # 3-3 🔹 依每天實際筆數決定每組大小，再將 position 排名轉成小時 slot
    # 先去重（同一天同一 position 只保留一筆），避免重複資料影響 group_size 計算
    df = df.drop_duplicates(subset=["delivery_date", "mtu_position"])
    df = df.sort_values(["delivery_date", "mtu_position"]).reset_index(drop=True)

    # 每天筆數 / 24 = 每小時幾筆（96→4, 48→2, 24→1）
    # 用 map 確保 group_size 對應正確，sort 後再 transform
    day_group_size = (
        df.groupby("delivery_date")["mtu_position"]
        .count()
        .apply(lambda n: max(1, round(n / 24)))
    )
    df["rank_in_day"] = df.groupby("delivery_date").cumcount()  # 0-based
    df["group_size"]  = df["delivery_date"].map(day_group_size)
    df["hour"]        = df["rank_in_day"] // df["group_size"]

    # 3-4 🔹 小時層級：該小時內有任一 MTU < 0 → 計為負電價小時
    hourly = (
        df.groupby(["delivery_date", "hour"], as_index=False)["is_negative"]
        .any()
        .rename(columns={"is_negative": "hour_neg"})
    )

    # 3-5 🔹 日層級彙總
    daily_neg_hours = (
        hourly.groupby("delivery_date", as_index=False)["hour_neg"]
        .sum()
        .rename(columns={"hour_neg": "neg_hours"})
    )
    daily_neg_day = (
        df.groupby("delivery_date", as_index=False)["is_negative"]
        .any()
        .rename(columns={"is_negative": "neg_day"})
    )

    result_df = daily_neg_day.merge(daily_neg_hours, on="delivery_date", how="left")
    result_df["neg_hours"] = result_df["neg_hours"].fillna(0).astype(int)
    result_df = result_df.sort_values("delivery_date").reset_index(drop=True)

    return result_df
