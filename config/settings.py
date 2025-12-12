# config/settings.py
from typing import Dict

# 應用程式標題
APP_TITLE: str = "歐洲電力市場數據分析工具"

# ENTSO-E API 相關設定
ENTSOE_API_BASE_URL: str = "https://web-api.tp.entsoe.eu/api"
# A44 = Day-ahead prices（日前電價，依 ENTSO-E 文件）
ENTSOE_DOC_TYPE_DA_PRICE: str = "A44"

# 一次呼叫最多涵蓋的天數（避免日期區間過大）
MAX_DAYS_PER_REQUEST_DA: int = 100

# 之後建議改用 st.secrets["ENTSOE_API_TOKEN"]，這裡只是預設值或占位
DEFAULT_ENTSOE_TOKEN: str = "adb582cd-6b2d-482e-84fd-1d9b2e72c8dd"

# UI 下拉選單使用的國家／區域設定
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

# ENTSO-E 定義的 bidding zone / control area EIC codes
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

# ===== Day-Ahead (DA) Market - Time Resolution Settings =====
# 目前工具在「原始 MTU CSV → 每小時 CSV」階段可接受的時間解析度（分鐘）
DA_SUPPORTED_RESOLUTION_MINUTES = [60, 30, 15]

# 是否在遇到「非支援 MTU 筆數」的日期時，直接跳過該日（True）或拋錯（False）
DA_SKIP_UNSUPPORTED_MTU_DAYS = True

# 是否仍保留「最後一個週日」的粗略 DST 跳過邏輯（可選）
# DA_SKIP_LAST_SUNDAY_DSTS = False

DA_MARKET_TIMEZONE = "Europe/Brussels"

# === 簡易帳號設定（純本機用，之後可改用環境變數／資料庫） ===
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