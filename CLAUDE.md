# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Architecture

Layered pipeline: **UI → Services → Utils → Config**

```
ENTSO-E REST API
    ↓ safe_get() with retry
fetch_da_price_xml_bytes()          # services/data_fetcher.py
    ↓ XML bytes
parse_da_xml_to_raw_csv_bytes()     # services/data_processor.py
    ↓ Raw MTU CSV (Date | MTU | Price)
convert_raw_mtu_csv_to_hourly_csv_bytes()
    ↓ Hourly CSV (Date | Hour | Price)
calculate_daily_stats()
    ↓ Daily Stats CSV + summary dict
render_fetch_da_price_page()        # ui/pages.py (Streamlit UI)
```

## Module Responsibilities

| File | Role |
|------|------|
| `app.py` | Entry point; two-level sidebar menu → routes to page renderers |
| `config/settings.py` | All constants: API token, EIC codes, country list, resolution params |
| `services/data_fetcher.py` | ENTSO-E API client — date chunking (≤100 days/call), pagination (offset=100), per-segment dedup by `(mRID, startTime)`, delivery-date filtering |
| `services/data_processor.py` | XML → Raw MTU CSV → Hourly CSV; implements ENTSO-E price-fill rule |
| `utils/timezone_helper.py` | Converts UTC `timeInterval/start` → delivery date using `Europe/Brussels` |
| `ui/pages.py` | All Streamlit page renderers |
| `ui/ui_theme.py` | Style dicts for `streamlit-option-menu` |

## Page Routing

```
Sidebar (Two-level option-menu)
├─ 資料獲取
│  ├─ 日前市場價格 → render_fetch_da_price_page()   ← fully implemented
│  └─ aFRR容量價格 → render_fetch_afrr_capacity_page()  ← stub
├─ 資料處理
│  └─ 時間序列處理 → render_data_processing_page()  ← stub
└─ 繪圖區
   └─ 電價圖表 → render_plot_page()  ← stub
```

Session state keys used by the DA price page: `da_xml_bytes`, `da_file_name`, `show_analysis`.

## Key Design Decisions

**Delivery date always uses `Europe/Brussels`** (`DA_MARKET_TIMEZONE`), even for Portugal/Spain. Using local timezones causes an off-by-one-day bug — ENTSO-E period start timestamps are in UTC and align to Brussels market hours.

**ENTSO-E price-fill rule** (`_expand_points_with_fill`): When a TimeSeries omits positions (e.g., jumps 4→6), the gap inherits the last published price. Position sequence must start at 1 and be monotonically increasing.

**Deduplication is per date-segment** (`seen_mrids_segment`): Each 100-day API chunk has its own dedup set. A second dedup pass in `parse_da_xml_to_raw_csv_bytes()` keeps only the first TimeSeries per delivery day.

**`classificationSequence_AttributeInstanceComponent.position`** elements mark non-price sequences and are skipped during XML parsing.

**XML namespace handling**: All ElementTree queries must extract and include the namespace prefix. ENTSO-E XML uses a default namespace, so bare tag names like `find("TimeSeries")` will fail — always use `find(f"{ns}TimeSeries")`.

## Configuration (`config/settings.py`)

- `DEFAULT_ENTSOE_TOKEN` — rotate here when credentials change
- `MAX_DAYS_PER_REQUEST_DA = 100` — hard ENTSO-E limit per API call
- `DA_SUPPORTED_RESOLUTION_MINUTES = [60, 30, 15]` — accepted MTU resolutions
- `DA_SKIP_UNSUPPORTED_MTU_DAYS = True` — silently skip days with unexpected resolution
- `DA_DOWNLOAD_OPTIONS` — booleans controlling which output files appear as download buttons
- `DA_SUPPORTED_COUNTRIES` — country codes shown in the DA market dropdown; subset of `ENTSOE_EIC_BY_COUNTRY`

## Output CSV Formats

| CSV | Columns |
|-----|---------|
| Raw MTU | `Date`, `Market Time Unit (MTU)`, `Day-ahead Price (EUR/MWh)` |
| Hourly | `Date`, `Hour`, `Day-ahead Price (EUR/MWh)` |
| Daily Stats | `Date`, `Daily Average Price`, `Daily Price Spread`, `Daily Volatility (SD)`, `Daily Max Price`, `Daily Min Price` |

30-min and 15-min data is averaged to hourly by grouping on `(Date, hour_bucket)`.

## Login System

`show_login_page()` exists in `app.py` but is bypassed — `main()` calls `show_main_app()` directly. Credentials are hardcoded in `config/settings.py` and are for local/demo use only.
