# services/supabase_reader.py

"""
📌 整體流程：
1. 建立 Supabase 連線 (從 st.secrets 讀取憑證)
2. 定義 fetch_daily_avg_prices()：
   2-1. 呼叫 Supabase RPC 函式取得日均電價
   2-2. 轉換為 DataFrame 並確保欄位型別正確
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
