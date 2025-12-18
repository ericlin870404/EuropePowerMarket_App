
# 🧩 歐洲電力市場數據分析工具

**European Electricity Market Data Analysis Tool**

本工具以 **Streamlit** 開發，目標是協助能源從業人員快速取得、處理與分析 **歐洲電力市場（ENTSO-E Transparency Platform）** 的公開資料，並支援原始 XML 下載、資料補值、解析度轉換（MTU → Hourly）、及未來的視覺化功能。

---

## 🚀 功能總覽

### **1. 資料獲取（Raw Data Fetching）**

- 支援從 **ENTSO-E Transparency Platform** 下載日前市場價格（Day-Ahead Price, A44）。
- **智慧化資料抓取流程**：
    - 自動處理多天分段請求（避免 API 超時）。
    - 處理 API offset 分頁邏輯。
    - **去重機制**：依據 `mRID` 與 `startTime` 組合鍵值進行資料去重。
    - **精準交割日過濾**：透過統一的時區輔助模組，精確篩選出目標日期的 TimeSeries。

### **2. 資料處理（Data Processing）**

- 將下載的 XML 解析並產生：
    - **原始 MTU CSV**（含補值後完整 MTU 序列）。
    - **逐時 Hourly CSV**（依 60/30/15 分鐘解析度自動平均）。
- 處理 ENTSO-E 特性：
    - **自動補值**：依據 ENTSO-E 規則，自動補齊被省略的相同價格區間。
    - **序列過濾**：自動過濾非預設（classificationSequence）的資料序列。
    - **解析度相容**：支援 PT60M / PT30M / PT15M 等多種時間解析度。

### **3. 繪圖區（Plotting Area）**

（尚未實作 — 預留折線圖、堆疊圖、比較圖等快速視覺化功能）

### **4. 登入系統（User Authentication）**

- 內建簡易帳號密碼登入（本機測試用途，可擴充為資料庫 / OAuth）。

---

## 📦 專案結構

```text
歐洲電力市場分析App/
│
├─ app.py                         # 主程式入口，負責登入驗證、Session 管理與頁面路由
│
├─ config/
│   └─ settings.py                # 系統設定：API Token、EIC 對照表、市場規範參數
│
├─ services/
│   ├─ data_fetcher.py            # 服務層：與 ENTSO-E API 通訊，下載並過濾原始 XML
│   └─ data_processor.py          # 服務層：執行 XML 解析、補值運算與 CSV 轉換
│
├─ utils/
│   └─ timezone_helper.py         # 工具層：統一處理時區轉換與交割日判定邏輯
│
├─ ui/
│   ├─ pages.py                   # UI 層：定義各功能頁面的佈局與互動邏輯
│   └─ ui_theme.py                # UI 層：選單樣式與視覺主題設定
│
└─ download/                      # (Optional) 原始資料與 CSV 下載暫存區

```

---

## 🔧 核心模組與其角色

### **app.py**

- 控制登入流程，完成身份驗證後進入主應用程式。
- 管理主選單與子選單，依選擇載入不同頁面。

---

### **config/settings.py**

- 定義系統常數：API URL、ENTSO-E DocumentType、國家 EIC code、支援國家列表。
- 儲存本機測試用帳號密碼。

---

### **services/data_fetcher.py**

專責 **與 ENTSO-E API 通訊**，包含以下邏輯：

- **safe_get()**：具重試機制的 API 請求。
- **fetch_da_price_xml_bytes()**：
    - 日期分段抓取（避免範圍過大）
    - offset 分頁
    - mRID 過濾與合併
    - 根據國家時區判斷交割日並過濾
    - 產生最終 XML bytes（供下載）

---

### **services/data_processor.py**

專責 **資料解析與補值轉換**：

- **parse_da_xml_to_raw_csv_bytes()**：
    - 解析 XML → MTU CSV
    - 自動補齊 position（依 ENTSO-E 省略規則）
    - 過濾 classificationSequence ≠ 1 的 TimeSeries
- **convert_raw_mtu_csv_to_hourly_csv_bytes()**：
    - 依解析度（24/48/96 點）計算每小時平均價格
    - 產生最終 Hourly CSV

---

### **ui/pages.py**

- 組成各頁面的 Streamlit UI。
- 連動 data_fetcher 與 data_processor 完成下載與處理工作流程。

---

### **ui/ui_theme.py**

- 統一主選單與子選單的視覺風格，提升整體介面一致性。

---

## 📥 輸出檔案格式

### **1. 原始 XML**

```
EnergyPrice_DA_FR_20250101_20250131.xml

```

### **2. 原始 MTU CSV**

（已補齊省略點）

| Date | MTU | Price |
| --- | --- | --- |

### **3. Hourly CSV**

（每小時平均價格）

| Date | Hour | Price |
| --- | --- | --- |

