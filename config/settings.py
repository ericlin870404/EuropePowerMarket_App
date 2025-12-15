# config/settings.py
from typing import Dict

# 應用程式標題
APP_TITLE: str = "歐洲電力市場數據分析工具"

##################################
# ======== API 相關設定 ========
##################################

# ----- Overall ----- #
ENTSOE_API_BASE_URL: str = "https://web-api.tp.entsoe.eu/api" 
DEFAULT_ENTSOE_TOKEN: str = "adb582cd-6b2d-482e-84fd-1d9b2e72c8dd" # API token，之後建議改用 st.secrets["ENTSOE_API_TOKEN"]

# ----- 電能現貨市場(日前市場) ----- #
ENTSOE_DOC_TYPE_DA_PRICE: str = "A44"              # A44 = Day-ahead prices
MAX_DAYS_PER_REQUEST_DA: int = 100                 # 一次呼叫最多涵蓋的天數（避免日期區間過大）
DA_SUPPORTED_RESOLUTION_MINUTES = [60, 30, 15]     # 為「原始 MTU CSV → 每小時 CSV」階段可接受的時間解析度（分鐘）
DA_SKIP_UNSUPPORTED_MTU_DAYS = True                # 是否在遇到「非支援 MTU 筆數」的日期時，直接跳過該日（True）或拋錯（False）
DA_MARKET_TIMEZONE = "Europe/Brussels"             # 時區設定

##################################
# ========== 國家設定 ===========
##################################

# ----- Overall ----- #
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

# ----- 電能現貨市場(日前市場) ----- #
DA_SUPPORTED_COUNTRIES = ["FR", "NL", "ES", "PT", "IT-North", "IT-South", "BE", "CZ", "CH"]  


##################################
# ========== 帳號設定 ===========
##################################

USERS = {
    # 你自己（管理員）
    "eric": {
        "password": "8888",  # 建議先放一個暫時的測試密碼
        "role": "admin",
        "display_name": "Eric",
    },
    # 可以再加其他使用者（一般使用者）
    "alice": {
        "password": "alice123",
        "role": "user",
        "display_name": "Alice",
    },
}