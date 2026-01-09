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

from typing import Dict, List


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
    "BE": "比利時",
    "GB": "英國",
    "CZ": "捷克",
    "CH": "瑞士",
    # 義大利區域 (依地理位置由北至南排序)
    "IT-North": "義大利（北部）",
    "IT-Centre-North": "義大利（中北部）",
    "IT-Centre-South": "義大利（中南部）",
    "IT-South": "義大利（南部）",
    "IT-Calabria": "義大利（卡拉布里亞）",
    "IT-Sicily": "義大利（西西里島）",
    "IT-Sardinia": "義大利（薩丁尼亞島）",
}

# 3-2 🔹 ENTSO-E EIC 代碼對照表
ENTSOE_EIC_BY_COUNTRY: Dict[str, str] = {
    "ES": "10YES-REE------0",
    "PT": "10YPT-REN------W",
    "NL": "10YNL----------L",
    "FR": "10YFR-RTE------C",
    "BE": "10YBE----------2",
    "GB": "10YGB----------A",
    "CZ": "10YCZ-CEPS-----N",
    "CH": "10YCH-SWISSGRIDZ",
    # 義大利區域 EIC Codes
    "IT-North": "10Y1001A1001A73I",
    "IT-Centre-North": "10Y1001A1001A70O",
    "IT-Centre-South": "10Y1001A1001A71M",
    "IT-South": "10Y1001A1001A788",
    "IT-Calabria": "10Y1001C--00096J",
    "IT-Sicily": "10Y1001A1001A75E",
    "IT-Sardinia": "10Y1001A1001A74G",
}

# 3-3 🔹 DA 市場支援國家清單
# 注意：確保此處的 Key 與上述字典 Key 完全一致
DA_SUPPORTED_COUNTRIES: List[str] = [
    "FR", "NL", "ES", "PT", "BE", "CZ", "CH",
    "IT-North", "IT-Centre-North", "IT-Centre-South", 
    "IT-South", "IT-Calabria", "IT-Sicily", "IT-Sardinia"
]
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