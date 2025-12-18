"""
📌 整體流程：
1. 定義應用程式基礎資訊 (標題)
2. 定義 API 連線設定
   2-1. 基礎 URL 與 Token
   2-2. 日前市場 (DA) 專屬參數 (DocType, 天數限制, 解析度, 下載功能開關)
3. 定義國家與區域設定
   3-1. 支援國家列表 (中文名稱)
   3-2. ENTSO-E EIC 代碼對照表
   3-3. DA 市場支援國家清單
4. 定義使用者帳號 (登入權限)
"""

from typing import Dict

# =========================== #
# 1 🔹 定義應用程式基礎資訊
# =========================== #
APP_TITLE: str = "歐洲電力市場數據分析工具"

# =========================== #
# 2 🔹 定義 API 連線設定
# =========================== #

# 2-1 🔹 基礎 URL 與 Token
ENTSOE_API_BASE_URL: str = "https://web-api.tp.entsoe.eu/api" 
DEFAULT_ENTSOE_TOKEN: str = "adb582cd-6b2d-482e-84fd-1d9b2e72c8dd"

# 2-2 🔹 日前市場 (DA) 專屬參數
ENTSOE_DOC_TYPE_DA_PRICE: str = "A44"              # A44 = Day-ahead prices
MAX_DAYS_PER_REQUEST_DA: int = 100                 # 一次呼叫最多涵蓋的天數
DA_SUPPORTED_RESOLUTION_MINUTES = [60, 30, 15]     # 支援的時間解析度
DA_SKIP_UNSUPPORTED_MTU_DAYS = True                # 是否跳過不支援的解析度日期
DA_MARKET_TIMEZONE = "Europe/Brussels"             # ENTSO-E 市場時區
# 下載功能開關 (DA_DOWNLOAD_OPTIONS)
DA_DOWNLOAD_OPTIONS: Dict[str, bool] = {
    "xml_original": False,     # 開關：原始 XML
    "csv_raw_mtu": True,      # 開關：原始 MTU CSV
    "csv_hourly": True,       # 開關：每小時 CSV
}

# =========================== #
# 3 🔹 定義國家與區域設定
# =========================== #

# 3-1 🔹 支援國家列表 (中文名稱)
SUPPORTED_COUNTRIES: Dict[str, str] = {
    "FR": "法國",
    "NL": "荷蘭",
    "ES": "西班牙",
    "PT": "葡萄牙",
    "IT-North": "義大利（北部）",
    "IT-South": "義大利（南部）",
    "BE": "比利時",
    "GB": "英國",
    "CZ": "捷克",
    "CH": "瑞士",
}

# 3-2 🔹 ENTSO-E EIC 代碼對照表
ENTSOE_EIC_BY_COUNTRY: Dict[str, str] = {
    "ES": "10YES-REE------0",
    "PT": "10YPT-REN------W",
    "IT-North": "10Y1001A1001A73I",
    "IT-South": "10Y1001A1001A788",
    "NL": "10YNL----------L",
    "FR": "10YFR-RTE------C",
    "BE": "10YBE----------2",
    "GB": "10YGB----------A",
    "CZ": "10YCZ-CEPS-----N",
    "CH": "10YCH-SWISSGRIDZ",
}

# 3-3 🔹 DA 市場支援國家清單
DA_SUPPORTED_COUNTRIES = ["FR", "NL", "ES", "PT", "IT-North", "IT-South", "BE", "CZ", "CH"]  

# =========================== #
# 4 🔹 定義使用者帳號
# =========================== #
USERS = {
    "eric": {
        "password": "8888",
        "role": "admin",
        "display_name": "Eric",
    },
    "alice": {
        "password": "alice123",
        "role": "user",
        "display_name": "Alice",
    },
}