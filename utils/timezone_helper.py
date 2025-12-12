from __future__ import annotations

from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET

from config.settings import DA_MARKET_TIMEZONE


def get_da_delivery_date_from_timeseries(ts: ET.Element) -> date:
    """
    取得 DA (Day-Ahead) 價格 TimeSeries 的交割日。

    規則：
    - 以 DA 市場日界線時區（DA_MARKET_TIMEZONE，例如 Europe/Brussels）判定交割日
    - 避免使用各國本地時區導致（尤其 Portugal/Lisbon）Date 偏移一天
    """
    ns = ts.tag.split("}")[0].strip("{")

    start_elem = ts.find(
        f".//{{{ns}}}Period/{{{ns}}}timeInterval/{{{ns}}}start"
    )
    if start_elem is None or not start_elem.text:
        raise ValueError("TimeSeries 缺少 Period/timeInterval/start")

    utc_dt = datetime.fromisoformat(start_elem.text.replace("Z", "+00:00")).astimezone(timezone.utc)
    market_dt = utc_dt.astimezone(ZoneInfo(DA_MARKET_TIMEZONE))
    return market_dt.date()
