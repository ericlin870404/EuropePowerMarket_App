# config/settings.py

APP_TITLE = "歐洲電力市場數據分析工具"

SUPPORTED_COUNTRIES = {
    "FR": "France",
    # 未來可以在這裡加 ES, PT, NL...
}

API_BASE_URL = "https://transparency.entsoe.eu/api"
API_KEY = "YOUR_API_KEY_HERE"

DEFAULT_TIMEZONE = "Europe/Paris"