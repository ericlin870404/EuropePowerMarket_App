import pandas as pd
import pytz

def convert_to_local(dt, tz="Europe/Paris"):
    tz_local = pytz.timezone(tz)
    return pd.Timestamp(dt).tz_convert(tz_local)
