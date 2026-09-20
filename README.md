# 3Dollar ERP (三圓科技架構引擎) - 專案使用說明書與快速啟動指南

> [!IMPORTANT]
> **使用說明書 SSOT 定位**：
> 本文件為**「本專案如何使用與快速啟動」（How to Run & Operate）**的唯一權威來源。
> * 若要查閱系統架構規格、雙軌研發邊界與技術插槽：請參閱 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)。
> * 若要查閱當前衝刺進度、驗收紀錄與阻礙狀態：請參閱 [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md)。
> * 若要查閱智能體操作規範與分層相依性守則：請參閱 [`AGENTS.md`](file:///d:/3dollar_erp/AGENTS.md)。

---

## 一、 快速啟動 (Quick Start)

### 1. 環境需求
* **作業系統**：Windows（支援 Windows PowerShell）
* **執行環境**：Python 3.10+
* **前端與樣式**：零構建服務端渲染（Zero-Build SSR），由 CDN 自動加載 Tailwind CSS 與 HTMX 1.9，**無須安裝 Node.js、npm 或執行任何打包步驟**。
* **資料庫初始化與種子資料**：系統啟動時會**自動偵測並初始化**本地 `erp.db`（執行 `schema.sql`），若資料庫為空則自動注入展示示範資料（雙倉、3 項商品、涵蓋 DIRECT / CRM / LINE 多通路與 DRAFT / CONFIRMED / SHIPPED / COMPLETED 全生命週期之示範單據、客戶主檔、商機報價單與借貸平衡傳票），免去手動建表與填單步驟。

### 2. 啟動管理後台伺服器
於專案根目錄（`d:\3dollar_erp`）開啟 PowerShell 執行：

```powershell
python -m uvicorn src.channel_ui.web.app:app --reload --port 8000
```

伺服器啟動成功後，終端機會顯示：
`INFO: Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)`

---

## 二、 管理後台訪問入口 (Web GUI Portal)

使用瀏覽器開啟以下網址即可使用對應的管理功能：

| 功能頁面 | 瀏覽器網址 | 功能描述與重點作業 |
| :--- | :--- | :--- |
| **營運即時儀表板** | [`http://127.0.0.1:8000/`](http://127.0.0.1:8000/) | 即時展示 4 大 KPI 卡片（今日訂單、待出貨、安全存量警報、未沖銷 AR）、低存量預警清單、近期訂單列表。 |
| **訂單與出貨作業** | [`http://127.0.0.1:8000/orders`](http://127.0.0.1:8000/orders) | 管理銷售訂單（SO），支援 HTMX 無刷新「一鍵鎖庫」、「一鍵出貨」、「拆批出貨」、「開立發票」與原生 100x150mm 熱感 / 多格 A4 標籤貼紙串流下載。 |
| **多倉庫存與流水** | [`http://127.0.0.1:8000/inventory`](http://127.0.0.1:8000/inventory) | 主倉與門市倉存量對照、原子性調撥表單、Append-Only 雙記帳庫存異動流水（Stock Ledger）。 |
| **探吉 會計記帳** | [`http://127.0.0.1:8000/accounting`](http://127.0.0.1:8000/accounting) | 總分類帳試算表、多步驟損益表、應收 (AR)/應付 (AP) 4 區間帳齡分析、借貸平衡傳票登錄、款項沖銷與 Excel (.xlsx) 匯出。 |
| **哩來 CRM 商機** | [`http://127.0.0.1:8000/crm`](http://127.0.0.1:8000/crm) | 四段商機管線看板（LEAD $\rightarrow$ DISCOVERY $\rightarrow$ PROPOSAL $\rightarrow$ WON/LOST）、客戶主檔管理、多品項商業報價單產出、Word (.docx) / 原生防竄改 PDF 串流下載、贏單一鍵轉 ERP 銷售訂單。 |
| **AI 檔案自動化** | [`http://127.0.0.1:8000/ai/tools`](http://127.0.0.1:8000/ai/tools) | BOM 表 Excel 批量解析比價、原生 PDF 電子發票文字層抽取轉 AP 應付帳款、4合1全方位財務營運報表 Excel 串流下載。 |
| **API 互動規格文件** | [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs) | 檢視所有 FastAPI 路由、Swagger UI 互動式測試與資料傳輸物件（View DTO）綱要。 |


---

## 三、 核心業務操作手冊 (Operational Workflows)

### 1. 訂單履行一條龍流程 (Order Fulfillment)
進入 **「訂單與出貨作業」**（`/orders`），單據依序遵循剛性狀態機流轉：

```
[DRAFT 草稿] ──(鎖庫確認)──> [CONFIRMED 已確認] ──(一鍵/拆批出貨)──> [PARTIAL / SHIPPED] ──(開立發票)──> [COMPLETED 已完成 (四單剛性勾稽)]
```

1. **鎖庫確認（Confirm Order）**：
   * 點擊單據列上的 **「鎖庫確認」** 按鈕。
   * **系統行為**：透過 HTMX 發送請求，底層於指定倉庫建立虛擬庫存鎖（`stock_locks`），鎖定購買數量，可用庫存相應扣減，畫面狀態即時變更為 `CONFIRMED`。
2. **一鍵出貨扣庫（One-Click Ship）**：
   * 點擊單據列上的 **「一鍵出貨 (扣庫)」** 按鈕。
   * **系統行為**：釋放虛擬鎖並於雙記帳流水（`stock_ledger`）寫入出庫異動（`ReferenceType.SALE`），生成出貨單（`DO`）與託運號碼，解鎖 **「🏷️ 標籤」** 下載按鈕，並於發票已開時晉級為 `COMPLETED`。
3. **開立台灣電子發票（Issue MIG 3.2.1 Invoice）**：
   * 點擊單據列上的 **「開立發票」** 按鈕。
   * **系統行為**：依財政部 MIG 3.2.1 標準生成發票字軌（如 `AB-12345678`）、4 位隨機碼與左右雙 QR Code，並同步建立 1:1 應收帳款（`AR`），解鎖 **「🧾 發票」** 下載按鈕，若已出貨則晉級為 `COMPLETED`。
4. **列印與下載原生 PDF**：
   * 點擊 **「🏷️ 標籤」**：瀏覽器新分頁直接串流開啟標準 100x150mm 物流託運標籤 PDF（含條碼文字與揀貨覆核簽名欄位）。
   * 點擊 **「🧾 發票」**：瀏覽器新分頁直接串流開啟標準 5.7cm 熱感紙證明聯 PDF（含左右雙 QR Code、字軌、消費明細）。
   * > [!NOTE]
   * > **青春版規格說明**：當前版本專注驗證紙張版型尺寸與文字層串流，條碼與 QR Code 處採用法規佔位方框與字軌文字（`||| AB-12345678 |||`、`[QR-L]`、`* TRK-XXXX *`），未引入外部圖像生成套件。

### 2. 倉庫調撥作業 (Inter-Warehouse Transfer)
進入 **「多倉庫存與流水」**（`/inventory`）：
1. 於頂部「倉庫調撥作業」卡片中，選擇 **來源倉庫**（如主倉 `WH-MAIN`）、**目的倉庫**（如門市倉 `WH-STORE`）、輸入 **品號 (SKU)** 與 **調撥數量**。
2. 點擊 **「執行調撥」**：
   * **防負庫存檢驗**：系統自動校驗來源倉之可用餘額（`Available = Physical - Locked`）。若可用量不足，系統會觸發 HTTP 400 攔截。
   * **雙層防護 HTMX 警示**：前端配置白名單機制，將 4xx 業務防呆透過 OOB（Out-Of-Band）即時彈出紅底錯誤橫幅（`#toast-container`），並以 `HX-Reswap: none` 嚴密保護現有庫存表格不被破壞；若遇 5xx 伺服器崩潰則強制拒絕抽換，杜絕醜陋的程式碼報錯破壞畫面。
   * **雙向記帳**：檢驗通過後，原子性在來源倉寫入負向流水（`-qty`），在目的倉寫入正向流水（`+qty`），庫存表格與異動日誌透過 HTMX 即時刷新。

### 3. 探吉 會計記帳與財務報表 (TanGii Accounting & Financial Reporting)
進入 **「探吉 會計記帳」**（`/accounting`）：
1. **事件自動入帳機制 (Event-Driven Auto Journaling)**：
   * 採購入庫（GRN）完成時：自動建立 1:1 應付帳款（AP），並拋轉分錄 `借：1201 存貨 / 貸：2144 應付帳款`。
   * 訂單出貨（DO）扣庫時：自動依庫存流水移動平均成本認列 `借：5111 銷貨成本 / 貸：1201 存貨`。
   * 電子發票（INV）開立時：自動依 MIG 3.2.1 稅率分離認列 `借：1144 應收帳款 / 貸：4111 銷貨收入 / 貸：2201 銷項稅額`。
2. **會計總分類帳試算表 (Trial Balance)**：
   * 點選「⚖️ 會計試算表」頁籤，即時檢視所有會計科目借方與貸方累計發生額與期末餘額。
   * 底端合計欄強制遵循商業會計借貸恆等式（$\sum \text{Debit} = \sum \text{Credit}$），並提供「✓ 借貸嚴格平衡」即時檢驗徽章。
   * 點擊 **「匯出 Excel 試算表」**：原生串流產出專業排版之 `.xlsx` 檔案（含雙線會計底線、格式化貨幣樣式）。
3. **即時損益表 (Income Statement)**：
   * 點選「📑 即時損益表」頁籤，直觀呈現多步驟式損益結構：`營業收入 - 營業成本 = 營業毛利 - 營業費用 = 本期營業淨利`，並即時計算毛利率與淨利率。
   * 點擊 **「匯出 Excel 損益表」**：原生串流產出多步驟損益結構之 `.xlsx` 財務報告。
4. **應收 (AR) 與應付 (AP) 帳齡矩陣 (Aging Analysis)**：
   * 點選「⏳ 應收/應付帳齡分析」頁籤，即時檢視未到期 (Current)、1-30天、31-60天、60+天 4 大區間之款項分佈與逾期警報。
   * 點擊 **「⚡ 沖銷收款」** 或 **「⚡ 沖銷付款」**：透過 HTMX 發送請求，底層自動更新單據未付餘額為結清，並同步生成借貸平衡的現金收付沖銷傳票（`借：現金 / 貸：應收帳款` 或 `借：應付帳款 / 貸：現金`）。
5. **手動登錄平衡傳票 (Manual Journal Voucher Entry)**：
   * 點選「📖 借貸日記帳簿」頁籤，提供手動傳票輸入表單。
   * 若借方總額不等於貸方總額（例如借 10,000 / 貸 9,000），系統立即攔截並彈出紅底錯誤通知橫幅，嚴格禁止失衡傳票寫入總帳。

### 4. 哩來 CRM 前段商機與文件套印中心 (LiLai CRM Workflows)
進入 **「哩來 CRM 商機」**（`/crm`）：
1. **建立客戶主檔與統編格式防呆**：
   * **動作 (Action)**：點擊頂部 **「👤 新增客戶」** 按鈕，於彈窗輸入公司名稱（如 `宏達數位科技有限公司`）、8 位數統一編號（如 `24567890`）與聯絡人。若故意輸入非 8 碼數字（如 `1234`）並提交。
   * **預期成果 (Expected Outcome)**：若統編格式不符，系統立即以 OOB 紅底橫幅提示 `⚠️ 執行失敗: 統一編號格式錯誤：必須為 8 位純數字`；輸入正確則成功建檔，客戶清冊即時更新。
2. **四段商機管線推進 (LEAD ➜ DISCOVERY ➜ PROPOSAL ➜ WON / LOST)**：
   * **動作 (Action)**：於看板點擊 **「✨ 建立新商機」**，選取目標客戶並輸入案名；在卡片上依序點擊 **「進展洽談 ➜」** 與 **「進展報價 ➜」**。
   * **預期成果 (Expected Outcome)**：商機卡片即時於對應欄位間平滑推進，狀態徽章與階段即時更新。
3. **商業報價單試算與 Word (.docx) / PDF 套印下載**：
   * **動作 (Action)**：於商機卡片點擊 **「＋ 報價單」**，選取商品規格、輸入採購數量與報價單價，點擊「產出報價單」；產出後分別點擊 **「📥 DOCX」** 與 **「📑 預覽 PDF」**。
   * **預期成果 (Expected Outcome)**：系統依多品項自動試算未稅合計、5% 營業稅與含稅總計，並將商機自動推進至 `PROPOSAL`；點擊下載可取得專業排版之 Word 報價草稿 `.docx` 檔案，以及直接於瀏覽器預覽含防竄改文字層與簽署蓋章欄之標準 A4 報價單 `.pdf`。
4. **贏單 (WON) 一鍵穿透轉 ERP 銷售訂單 (SO)**：
   * **動作 (Action)**：於報價階段之商機卡片點擊 **「⚡ 贏單轉 ERP」**。
   * **預期成果 (Expected Outcome)**：系統透過原子性事務調用核心 `OrderService`，自動生成 CRM 通路之 `DRAFT` 銷售訂單（`SO-XXXX`），商機卡片即時移入「結案」欄位並標記為 `WON`，顯示綠色 `SO-XXXX ➜` 訂單標籤，點擊可直接跳轉至 `/orders` 進行後續鎖庫、出貨與開立發票作業。

### 5. AI 檔案自動化與報表中心 (AI & File Automation Workflows)
進入 **「AI 檔案自動化」**（`/ai/tools`）：
1. **BOM 表 Excel 批量解析與多供應商歷史比價**：
   * **動作 (Action)**：點擊頁籤「📑 BOM 物料比價 (Excel)」，點擊「下載 BOM 匯入範本 (.xlsx)」取得測試範本，並將其上傳點擊「開始智慧比價」。
   * **預期成果 (Expected Outcome)**：系統透過 `openpyxl` 解析各零件數量與規格，跨表檢索 ERP 歷史採購單資料庫，無刷新呈現各供應商報價、綠色高亮標示最低價推薦，並試算整體潛在節省金額。
2. **原生 PDF 電子發票文字層抽取與一鍵轉應付帳款 (AP)**：
   * **動作 (Action)**：點擊頁籤「🧾 原生發票抽取 (PDF)」，點擊「下載示範發票 (.pdf)」取得標準台灣電子發票樣張，上傳並點擊「抽取發票資料」；預覽確認後點擊「✓ 確認無誤，建立應付帳款 (AP)」。
   * **預期成果 (Expected Outcome)**：系統透過 `PyMuPDF (fitz)` 抽取發票字軌號碼、統編、開立日期與金額明細，自動執行 $Total = Sales + Tax$ 數學勾稽；點擊確認後自動拋轉於探吉會計建立 `accounts_payable` 應付單據，並同步登錄借貸平衡傳票（`借：1201 存貨 / 貸：2144 應付帳款`）。
3. **全方位財務與營運整合報表串流匯出**：
   * **動作 (Action)**：點擊頁籤「📊 財務營運報表中心」，點擊「匯出全套財務營運報表 (.xlsx)」。
   * **預期成果 (Expected Outcome)**：系統透過 `xlsxwriter` 高速串流產出包含「損益表」、「會計試算表」、「帳齡矩陣」、「雙倉庫存盤點底冊」4 合 1 之高階主管財務活頁簿，格式自帶貨幣排版與雙線會計底線。

---

## 四、 自動化測試與架構驗收 (Testing & Verification)

專案內建完整的自動化單元測試、整合測試、Playwright 瀏覽器測試與 AST 相依性架構檢查器。

### 1. 執行全套測試 (91 項測試案例)
在 PowerShell 終端機執行：

```powershell
python -m pytest
```

* **預期成果**：全部 91 項測試案例執行通過（`91 passed`），涵蓋：
  * **Day 1**: 資料庫模型與邊界測試
  * **Day 2**: 雙倉庫存流水、採購移動平均成本、訂單出貨、MIG 3.2.1 電子發票與四單勾稽測試
  * **Day 3**: 探吉 (TanGii) 會計借貸平衡、EAS 科目表、ERP 事件自動入帳、AR/AP 帳齡矩陣、款項沖銷、xlsxwriter 試算表/損益表匯出
  * **Day 4**: 哩來 (LiLai) CRM 客戶主檔與統編校驗、四段商機管線推進、python-docx / PyMuPDF 報價單套印、贏單一鍵轉 ERP 銷售訂單與 `/crm` Web 看板切片測試
  * **Day 5**: LINE Bot Webhook HMAC 簽名校驗、Stateless Token v3 換發、Flex 型錄卡片與離線仿真測試
  * **Day 6**: AI Wrapper 外圍增強層：BOM 表 Excel 解析比價 (`openpyxl`)、原生 PDF 電子發票文字層抽取 (`fitz`)、4合1財務活頁簿匯出 (`xlsxwriter`) 與 `/ai/tools` Web GUI 垂直切片整合測試
  * **Day 7**: 全鏈路端到端整合測試 (`tests/test_full_lifecycle_e2e.py` 覆蓋 B2B、B2C LINE 下單出貨、AI 檔案與會計 4-Way Match) 與 Playwright 真實 Chromium 瀏覽器端到端驗收 (`tests/test_playwright_day7_e2e.py`)

### 2. 執行單獨架構邊界檢查 (Architecture Fitness Function)
確保系統嚴格遵守由外向內的單向相依性，杜絕底層反向引用外圍：

```powershell
python tools/check_boundaries.py
```

* **驗證結果**：輸出 `✅ All architecture boundary checks passed! No layer violations found.`。

---

## 五、 產品生態與四層架構拆解 (Architecture Overview)

本專案複製三圓科技（藍圖思維）產品體系，以中小企業進銷存為核心基石，層級拆分如下：

```
┌────────────────────────────────────────────────────────┐
│ Layer 4: AI Wrapper & Native File Engine (外圍增強層)   │
│ • BOM 表比價 Excel 解析 / 原生 PDF 發票文字層抽取        │
├────────────────────────────────────────────────────────┤
│ Layer 3: Channel & UI (外圍通路與介面層)               │
│ • 內部管理 Web GUI (FastAPI + HTMX + Tailwind CDN)     │
│ • 外部客戶 LINE Bot 通路 (Flex Message 下單與查單)      │
├────────────────────────────────────────────────────────┤
│ Layer 2: Extended Core (次核心層: CRM & Accounting)    │
│ • 前段業務：哩來 CRM (商機管線、報價單套印)             │
│ • 後段會計：探吉 記帳系統 (借貸傳票、帳齡、財務報表)    │
├────────────────────────────────────────────────────────┤
│ Layer 1: Core Engine (核心引擎層: Dinkoko ERP)         │
│ • 多倉庫存流水 (Stock Ledger) / 虛擬鎖庫 (Stock Locks) │
│ • 訂單 (SO) 1:1 出貨 (DO) 1:1 發票 (INV) 1:1 帳款 (AR)  │
└────────────────────────────────────────────────────────┘
```

---

## 六、 5 分鐘全鏈路端到端示範演練腳本 (5-Minute End-to-End Demo Script)

本腳本遵循 `AGENTS.md` 規範之 **「動作 (Action) $\rightarrow$ 預期成果 (Expected Outcome)」** 標準結構，適合主管審查或新進人員於 5 分鐘內完整體驗 3Dollar ERP 之四層架構與全鏈路閉環運作。

### 步驟 1：哩來 CRM 商機建立與文件套印 (Lead to Quote)
* **動作 (Action)**：開啟瀏覽器前往 [`http://127.0.0.1:8000/crm`](http://127.0.0.1:8000/crm)，點擊「✨ 建立新商機」，選擇客戶「宏達數位科技有限公司」、輸入商機名稱「企業伺服器汰換專案」，在卡片上點擊「＋ 報價單」，選取商品 `SKU-IPHONE15-128`、數量 `2`、單價 `28,000` 並點擊「產出報價單」，隨後點擊卡片上之「📑 預覽 PDF」。
* **預期成果 (Expected Outcome)**：商機卡片自動推進至「提案報價 (PROPOSAL)」欄位，顯示未稅 `56,000` 元、稅額 `2,800` 元與含稅 `58,800` 元；瀏覽器新分頁即時開啟由 `fitz` 原生產生之 A4 商業報價單 PDF。

### 步驟 2：贏單轉換與訂單履行 (Won Deal to Fulfillment)
* **動作 (Action)**：在該商機卡片上點擊「⚡ 贏單轉 ERP」；跳轉至 [`http://127.0.0.1:8000/orders`](http://127.0.0.1:8000/orders) 找到新建立之訂單，依序點擊「鎖庫確認」、「一鍵出貨 (扣庫)」與「開立發票」，最後點擊「🏷️ 標籤」與「🧾 發票」。
* **預期成果 (Expected Outcome)**：CRM 商機轉為 `WON` 並關聯生成銷售訂單；訂單狀態平滑晉級 `DRAFT` $\rightarrow$ `CONFIRMED` $\rightarrow$ `SHIPPED` $\rightarrow$ `COMPLETED`；分頁即時串流產出 100x150mm 物流託運標籤與 MIG 3.2.1 電子發票證明聯 PDF。

### 步驟 3：探吉會計事件自動入帳與試算平衡 (Accounting & Trial Balance)
* **動作 (Action)**：前往 [`http://127.0.0.1:8000/accounting?tab=trial_balance`](http://127.0.0.1:8000/accounting?tab=trial_balance) 查看試算表，再切換至「📑 即時損益表」與「⏳ 應收/應付帳齡分析」。
* **預期成果 (Expected Outcome)**：剛才訂單的出貨（認列銷貨成本）與開票（認列銷貨收入與銷項稅額）已自動入帳，試算表底部綠色徽章標記「✓ 借貸嚴格平衡」；損益表即時呈現營業毛利；帳齡分析出現該筆發票之未結應收帳款（AR）。

### 步驟 4：AI 智慧 BOM 物料比價 (AI BOM Pricing Engine)
* **動作 (Action)**：前往 [`http://127.0.0.1:8000/ai/tools?tab=bom`](http://127.0.0.1:8000/ai/tools?tab=bom)，點擊「下載 BOM 匯入範本 (.xlsx)」，接著將下載之檔案上傳並點擊「開始智慧比價」。
* **預期成果 (Expected Outcome)**：系統透過 `openpyxl` 批量解析零件料號，跨表比對 ERP 採購單歷史價格，即時顯示供應商比價矩陣、綠色推薦最低價廠商，並試算整體潛在節省金額。

### 步驟 5：LINE Bot 智慧通路體驗 (LINE Bot Channel)
* **動作 (Action)**：以真實手機開啟 LINE 加入官方帳號好友（或於離線環境執行 `python -m pytest tests/test_line_bot_e2e.py`），點擊 Rich Menu「📦 熱銷商品」，在彈出的 Flex 型錄卡片點擊「立即購買」，隨後輸入「查單 {剛收到的訂單號}」。
* **預期成果 (Expected Outcome)**：LINE 聊天室即時收到美觀之商品 Flex 卡片，點擊購買後系統自動穿透 ERP 寫入 `channel=LINE` 訂單並鎖定庫存，發送訂單成立收據；輸入查單即時回覆出貨狀態、物流追蹤碼與發票號碼。

