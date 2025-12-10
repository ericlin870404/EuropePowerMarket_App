import os
import pandas as pd

DOWNLOAD_DIR = "download"

def save_to_excel(df, filename):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    df.to_excel(os.path.join(DOWNLOAD_DIR, filename), index=False)

def save_csv(df, filename):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    df.to_csv(os.path.join(DOWNLOAD_DIR, filename), index=False)
