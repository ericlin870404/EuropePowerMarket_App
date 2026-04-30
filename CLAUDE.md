# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This app covers two European electricity markets:
- **電能現貨市場** — Currently day-ahead (DA) price data; intraday may be added later.
- **平衡服務市場** — Currently aFRR capacity market data; may expand to other balancing products.

Two goals: internal work tool for market data analysis, and a portfolio demo for job interviews.

## Running the App

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Sidebar Structure

Three top-level items (in order): **Dashboard** (default) → **資料下載** → **收益試算**. Routing logic is in `app.py`; all page renderers are in `ui/pages.py`.

## Comment Style Convention

All files use a consistent Chinese comment style. **Always follow this pattern** when writing or modifying code:

```python
# =========================== #
# N 🔹 區塊標題
# =========================== #
def some_function():
    """
    📌 整體流程：
    1. 第一步說明
    2. 第二步說明
    """
    # N-1 🔹 子步驟說明
    ...
```

- Section headers use `# =========================== #` fences with a number and 🔹
- Docstrings open with `📌 整體流程：` and a numbered list
- Inline sub-steps use `# N-M 🔹` matching the docstring numbering
- All comments in Traditional Chinese

## Data Pipeline

```
ENTSO-E REST API
    ↓ safe_get() with retry              (services/data_fetcher.py)
fetch_da_price_xml_bytes()
    ↓ XML bytes
parse_da_xml_to_raw_csv_bytes()          (services/data_processor.py)
    ↓ Raw MTU CSV
convert_raw_mtu_csv_to_hourly_csv_bytes()
    ↓ Hourly CSV
calculate_daily_stats()
    ↓ Daily Stats CSV + summary dict
```

## Key Design Decisions

**Delivery date uses `Europe/Brussels`** for all countries — using local timezones causes an off-by-one-day bug with Portugal/Spain because ENTSO-E timestamps are UTC aligned to Brussels market hours.

**ENTSO-E price-fill rule** (`_expand_points_with_fill`): omitted positions in a TimeSeries inherit the last published price. Position sequence must start at 1 and be monotonically increasing.

**Deduplication is per date-segment**: each 100-day API chunk has its own dedup set (`seen_mrids_segment`). A second pass in `parse_da_xml_to_raw_csv_bytes()` keeps only the first TimeSeries per delivery day.

**XML namespace handling**: always extract and prefix the namespace — bare tag names like `find("TimeSeries")` will silently return nothing. Use `find(f"{ns}TimeSeries")`.

**`classificationSequence_AttributeInstanceComponent.position`** elements mark non-price sequences and must be skipped during XML parsing.
