# 3Dollar ERP 專案即時狀態 (Project Status Living SSOT)

> [!IMPORTANT]
> **SSOT 邊界守則**：本文件為**專案執行狀態與進度 (Where & Now)** 的唯一真相來源。
> 所有規格標準、雙軌研發邊界（悲觀 MVP 裁切 vs 樂觀完整版）與架構插槽規範，唯一權威來源為 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)。任何任務開工前，必須同時查閱此處進度與 `ROADMAP.md` 規格。

## 專案進度儀表板 (Dashboard)

* **專案名稱**：3Dollar ERP (三元科技產品架構複製)
* **當前衝刺階段**：Day 2 完成，推進 Day 3 (TanJee 會計與記帳系統)
* **研發策略模式**：雙軌制（悲觀基準 MVP 交付優先，架構插槽預留樂觀完整版）
* **整體完成度**：28.6% [███░░░░░░░]
* **當前焦點任務**：Day 3 記帳系統（事件自動轉傳票 $Dr=Cr$、應收應付帳齡、損益表與試算表產出）
* **當前阻礙 (Blockers)**：無
* **最後更新時間**：2026-09-14

---

## 里程碑詳細追蹤 (Milestone Tracking)

### [x] Day 1: 核心架構與資料基底 (Core Architecture & Data Foundations) - 已驗收
- [x] **Task 1.1**: 專案結構初始化（Modular Monolith 領域模組骨架與基礎配置）
- [x] **Task 1.2**: 關聯式資料庫 Schema 建模（多倉庫存、單據流轉、交易日誌、借貸傳票）
- [x] **Task 1.3**: 設定架構邊界防護與相依性檢查器（AST 規則防護與 test_architecture_rules.py）
- [x] **Task 1.4**: 實作基礎 Data Access / Repository 層與資料庫連接驗證測試

### [x] Day 2: Dinkoko ERP 核心流程 (Core Engine) - 已驗收
> 規格詳細定義：[`ROADMAP.md#第一層核心層dinkoko-erp---營運與單據中樞`](file:///d:/3dollar_erp/ROADMAP.md#第一層核心層dinkoko-erp---營運與單據中樞)
- [x] **Task 2.1**: 多倉庫存管理與調撥邏輯（落實 ROADMAP 悲觀 MVP：主倉/門市雙倉流水、虛擬鎖庫、防負庫存）
- [x] **Task 2.2**: 採購進貨流程與入庫單據處理（落實 ROADMAP 悲觀 MVP：PO $\rightarrow$ GRN 移動平均成本計價）
- [x] **Task 2.3**: 訂單管理與出貨扣庫一條龍（落實 ROADMAP 悲觀 MVP：一鍵轉出貨單 DO、PDF 標籤）
- [x] **Task 2.4**: 台灣電子發票開立與四單自動對帳（落實 ROADMAP 悲觀 MVP：MIG 3.2.1 MockProvider、SO 1:1 DO 1:1 INV 1:1 AR 剛性對帳）
- [x] **Task 2.5**: 每日自動化排程引擎（落實 ROADMAP 悲觀 MVP：低安全存量掃描、逾期應收單據掃描）
- [x] **Task 2.6**: Dinkoko ERP 營運管理 Web GUI 垂直切片（落實 Zero-Build SSR：儀表板 KPI、訂單與出貨 HTMX 局部更新、物流標籤與發票 PDF 串流、多倉調撥表）

### 後續衝刺清單 (Day 3 ~ Day 7 待啟動)
> 具體業務規格、驗收標準與雙軌裁切定義嚴格收錄於 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)，此處不展開單一行標題以杜絕假性滿足：
* **Day 3**: TanJee 會計與記帳系統（事件自動轉傳票 $Dr=Cr$、帳齡分析、損益表與試算表產出）
* **Day 4**: DanLee CRM 前段商機（客戶主檔、四段商機管線、DOCX 範本套印與 PDF 產出）
* **Day 5**: LINE Bot 智能通路入口（Webhook 簽名驗證、Flex Message 型錄與直接下單、查單）
* **Day 6**: AI 增強外掛與檔案自動化（BOM 表 Excel 解析比價、原生 PDF 電子發票抽取、報表匯出）
* **Day 7**: 全鏈路端到端整合與驗收（商機 $\rightarrow$ 報價 $\rightarrow$ 下單 $\rightarrow$ 出貨扣庫 $\rightarrow$ 會計出表 E2E 驗收與種子資料）

---

## 驗收日誌 (Verification Log)

| 時間戳記 | 階段 / 任務 | 驗收內容與成果 | 狀態 |
| :--- | :--- | :--- | :--- | :---: |
| 2026-09-14 | 初始化 | 完成專案 Roadmap 與 Living SSOT 狀態追蹤機制建置 | PASS |
| 2026-09-14 | 版本控管 | 初始化 Git 儲存庫與配置多語言環境 .gitignore | PASS |
| 2026-09-14 | Day 1 (Task 1.1 - 1.4) | 完成 Modular Monolith 骨架、SQLite ANSI Schema、AST 架構邊界守護與自動化測試 (5/5 PASS) | PASS |
| 2026-09-14 | 規劃同步 | 同步 ROADMAP.md 雙軌研發規格（悲觀基準 MVP vs 樂觀完整版）與擴充插槽定義 | PASS |
| 2026-09-14 | 治理與協議強化 | 重構 STATUS.md 與 AGENTS.md，消除偽完整假象，建立強制雙重查核（STATUS 進度 + ROADMAP 悲觀 MVP 規格）協議 | PASS |
| 2026-09-14 | Day 2 (Task 2.1 - 2.5) | 完成雙倉流水 (Stock Ledger)、移動平均成本、訂單出貨與物流標籤 PDF、MIG 3.2.1 發票與 5.7cm PDF、SO:DO:INV:AR 四單剛性對帳與每日排程掃描，通過全部單元與架構邊界測試 (20/20 PASS) | PASS |
| 2026-09-14 | 架構與記憶固化 | 補齊 ROADMAP.md Layer 3 Web GUI 規格與 View DTO 垂直切片準則，更新 AGENTS.md 守則，寫入 Serena 永久架構記憶 | PASS |
| 2026-09-14 | Day 2 (Task 2.6 Web GUI) | 完成 Zero-Build SSR 管理後台（FastAPI+Jinja2+HTMX+Tailwind CDN），實作 View DTO、儀表板圖卡、訂單 HTMX 鎖庫/出貨/開票、雙倉調撥與 PDF 串流，通過全部端點整合測試 (25/25 PASS) | PASS |
