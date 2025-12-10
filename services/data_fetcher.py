import requests
import pandas as pd
import os
from config.settings import API_KEY, API_BASE_URL
from utils.file_manager import save_to_excel

def fetch_raw_data(start, end, country):
    params = {
        "securityToken": API_KEY,
        "documentType": "A44",
        "outBiddingZone_Domain": f"10Y{country}------A",
        "periodStart": start.strftime("%Y%m%d0000"),
        "periodEnd": end.strftime("%Y%m%d2300"),
    }

    r = requests.get(API_BASE_URL, params=params)

    # TODO: XML parse → DataFrame
    df = pd.DataFrame()

    save_to_excel(df, f"raw_{country}_{start}_{end}.xlsx")
