import pandas as pd
from utils.file_manager import save_csv

def process_data(uploaded_file, resolution):
    df = pd.read_csv(uploaded_file)

    # TODO: 補值邏輯（依 resolution）
    df_filled = df.copy()

    save_csv(df_filled, "processed_output.csv")
