# 3Dollar ERP (三元科技架構引擎) - 專案使用說明書與快速啟動指南

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
| **訂單與出貨作業** | [`http://127.0.0.1:8000/orders`](http://127.0.0.1:8000/orders) | 管理銷售訂單（SO），支援 HTMX 無刷新「一鍵鎖庫」、「一鍵出貨」、「開立發票」與原生 PDF 下載。 |
| **多倉庫存與流水** | [`http://127.0.0.1:8000/inventory`](http://127.0.0.1:8000/inventory) | 主倉與門市倉存量對照、原子性調撥表單、Append-Only 雙記帳庫存異動流水（Stock Ledger）。 |
| **API 互動規格文件** | [`http://127.0.0.1:8000/docs`](http://127.0.0.1:8000/docs) | 檢視所有 FastAPI 路由、Swagger UI 互動式測試與資料傳輸物件（View DTO）綱要。 |

---

## 三、 核心業務操作手冊 (Operational Workflows)

### 1. 訂單履行一條龍流程 (Order Fulfillment)
進入 **「訂單與出貨作業」**（`/orders`），單據依序遵循剛性狀態機流轉：

```
[DRAFT 草稿] ──(鎖庫確認)──> [CONFIRMED 已確認] ──(一鍵出貨)──> [SHIPPED 已出貨] ──(開立發票)──> [四單剛性勾稽]
```

1. **鎖庫確認（Confirm Order）**：
   * 點擊單據列上的 **「鎖庫確認」** 按鈕。
   * **系統行為**：透過 HTMX 發送請求，底層於指定倉庫建立虛擬庫存鎖（`stock_locks`），鎖定購買數量，可用庫存相應扣減，畫面狀態即時變更為 `CONFIRMED`。
2. **一鍵出貨扣庫（One-Click Ship）**：
   * 點擊單據列上的 **「一鍵出貨 (扣庫)」** 按鈕。
   * **系統行為**：釋放虛擬鎖並於雙記帳流水（`stock_ledger`）寫入出庫異動（`ReferenceType.SALE`），生成出貨單（`DO`）與託運號碼，並解鎖 **「🏷️ 標籤」** 下載按鈕。
3. **開立台灣電子發票（Issue MIG 3.2.1 Invoice）**：
   * 點擊單據列上的 **「開立發票」** 按鈕。
   * **系統行為**：依財政部 MIG 3.2.1 標準生成發票字軌（如 `AB-12345678`）、4 位隨機碼與左右雙 QR Code，並同步建立 1:1 應收帳款（`AR`），解鎖 **「🧾 發票」** 下載按鈕。
4. **列印與下載原生 PDF**：
   * 點擊 **「🏷️ 標籤」**：瀏覽器新分頁直接串流開啟標準 100x150mm 物流託運標籤 PDF（含條碼文字與揀貨覆核簽名欄位）。
   * 點擊 **「🧾 發票」**：瀏覽器新分頁直接串流開啟標準 5.7cm 熱感紙證明聯 PDF（含左右雙 QR Code、字軌、消費明細）。

### 2. 倉庫調撥作業 (Inter-Warehouse Transfer)
進入 **「多倉庫存與流水」**（`/inventory`）：
1. 於頂部「倉庫調撥作業」卡片中，選擇 **來源倉庫**（如主倉 `WH-MAIN`）、**目的倉庫**（如門市倉 `WH-STORE`）、輸入 **品號 (SKU)** 與 **調撥數量**。
2. 點擊 **「執行調撥」**：
   * **防負庫存檢驗**：系統自動校驗來源倉之可用餘額（`Available = Physical - Locked`）。若可用量不足，畫面即時彈出防呆警示橫幅。
   * **雙向記帳**：檢驗通過後，原子性在來源倉寫入負向流水（`-qty`），在目的倉寫入正向流水（`+qty`），庫存表格與異動日誌透過 HTMX 即時刷新。

---

## 四、 自動化測試與架構驗收 (Testing & Verification)

專案內建完整的自動化單元測試、整合測試與 AST 相依性架構檢查器。

### 1. 執行全套測試
在 PowerShell 終端機執行：

```powershell
python -m unittest discover -s tests
```

* **預期成果**：全部 25+ 項測試案例執行通過（`OK`），包括：
  * Day 1 資料庫模型與邊界測試
  * Day 2 庫存流水、採購移動平均成本、訂單出貨、MIG 3.2.1 電子發票與四單勾稽測試
  * Web GUI 端點、HTMX 局部抽換與 PDF 串流整合測試

### 2. 執行單獨架構邊界檢查 (Architecture Fitness Function)
確保系統嚴格遵守由外向內的單向相依性，杜絕底層反向引用外圍：

```powershell
python -m unittest tests/test_architecture_rules.py
```

* **驗證結果**：輸出 `✅ All architecture fitness checks passed! Strict unidirectional boundaries verified.`。

---

## 五、 產品生態與四層架構拆解 (Architecture Overview)

本專案複製三元科技（藍圖思維）產品體系，以中小企業進銷存為核心基石，層級拆分如下：

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
│ • 前段業務：DanLee CRM (商機管線、報價單套印)           │
│ • 後段會計：TanJee 記帳系統 (借貸傳票、帳齡、財務報表)  │
├────────────────────────────────────────────────────────┤
│ Layer 1: Core Engine (核心引擎層: Dinkoko ERP)         │
│ • 多倉庫存流水 (Stock Ledger) / 虛擬鎖庫 (Stock Locks) │
│ • 訂單 (SO) 1:1 出貨 (DO) 1:1 發票 (INV) 1:1 帳款 (AR)  │
└────────────────────────────────────────────────────────┘
```
