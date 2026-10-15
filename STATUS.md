# 3Dollar ERP 專案即時狀態 (Project Status Living SSOT)

> [!IMPORTANT]
> **SSOT 邊界守則**：本文件為**專案執行狀態與進度 (Where & Now)** 的唯一真相來源。
> 所有規格標準、雙軌研發邊界（青春版 MVP 裁切 vs 樂觀完整版）與架構插槽規範，唯一權威來源為 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)。任何任務開工前，必須同時查閱此處進度與 `ROADMAP.md` 規格。

### 專案進度儀表板 (Dashboard)

* **專案名稱**：3Dollar ERP (三圓科技產品架構複製)
* **當前衝刺階段**：高層級名稱優先呈現與視覺降噪 (High-Level Name Priority)
* **研發策略模式**：雙軌制（青春版基準 MVP 交付完畢，滿血版推進中）
* **整體完成度**：100.0%（全系統 194/194 PASS，架構邊界 0 違規）
* **當前焦點任務**：Iteration 0924 高層級名稱翻轉全 4 批次交付完畢
* **當前阻礙 (Blockers)**：無阻礙 (None)
* **最後更新時間**：2026-09-24

---

## 里程碑詳細追蹤 (Milestone Tracking)

### [x] Day 1: 核心架構與資料基底 (Core Architecture & Data Foundations) - 已驗收
- [x] **Task 1.1**: 專案結構初始化（Modular Monolith 領域模組骨架與基礎配置）
- [x] **Task 1.2**: 關聯式資料庫 Schema 建模（多倉庫存、單據流轉、交易日誌、借貸傳票）
- [x] **Task 1.3**: 設定架構邊界防護與相依性檢查器（AST 規則防護與 test_architecture_rules.py）
- [x] **Task 1.4**: 實作基礎 Data Access / Repository 層與資料庫連接驗證測試

### [x] Day 2: Dura ERP 核心流程 (Core Engine) - 已驗收
> 規格詳細定義：[`ROADMAP.md#第一層核心層dura-erp---營運與單據中樞`](file:///d:/3dollar_erp/ROADMAP.md#第一層核心層dura-erp---營運與單據中樞)
- [x] **Task 2.1**: 多倉庫存管理與調撥邏輯（落實 ROADMAP 青春版 MVP：主倉/門市雙倉流水、虛擬鎖庫、防負庫存）
- [x] **Task 2.2**: 採購進貨流程與入庫單據處理（落實 ROADMAP 青春版 MVP：PO $\rightarrow$ GRN 移動平均成本計價）
- [x] **Task 2.3**: 訂單管理與出貨扣庫一條龍（落實 ROADMAP 青春版 MVP：一鍵轉出貨單 DO、PDF 標籤）
- [x] **Task 2.4**: 台灣電子發票開立與四單自動對帳（落實 ROADMAP 青春版 MVP：MIG 3.2.1 MockProvider、SO 1:1 DO 1:1 INV 1:1 AR 剛性對帳）
- [x] **Task 2.5**: 每日自動化排程引擎（落實 ROADMAP 青春版 MVP：低安全存量掃描、逾期應收單據掃描）
- [x] **Task 2.6**: Dura ERP 營運管理 Web GUI 垂直切片（落實 Zero-Build SSR：儀表板 KPI、訂單與出貨 HTMX 局部更新、物流標籤與發票 PDF 串流、多倉調撥表）

### [x] Day 3: 探吉 (TanGii) 會計與記帳系統 (Extended Core) - 已驗收
> 規格詳細定義：[`ROADMAP.md#2-探吉-tangi-記帳系統業務後段管理會計與內帳`](file:///d:/3dollar_erp/ROADMAP.md#2-探吉-tangi-記帳系統業務後段管理會計與內帳)
- [x] **Task 3.1**: 擴充會計資料模型與科目表（EAS/GAAP 標準代碼、AccountsPayable 表、Pydantic 借貸平衡校驗器）
- [x] **Task 3.2**: 實作 AccountingService 借貸總帳引擎（剛性借貸平衡傳票、試算表、多步驟損益表、款項沖銷）
- [x] **Task 3.3**: 實作 ERP 核心事件自動入帳處理器（GRN 入庫轉 AP、DO 出庫轉銷貨成本、INV 開票轉營收與營業稅）
- [x] **Task 3.4**: 實作應收 (AR) 與應付 (AP) 帳齡分析引擎（Current、1-30天、31-60天、60+天矩陣與催收管理）
- [x] **Task 3.5**: 財務報表 Excel 原生串流匯出引擎（基於 xlsxwriter 產出專業排版之試算表與損益表）
- [x] **Task 3.6**: 探吉 (TanGii) 會計記帳 Web GUI 垂直切片（Zero-Build SSR：`/accounting` 財務 KPI、試算表、損益表、帳齡分析與手動傳票輸入）

### [x] Day 4: 哩來 (LiLai) CRM 前段商機 (Extended Core) - 已驗收
> 規格詳細定義：[`ROADMAP.md#1-哩來-lilai-crm業務前段名片到成交`](file:///d:/3dollar_erp/ROADMAP.md#1-哩來-lilai-crm業務前段名片到成交)
- [x] **Task 4.1**: 客戶主檔與聯絡人管理（統編 8 位數格式檢驗、公司與窗口建檔、防呆與資料模型擴充）
- [x] **Task 4.2**: 四段商機管線狀態機（LEAD $\rightarrow$ DISCOVERY $\rightarrow$ PROPOSAL $\rightarrow$ WON / LOST 剛性推進與已轉單鎖定保護）
- [x] **Task 4.3**: 報價單與文件套印中心（python-docx 原生產生 Word 報價單範本、PyMuPDF 原生產生防竄改 A4 報價單 PDF、多品項明細與稅額試算）
- [x] **Task 4.4**: 贏單 (WON) 一鍵穿透拋轉 ERP 銷售訂單（呼叫 OrderService 建立 CRM 通路 DRAFT 銷售訂單、converted_order_id 雙向關聯、報價單自動 ACCEPTED）
- [x] **Task 4.5**: 哩來 CRM 營運管理 Web GUI 垂直切片（Zero-Build SSR：`/crm` 四欄式商機看板、客戶主檔分頁、報價單 DOCX/PDF 串流下載、一鍵轉 ERP 訂單）

### [x] Day 5: LINE Bot 智能通路入口 (Channel & UI) - 已驗收 (100% 完成)
> 規格詳細定義：[`ROADMAP.md#2-外部客戶輕量通路line-bot-智能對話入口`](file:///d:/3dollar_erp/ROADMAP.md#2-外部客戶輕量通路line-bot-智能對話入口)
- [x] **Task 5.1**: Webhook 簽名防偽與事件分流（HMAC-SHA256 數位簽名檢驗、MessageEvent 與 PostbackEvent 派發）
- [x] **Task 5.2**: Flex Message 視覺卡片構建器（遵循 LINE 官方 Pydantic 模型，商品型錄輪播卡、訂單成立收據卡、出貨/發票進度卡）
- [x] **Task 5.3**: 一鍵穿透下單與鎖庫流程（Postback 一鍵下單 `channel_id="LINE"`，呼叫 OrderService 建立訂單並鎖庫，庫存不足自動取消並回傳繁中防呆通知）
- [x] **Task 5.4**: 自助文字查單與進度回報（解析「查單 SO-xxx」，查詢訂單狀態、出貨單 DO、物流追蹤碼與電子發票號碼）
- [x] **Task 5.5**: 緊湊型 Rich Menu 圖文選單配置規範（2500x843 畫布、3 格佈局 JSON 與 Pydantic 模型產生器）
- [x] **Task 5.6**: 全鏈路離線仿真測試體系（`LineMessagingPort` 與 `MockLineMessagingAdapter`，無外部網路/真實密鑰依賴之 E2E 仿真測試 14/14 PASS）
- [x] **Task 5.7**: 真機對接與上線驗證（.env 換發 Stateless Token v3、Cloudflare Quick Tunnel TPE01 Webhook 綁定、LINE OA 後台關閉自動回覆、2500x843 亮色極簡 Rich Menu 上傳綁定、手機端 @337keuin E2E 實機抽測全數通過）
- [x] **Task 5.8**: Flex Card 氣泡安全邊距與底部提示字級排版優化（Header/Footer 安全內距與文字對齊 QOL 修復）

### [x] Day 6: AI 增強外掛與檔案自動化 (AI Wrapper & Native File Engine) - 已驗收
> 規格詳細定義：[`ROADMAP.md#第四層外圍增強層ai-wrapper---自動化與知識外掛`](file:///d:/3dollar_erp/ROADMAP.md#第四層外圍增強層ai-wrapper---自動化與知識外掛)
- [x] **Task 6.1**: BOM 表 Excel 批量解析與多供應商歷史比價（openpyxl 智慧表頭辨識、歷史採購單價格跨表比對、最低價供應商推薦與潛在節省金額試算）
- [x] **Task 6.2**: 原生 PDF 電子發票文字層抽取與自動入帳（PyMuPDF/fitz 原生抽取 MIG 3.2.1/B2B 統一發票字軌、統編、金額，免 OCR 誤差，算式勾稽與 AP 一鍵拋轉）
- [x] **Task 6.3**: 全方位財務與營運報表原生串流生成（xlsxwriter 產出損益表、試算表、帳齡矩陣、雙倉庫存盤點底冊 4 合 1 高階主管活頁簿，BOM 比價報表）
- [x] **Task 6.4**: AI 增強外掛與檔案自動化 Web GUI 垂直切片（Zero-Build SSR：`/ai/tools` 三頁籤作業中心、拖曳上傳、示範 BOM/發票下載、HTMX 局部預覽卡片）
- [x] **Task 6.5**: 4 層單向依賴嚴格解耦與全套自動化測試（動態外掛掛載，check_boundaries.py 零違規，全專案 72/72 PASS）

### [x] Day 7: 全鏈路端到端整合與驗收 (Final Full-Lifecycle E2E Integration & Delivery) - 已驗收 (100% 完成)
> 規格詳細定義：[`ROADMAP.md#四-7-天雙軌時程規劃表-7-day-dual-track-sprint`](file:///d:/3dollar_erp/ROADMAP.md#四-7-天雙軌時程規劃表-7-day-dual-track-sprint)
- [x] **Task 7.1**: 訂單生命週期狀態機完備（出貨與開票後自動晉級至 `COMPLETED` 完成狀態，雙向閉環校驗）
- [x] **Task 7.2**: 展示環境豐富種子資料注入（`demo_seed.py` 擴充多通路 DIRECT / CRM / LINE 及 DRAFT / CONFIRMED / SHIPPED / COMPLETED 各階段示範單據）
- [x] **Task 7.3**: 全鏈路端到端整合測試套件（`test_full_lifecycle_e2e.py` 覆蓋 B2B 商機轉單、B2C LINE 下單出貨查單、AI 檔案與會計 4-Way Match 全流程）
- [x] **Task 7.4**: Playwright 真實瀏覽器端到端驗收（`test_playwright_day7_e2e.py` 串聯四大垂直切片 Web 互動，全專案 91/91 測試與架構防護 0 違規全數通過）

### [x] Full Expansion Batch 1: 底層基建與核心彈性 (Core Resilience & DB Migration) - 已驗收 (100% 完成)
> 規格詳細定義：[`ROADMAP.md#第-1-批底層基建與核心彈性-core-resilience--db-migration`](file:///d:/3dollar_erp/ROADMAP.md#第-1-批底層基建與核心彈性-core-resilience--db-migration)
- [x] **Task B1.1**: PostgreSQL 抽象與 Alembic 版本控制（雙引擎 `Database`、參數標記 `?` $\rightarrow$ `%s` 透明轉譯、`UnifiedRow` 索引/鍵名雙模式存取、Alembic 001 基準腳本）
- [x] **Task B1.2**: 1:N 訂單拆批出貨與前端對話框切片（`delivery_allocations` 關聯表、`shipped_quantity` 累計、`PARTIALLY_SHIPPED` 狀態機、`partial_ship_modal.html` 拆批彈窗、`deliveries_modal.html` 出貨歷程檢視、1:1 零破壞向下相容）
- [x] **Task B1.3**: A4 多格標籤排版適配與起印選取切片（`PdfPrinterAdapter` 實作 2x2 A4 標籤紙排版、`a4_label_modal.html` 視覺化 1~4 格位選取、`/orders/{id}/label_a4.pdf` 支援 `start_pos`/`do_id` 路由串接）

### [ ] Full Expansion Batch 2: 次核心業務深化 (Extended Core: Accounting, CRM & Lightweight HR)
> 規格詳細定義：[`ROADMAP.md#第-2-批次核心業務深化-extended-core-accounting-crm--lightweight-hr`](file:///d:/3dollar_erp/ROADMAP.md#第-2-批次核心業務深化-extended-core-accounting-crm--lightweight-hr)
- [ ] **Task B2.1**: 探吉 (TanGii) 完整財務報表垂直切片（資產負債表與現金流量表產出邏輯、`/accounting` 查詢頁籤、金額展示表格與 Excel 匯出）
- [ ] **Task B2.2**: 台銀公開牌告匯率與匯兌損益垂直切片（公開免費牌告匯率排程更新、收付款沖銷自動拋轉兌換損益傳票、沖銷彈窗幣別與匯率欄位）
- [ ] **Task B2.3**: 哩來 (LiLai) 規則式 Lead Scoring 垂直切片（0～100 分規則計分引擎、`/crm` 看板卡片與客戶清冊評分徽章渲染與排序篩選）
- [ ] **Task B2.4**: 報價單/合約多版本審批垂直切片（草稿多版本 v1/v2 比對、簽核狀態機、CRM 詳情頁版本下拉切換與主管核准/駁回按鈕）
- [ ] **Task B2.5**: 微型 HR 考勤打卡核心垂直切片（`attendance_records` 資料模型、打卡防呆規則、`/hr/attendance` 考勤管理日曆切片與出缺勤統計卡）

### [x] 業務整併與抽象層第 1 階段 (Core Contracts & Domain Relocation) - 已驗收
- [x] **Task 8.1**: 發票與貨運單雙抽象層（`ShippingCarrierPort`、`InternalShippingCarrierProvider` 自簽條碼與 QR 碼、`OrderService` 解耦）
- [x] **Task 8.2**: CRM Lead 品項化計價（`crm_deal_items` 資料表、`DealItem` 領域模型、`create_deal()` 多品項動態計價與自動累計）
- [x] **Task 8.3**: BOM 與財務報表業務歸位（BOM 解析與比價移至 `src/core` 採購業務，財務整合報表移至 `src/extended_core/accounting` 會計業務，解除跨層違規並向下相容）

### [x] 業務整併與前端垂直切片第 2 階段 (Web Workflow & UI Slices) - 已驗收
- [x] **Task 9.1**: 採購進貨中心整合 BOM 解析比價與一鍵依供應商分割下單（`GET /procurement/bom/sample`、`POST /procurement/bom/compare`、`POST /procurement/bom/create-pos` 自動 Group by Supplier 生成多張 DRAFT PO 並即刻更新流水）
- [x] **Task 9.2**: 營運儀表板低存量警報完整預填（`LowStockItemDTO` 擴充 `warehouse_id`, `suggested_qty`, `suggested_supplier`，點選「採購補貨」完整自動帶入料號、進貨倉、缺額量、單價與供應商）
- [x] **Task 9.3**: 多倉庫存與流水人性化選單與一鍵採購（調撥表單來源/目的倉動態載入並顯示直觀中文名稱，低於安全量品項提供「一鍵下單 &rarr;」按鈕）
- [x] **Task 9.4**: 會計記帳 4合1 財務報表中心與 MathJax 公式渲染（納入 `tab=reports` 財務報表中心與串流下載、引入 MathJax 3 使 $\sum Dr = \sum Cr$ 恆等式精美渲染）
- [x] **Task 9.5**: 哩來 CRM Lead 品項化計價建檔與轉報價單繼承（「建立新商機」支援品項與數量動態輸入與總額自動試算、商機卡片顯示品項摘要、轉報價單彈窗自動繼承物料明細）
#### [x] 體驗優化與多倉流轉深度迭代 (Iteration 0922)
> 規格詳細定義：[`iteration_0922_00.md`](file:///d:/3dollar_erp/iteration_0922_00.md)
- [x] **Batch 1**: 純前端微互動與字串精簡（庫存低量合併按鈕、調撥雙倉即時互斥與自動對調 JS、商機物料全面選填、預設數量歸 1、出貨單/A4出貨單正名、移除「原廠供應商」寫死字串）
- [x] **Batch 2**: CRM 轉單明細繼承與文件 PDF 半形化（轉單彈窗繼承報價單品項、PyMuPDF 英數符號強制半形與字型收斂）
- [x] **Batch 3**: 訂單出貨倉與採購目標倉多倉流轉架構（`sales_orders` 與 `purchase_orders` 增加 `warehouse_id`、轉單選出貨倉、驗收選目標倉、鎖扣倉一致性）
- [x] **Batch 4**: 全域通知統一與撤回 (Undo) 機制完備（CRM 階段推進 Toast OOB 與撤回、採購入庫紅字退庫沖銷與 AP 沖銷撤回、全站靜態綠框消滅）

#### [x] 體驗優化、系統防呆與報表對齊深度迭代 (Iteration 0923)
> 規格詳細定義：[`iteration_0923_00.md`](file:///d:/3dollar_erp/iteration_0923_00.md) / [`iteration-0923-00.md`](file:///d:/3dollar_erp/iteration-0923-00.md)
- [x] **Batch 1**: 純前端微互動、報表對齊與 Toast 多行自適應 (Pure Front-End: 報價單 Modal State 重置、庫存按鈕精簡、4 方塊文案對齊與字級放大、Toast break-words) - 已驗收 (4/4 PASS)
- [x] **Batch 2**: 訂單客戶辨識、CRM 贏單自動鎖庫與 BOM 批次撤回 (Fulfillment & CRM: CRM 贏單自動 confirm_order 鎖庫、訂單清單關聯公司名稱、BOM 分割下單批次撤回) - 已驗收 (3/3 PASS)
- [x] **Batch 3**: 會計防誤觸彈窗、發票防重與 PDF 嚴格半形化 (Accounting & Safety: 會計二階確認彈窗消滅 Chrome 對話框、進項發票防重登記、全域 PDF 半形正規化) - 已驗收 (5/5 PASS)

#### [x] 系統易用性與履約深度收斂迭代 (Bug Fixes 0923) - 已驗收 (100% 完成)
- [x] **Batch 1**: 體驗優化、商機導流與報表業務歸位 (Bug 1, 2, 3, 6: 報價單解除2項限制動態增刪、CRM 推進滾動跳底修復與結案區歷史折疊收合、轉單跳轉高亮脈衝聚焦、庫存盤點底冊 Excel 移至庫存區 /inventory) - 已驗收 (4/4 PASS)
- [x] **Batch 2**: 核心履約架構與拆批單據閉環 (Bug 4, 5: 拆批出貨支援選擇出貨倉庫、跨倉調撥扣庫與虛擬鎖庫一致性核銷、100x150 普通出貨單支援多批連續分頁列印) - 已驗收 (3/3 PASS, 全系統 165/165 PASS)

#### [x] 高層級名稱優先呈現與視覺降噪迭代 (Iteration 0924)
> 規格詳細定義：[`iteration-0924-high-level-name.md`](file:///d:/3dollar_erp/iteration-0924-high-level-name.md)
- [x] **Batch 1**: 庫存與營運儀表板高層級名稱翻轉 (Inventory & Dashboard: 低存量卡片品名大字置頂與 SKU 弱化標籤化、庫存總覽表格與行切片品名優先於品號) - 已驗收 (3/3 PASS)
- [x] **Batch 2**: 採購中心表單與單據明細名稱翻轉 (Procurement: 開單下拉選單「品名 (SKU) - 目前成本」、表頭正名「採購物料 (品名 / SKU)」、採購單列品名粗體優先、驗收入庫與 BOM 比價清冊品名優先) - 已驗收 (4/4 PASS)
- [x] **Batch 3**: 銷售訂單與履約彈窗名稱翻轉 (Sales Orders & Modals: 訂單表頭客戶名稱、出貨確認/拆批/出貨歷程彈窗預解析 View DTO 繁中品名與客戶名稱) - 已驗收 (5/5 PASS)
- [x] **Batch 4**: 外部通路、報價單與會計名稱翻轉 (LINE Bot, Documents & Accounting: LINE Flex 卡片品名優先、報價單文件表格正名、會計帳齡表客戶名稱顯著化) - 已驗收 (4/4 PASS)
- [x] **Playwright E2E**: 高層級名稱翻轉 Headed 瀏覽器端到端 UI 全自動驗收 (4大情境全量涵蓋) - 已驗收 (1/1 PASS)

---

## 驗收日誌 (Verification Log)

| 時間戳記 | 階段 / 任務 | 驗收內容與成果 | 狀態 |
| :--- | :--- | :--- | :--- |
| 2026-09-14 | 初始化 | 完成專案 Roadmap 與 Living SSOT 狀態追蹤機制建置 | PASS |
| 2026-09-14 | 版本控管 | 初始化 Git 儲存庫與配置多語言環境 .gitignore | PASS |
| 2026-09-14 | Day 1 (Task 1.1 - 1.4) | 完成 Modular Monolith 骨架、SQLite ANSI Schema、AST 架構邊界守護與自動化測試 (5/5 PASS) | PASS |
| 2026-09-14 | 規劃同步 | 同步 ROADMAP.md 雙軌研發規格（青春版基準 MVP vs 樂觀完整版）與擴充插槽定義 | PASS |
| 2026-09-14 | 治理與協議強化 | 重構 STATUS.md 與 AGENTS.md，消除偽完整假象，建立強制雙重查核（STATUS 進度 + ROADMAP 青春版 MVP 規格）協議 | PASS |
| 2026-09-14 | Day 2 (Task 2.1 - 2.5) | 完成雙倉流水 (Stock Ledger)、移動平均成本、訂單出貨與物流標籤 PDF、MIG 3.2.1 發票與 5.7cm PDF、SO:DO:INV:AR 四單剛性對帳與每日排程掃描，通過全部單元與架構邊界測試 (20/20 PASS) | PASS |
| 2026-09-14 | 架構與記憶固化 | 補齊 ROADMAP.md Layer 3 Web GUI 規格與 View DTO 垂直切片準則，更新 AGENTS.md 守則，寫入 Serena 永久架構記憶 | PASS |
| 2026-09-14 | Day 2 (Task 2.6 Web GUI) | 完成 Zero-Build SSR 管理後台（FastAPI+Jinja2+HTMX+Tailwind CDN），實作 View DTO、儀表板圖卡、訂單 HTMX 鎖庫/出貨/開票、雙倉調撥與 PDF 串流，通過全部端點整合測試 (25/25 PASS) | PASS |
| 2026-09-14 | 操作手冊與 SSOT 定位 | 完善 README.md 作為全專案權威使用說明書與快速啟動指南，於 AGENTS.md 與 Serena 永久記憶明確固化其定位 | PASS |
| 2026-09-14 | 術語標準化 (青春版) | 全面修訂 AGENTS.md、ROADMAP.md、STATUS.md 措辭，以「青春版 (Youth Edition MVP)」全面替代原「悲觀基準線」 | PASS |
| 2026-09-14 | HTMX 錯誤橫幅修復 | 配置 base.html 支援 4xx/5xx beforeSwap 與 OOB 全局 #toast-container 替換，通過 Playwright 瀏覽器實測防負庫存紅底警示 | PASS |
| 2026-09-14 | 資料庫自動建表與種子資料 | 實作 demo_seed.py 並掛載至 app.py 啟動流程，自動檢查建表並注入雙倉、3項示範商品與3筆不同階段訂單 | PASS |
| 2026-09-14 | 全域錯誤防洩漏雙重防禦 | 前端白名單攔截 5xx (shouldSwap=false) 保全畫面，後端全域 Exception 攔截阻斷原始 Traceback，全部單元測試 (25/25 PASS) | PASS |
| 2026-09-14 | SSOT 狀態同步與階段固化 | 全面同步 STATUS.md、README.md、ROADMAP.md 與 Serena 永久架構記憶，完成 Day 2 完美收斂，準備推進 Day 3 | PASS |
| 2026-09-14 | Day 3 (探吉 會計與記帳系統) | 完成 EAS/GAAP 會計模型、借貸恆等式強制校驗、ERP 事件自動入帳 (GRN/DO/INV)、AR/AP 4 區間帳齡分析、xlsxwriter 試算表/損益表匯出、Zero-Build SSR Web GUI (/accounting) 與全套自動化測試 (42/42 PASS, 架構防護 PASS) | PASS |
| 2026-09-16 | 品牌與模組全域防侵權重命名 | 完成「三元」$\rightarrow$「三圓」、「TanJee」$\rightarrow$「探吉 (TanGii)」、「DanLee」$\rightarrow$「哩來 (LiLai)」全庫替換（SSOT 文件、資料庫模型註解、UI 視圖範本、報表匯出預設抬頭與自動化測試），全套測試 42/42 PASS | PASS |
| 2026-09-17 | 探吉會計驗收與全域錯誤中文化 | 完成帳齡天數色彩語意配套、會計試算表累計機制驗證、全域使用者錯誤訊息繁體中文化雙層防禦（AGENTS.md 守則固化、Serena 永久記憶、app.py 安全網、核心服務全面在地化），測試 42/42 PASS | PASS |
| 2026-09-17 | EventBus 單例分裂根除與 DI 重構 | 核心領域服務 (__init__) 移除預設 default_event_bus 改為強制顯式注入；Web 路由全面採用 FastAPI Depends DI 提供者；tools/check_boundaries.py 加入 AST 規則嚴格禁止 default_event_bus 匯入；新增端到端跨層整合測試 (test_cross_layer_event_e2e.py)，驗收 44/44 PASS | PASS |
| 2026-09-17 | Day 4 (哩來 CRM 前段商機) | 完成客戶主檔 (統編8碼校驗)、四段商機管線狀態機 (LEAD $\rightarrow$ DISCOVERY $\rightarrow$ PROPOSAL $\rightarrow$ WON/LOST)、python-docx 原生產生 Word 報價單與 PyMuPDF 原生產生防竄改 A4 報價單 PDF、贏單一鍵穿透拋轉 ERP 銷售訂單 (SO)、Zero-Build SSR Web 管理後台切片 (/crm 看板與客戶清冊)、全域繁體中文錯誤防護與展示資料種子，全套測試與架構邊界守護全數通過 (55/55 PASS) | PASS |
| 2026-09-17 | CRM 互動體驗與通知層強化 | 解決瀏覽器 Autofill 搶填、修正彈窗成功後自動隱藏生命週期、將全域 #toast-container 提升為 z-[9999] 浮動頂層通知中心並經 Playwright 截圖驗收通過 (55/55 PASS) | PASS |
| 2026-09-18 | CRM 使用者體驗三項優化 | 完成防止同名企業重複錄入防呆、客戶清冊列點擊開啟編輯彈窗 (公司名唯讀鎖定)、Word (.docx) 報價單表格內建 Table Grid 網格線，全套自動化測試與 Playwright 瀏覽器驗證全數通過 (56/56 PASS) | PASS |
| 2026-09-18 | Day 5 (LINE Bot 智能通路入口) | 完成 HMAC-SHA256 簽名校驗 Webhook、Flex Message 商品型錄輪播卡/收據卡/查單卡、Postback 一鍵穿透下單寫入 ERP (channel=LINE) 與鎖庫流程、自助文字查單、2500x843 緊湊型 Rich Menu 規格、Stateless Token v3 自動換發機制、全套離線仿真測試 (70/70 PASS)；標記待真機連通驗收 | 仿真 PASS (待真機) |
| 2026-09-19 | Day 5 (Task 5.7 真機對接與上線驗收) | 完成真實金鑰 Stateless Token v3 換發、Cloudflare Quick Tunnel (TPE01) 自動化 Webhook 連通驗證、2500x843 亮色極簡 Rich Menu 預設綁定、真機手機端（@337keuin）加入好友、Flex 商品型錄瀏覽、一鍵穿透 ERP 下單鎖庫、自助查單全鏈路實機抽測全數通過 | PASS |
| 2026-09-19 | Day 5 (Task 5.8 Flex 排版 QOL 優化) | 調整商品型錄、訂單建立、訂單進度 Flex 卡片 header/footer 安全邊距與字級行距，測試 70/70 PASS | PASS |
| 2026-09-19 | Day 6 (AI 增強外掛與檔案自動化) | 完成 BOM 表 Excel 批量解析比價 (openpyxl)、原生 PDF 電子發票向量文字層抽取與自動建立 AP 應付帳款 (fitz/PyMuPDF)、全方位 4 合 1 財務與營運整合 Excel 串流生成 (xlsxwriter)、Zero-Build SSR 管理後台切片 (/ai/tools 與 HTMX 局部預覽)、Layer 3 與 Layer 4 動態外掛單向解耦，通過 check_boundaries 與全專案測試 (72/72 PASS) | PASS |
| 2026-09-19 | Day 6 (Playwright 瀏覽器端到端驗收) | 依據驗收規格完成真實 Chromium 瀏覽器 5 大情境測試（頁籤無刷新切換、BOM 範本下載/上傳比價推薦、電子發票 PDF 抽取與一鍵建立 AP、4合1 財務報表串流匯出、探吉會計帳齡與試算表借貸平衡穿透驗收），全專案 87/87 測試全數通過，銷毀暫行驗收規格書 | PASS |
| 2026-09-19 | Day 6 (使用者手動全功能真機驗收) | 使用者手動完成 5 大功能逐一驗證，修復示範發票 PDF 排版溢出、移除示範發票按鈕、更名為「下載 BOM 匯入範本」、買方未設置標準化、修正發票金額勾稽繁中公式與 PO 媒合重複防呆，全套測試 87/87 PASS，宣告 Day 6 驗收通過 | PASS |
| 2026-09-19 | Day 7 (全鏈路端到端整合與驗收) | 完成訂單 COMPLETED 狀態機閉環、demo_seed 多通路 (DIRECT/CRM/LINE) 與多階段單據擴充、B2B/B2C/AI 三路全鏈路 E2E 測試 (test_full_lifecycle_e2e.py)、Playwright 瀏覽器端到端驗收 (test_playwright_day7_e2e.py)、架構邊界 0 違規，全專案 91/91 自動化測試 100% 通過，全案正式交付 | PASS |
| 2026-09-20 | 滿血版第 1 批 (底層基建與核心彈性) | 完成 PostgreSQL 雙引擎轉接抽象、Alembic 001 遷移設定、1:N 訂單拆批出貨 (delivery_allocations / PARTIALLY_SHIPPED)、辦公室多格 A4 標籤貼紙 (2x2) 產生與下載，全套測試 100/100 PASS，架構邊界 0 違規 | PASS |
| 2026-09-20 | 滿血版第 1 批 (Playwright 真人 UI 端到端驗收) | 完成拆批出貨 UI 對話框、A4 多格標籤下載與尺寸驗證、超額防呆紅底警示、全狀態機躍遷與全模組雙引擎導覽，新增 test_playwright_batch1.py，全套 102/102 測試全數通過 | PASS |
| 2026-09-20 | 滿血版第 1 批 (UI 垂直切片補正與全流程貫通) | 補齊 1:N 出貨單歷程檢視彈窗 (deliveries_modal.html)、A4 標籤 2x2 視覺化起印選取彈窗 (a4_label_modal.html)、路由支援 start_pos/do_id 與 OrderRowDTO 欄位擴充，全系統 101/101 自動化測試全數通過，架構邊界 0 違規 | PASS |
| 2026-09-20 | 滿血版第 1 批 (Headed Playwright 真人 UI 驗收) | 依據使用者明確指令啟動 Headed Playwright 真實瀏覽器，全流程驗收拆批超額防呆、1:N 出貨歷程彈窗、A4 視覺化起印選取 (start_pos=3)、狀態機完整閉環與 5 大模組導覽，test_playwright_batch1.py 1/1 PASS | PASS |
| 2026-09-20 | 架構防禦 (發票與應收 1:1 約束解除) | 完成 schema.sql、migrations 001 及實體 erp.db 重建，解除 invoices.order_id 與 accounts_receivable.order_id 之 UNIQUE 約束並補齊索引，新增多單據資料庫測試 test_invoices_and_ar_allow_multiple_per_order，單元與架構邊界 0 違規全數 PASS | PASS |
| 2026-09-21 | 滿血版第 1 批 (使用者全功能真機手動驗收) | 使用者手動完成 1:N 拆批出貨、超額防呆、A4 標籤直向預覽適配、出貨歷程時間戳記展示、全域彈窗容器跨頁強化全面驗收通過，全系統 102/102 測試通過，宣告滿血版第 1 批正式交付完工 | PASS |
| 2026-09-21 | 核心引擎更名 (Dinkoko ➔ Dura ERP) | 貫徹「不使用模仿對象真實名字」原則，全面重命名核心引擎為 Dura ERP。完成 AGENTS.md、ROADMAP.md、STATUS.md、README.md、FastAPI Swagger OpenAPI 描述、LineBotService 與核心註釋共 8 處同步更新，修正跨文件跳轉錨點；全代碼庫全文搜尋 0 殘留，架構邊界 0 違規，全量 79/79 單元測試全數通過 | PASS |
| 2026-09-21 | 模組更名 (AI 檔案自動化 ➔ 檔案自動化) | 完成側邊欄導覽 (base.html)、頁面標題與主標題 (ai_tools.html)、Web 路由 (routes.py)、測試套件 (test_ai_wrapper_web.py, test_playwright_batch1.py, test_playwright_day6.py, test_playwright_day7_e2e.py) 與 README.md 全面對齊更名為「檔案自動化」，架構邊界 0 違規，全量 79/79 單元測試全數通過 | PASS |
| 2026-09-21 | 採購進貨 Web 垂直切片 (/procurement) | 完成前端採購開單 (DRAFT)、確認下訂 (SUBMITTED)、驗收入庫 (GRN / RECEIVED)、移動平均成本加權重算、雙記帳庫存流水與會計應付帳款 (AP) 自動立帳，側邊欄與儀表板低庫存一鍵補貨串接，新增 test_procurement_web.py (6/6 PASS)，全系統 85/85 測試與架構邊界 0 違規全數通過 | PASS |
| 2026-09-21 | 採購模組 Headed Playwright UI 全功能端到端驗收 | 依據使用者明確指令實施 Headed 模式（headless=False, slow_mo=500ms）真實瀏覽器彈窗 7 大場景端到端驗收（首頁低庫存快捷跳轉、動態物料增刪、表單防呆、多品項開單、下訂 HTMX 局部抽換、入庫彈窗、雙倉庫存流水增加、移動平均成本重算與會計 AP 自動立帳），產出 6 張驗收截圖，test_playwright_procurement.py 1/1 PASS，全系統 85/85 測試與架構邊界 0 違規全數通過 | PASS |
| 2026-09-22 | 業務整併與抽象層 (第 1 階段) | 完成發票與貨運單雙抽象層 (ShippingCarrierPort)、CRM Lead 多品項計價 (crm_deal_items)、BOM 與財務報表業務歸位 (Layer 1/2)，通過架構防護與全套自動化測試 (111/111 PASS)，Headed Playwright 測試 4/4 PASS | PASS |
| 2026-09-22 | 業務整併與前端垂直切片 (第 2 階段) | 完成採購進貨 BOM 解析比價與一鍵依供應商分割下單、儀表板低存量警報預填、多倉名稱與低量一鍵下單、會計 4合1 報表中心與 MathJax 公式、CRM Lead 品項計價與轉報價單繼承；全套單元測試 116/116 PASS，Headed Playwright 測試 5/5 PASS | PASS |
| 2026-09-22 | 檔案自動化介面收斂 | 移除檔案自動化 (/ai/tools) 中已整併至採購與會計之 BOM 比價與 4合1 報表頁籤，轉為專注之電子發票向量抽取與 AP 建立工作台並附導流說明；test_ai_wrapper_web (7/7 PASS) 與 Headed Playwright 全數通過 | PASS |
| 2026-09-22 | 無摩擦防誤觸與撤回 (Phase 2 多倉調撥切片) | 完成多倉調撥立即執行與紅字反向沖銷 (revert_transfer)、HTMX 三重目標連動 (庫存表/流水表/Toast OOB)、防重複撤回與目的倉可用存量校驗，新增 test_inventory_undo_web.py，全專案 129/129 測試與架構防護 0 違規全數通過 | PASS |
| 2026-09-22 | 無摩擦防誤觸與撤回 (Phase 3 全系統覆蓋) | 完成採購 (PO Draft/Submit Undo)、訂單 (Confirm Undo/虛擬鎖庫釋放/出貨確認彈窗)、會計 (手動傳票紅字反向沖銷 REV-JE-xxx)、CRM (商機草稿 Undo/贏單轉單確認彈窗)；全套單元與整合測試 138/138 PASS，架構邊界 0 違規 | PASS |
| 2026-09-22 | 無摩擦防誤觸與撤回 (Playwright Headed 視窗端到端全量驗收) | 實施 Headed 模式（headless=False, slow_mo=300ms）真實瀏覽器彈窗，全面端到端驗收 7 大情境（Toast 懸停/倒數/手動關閉、多倉調撥撤回與流水復原、採購草稿撤銷/下訂撤回/入庫防呆確認、訂單鎖庫撤回/出貨不可逆確認彈窗/發票開立無撤回、手動會計傳票 REV- 反向沖銷與借貸平衡、CRM 商機建立撤回/贏單轉 ERP 訂單確認彈窗、SQLite 唯增帳本不可竄改與全模組無中斷導覽），修復 HTMX 跨表解析與 templateFragments，test_playwright_undo_comprehensive.py 1/1 PASS，check_boundaries.py 0 違規 | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 1 純前端微互動與字串精簡) | 完成多倉低量按鈕合併 (⚠️ 低於安全量 • 一鍵下單 →)、調撥雙倉即時互斥與自動對調 Vanilla JS、商機預估物料明細全面改為選填與數量歸 1、報價單預設數量歸 1、出貨單/A4出貨單正名、清除「原廠供應商」寫死字串；測試套件更新並通過 (138/138 PASS)，check_boundaries.py 0 違規 | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 1 Headed Playwright E2E 驗收) | 實施 Headed 模式真實 Chromium 視窗全量驗收 5 大情境：庫存低量合併按鈕無原廠供應商字串、雙倉調撥互斥與自動對調 (Auto-Swap)、CRM 商機物料選填與自訂總額、報價單項次 1 & 2 預設數量重設為 1、訂單與出貨單名詞正名 (`🏷️ 出貨單`/`📄 A4 出貨單`) 與彈窗校驗，test_playwright_iteration0922_batch1.py 5/5 PASS | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 2 CRM 轉單明細繼承與文件 PDF 半形化) | 完成贏單轉 ERP 彈窗優先繼承報價單物料清冊、小計與單號展示，消除「無特定物料明細」Bug；PyMuPDF/DOCX 英數符號半形化與 helv 字型收斂；單元與整合測試 (140/140 PASS) 與 Headed Playwright E2E 測試 (test_playwright_iteration0922_batch2.py 1/1 PASS)，check_boundaries 0 違規 | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 3 訂單出貨倉與採購目標倉多倉流轉架構) | 完成 sales_orders 與 purchase_orders 之 warehouse_id 欄位擴充與領域模型/服務改裝、採購指定進貨倉開單與驗收彈窗預設、CRM 贏單轉單指定出貨倉、訂單鎖庫/一鍵出貨/拆批出貨依指定倉庫流轉扣庫，多倉庫存隔離驗證；全套單元與整合測試 (142/142 PASS)、Headed Playwright E2E 測試 (test_playwright_iteration0922_batch3.py PASS)、check_boundaries 0 違規 | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 4 全域通知統一與撤回機制完備) | 完成 CRM 商機階段推進 Toast OOB 與階段撤回 (/crm/deals/{id}/stage/undo)、報價單建立 Toast OOB 與報價單撤回 (/crm/quotes/{id}/undo)、客戶建立/更新 Toast OOB 統一；完成採購驗收入庫紅字退庫沖銷 (revert_goods_receipt)、庫存負數防呆、移動平均成本還原、會計傳票反向沖銷與 AP 註銷；徹底消滅 crm.html 與 procurement.html 舊版靜態綠框；單元與整合測試全數通過 (116/116 PASS)，check_boundaries.py 0 違規 | PASS |
| 2026-09-22 | 體驗優化迭代 (Batch 4 Headed Playwright E2E 驗收) | 實施 Headed 模式真實 Chromium 視窗全量驗收 7 大情境：CRM 商機階段推進與 Toast 撤回回到 LEAD、報價單建立與 Toast 撤回報價單回到 DISCOVERY、採購驗收入庫與 Toast 撤回入庫回到待到貨、負數紅字庫存流水沖銷、會計 AP 註銷與傳票 REVERSAL 沖銷、/crm 與 /procurement 100% 無舊版靜態綠框全由 #toast-container 掌管，test_playwright_iteration0922_batch4.py 7/7 PASS | PASS |
| 2026-09-23 | Iteration 0923 (Batch 1 純前端微互動、報表對齊與 Toast 多行自適應) | 完成報價單 Modal State 乾淨重置 (form.reset)、庫存狀態按鈕精簡為「⚠️ 低於安全量」、財務報表中心 4 方塊 1:1 對齊 Excel 4 頁籤並升級字級排版、Toast 解除 truncate 改為 break-words 多行自適應；新增 test_iteration0923_batch1.py (4/4 PASS)，全系統 116/116 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-23 | Iteration 0923 (Batch 2 訂單客戶辨識、CRM 贏單自動鎖庫與 BOM 批次撤回) | 完成 CRM 贏單自動調用 confirm_order 鎖定虛擬庫存（落實下單即鎖庫）、OrderRowDTO 關聯 crm_contacts 顯示真實公司名 (CUST-xxxx)、BOM 分割自動建立 PO 支援一鍵撤回 (/procurement/bom/create-pos/undo)；新增 test_iteration0923_batch2.py (3/3 PASS)，全系統 123/123 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-23 | Iteration 0923 (Batch 3 會計防誤觸彈窗、發票防重與 PDF 嚴格半形化) | 完成會計 AR/AP 沖銷 Tailwind 二階確認彈窗 (消滅 Chrome 原生對話框)、指定資金帳戶 (1101/1102) 拋轉傳票、進項發票 invoice_number 防重查驗阻斷、PDF 向量文字全域半形化 (to_half_width)；新增 test_iteration0923_batch3.py (5/5 PASS)，全系統 128/128 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-23 | Iteration 0923 (Playwright Headed UI 全量端到端驗收) | 依指令啟動 Headed 模式（headless=False, slow_mo=300ms）真實視窗全量驗收 3 大批次 9 大場景：報價單 Modal State 乾淨重置 (0 殘留)、低庫存按鈕精簡 ('⚠️ 低於安全量')、4合1 財務報表 1:1 Sheet 對齊、CRM 贏單自動 CONFIRMED 鎖庫、訂單清單公司名稱 (CUST-xxxx) 呈現、BOM 分割開單批次撤回、會計 AR/AP 沖銷二階 Tailwind 系統彈窗 (消滅 Chrome confirm) 與 1102 銀行存款入帳、進項發票防重複註冊 (ALREADY_RECORDED 按鈕禁用)；test_playwright_iteration0923.py 全數 PASS，check_boundaries.py 0 違規 | PASS |
| 2026-09-23 | Bug Fixes 0923 (Batch 1 體驗優化與報表歸位) | 完成報價單動態增刪品項 (解除2項限制)、CRM 推進滾動跳底修復與結案折疊收合、轉單目標行高亮脈衝與平滑滾動 (/orders?highlight=)、庫存盤點底冊 Excel 匯出搬移至 /inventory，全系統 162/162 單元與整合測試通過，check_boundaries 0 違規 | PASS |
| 2026-09-23 | Bug Fixes 0923 (Batch 2 拆批多倉與出貨單連印) | 完成拆批出貨彈窗倉庫下拉選單 (partial_ship_modal.html)、跨倉拆批扣庫與虛擬鎖庫一致性核銷 (fulfill_stock_lock)、100x150 普通出貨單支援多批連續分頁列印 (generate_shipping_labels_pdf)，新增 test_batch2_split_shipping.py (3/3 PASS)，全系統 165/165 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-23 | 系統易用性與履約收斂 (Playwright Headed UI 6大情境全量驗收) | 依據 iteration-0923-1455-verification.md 啟動 Headed 模式（headless=False, slow_mo=350ms）真實 Chromium 視窗全量驗收 6 大情境：1. 報價單動態增刪 3+ 品項/垃圾桶刪除/動態試算/推進 PROPOSAL/DOCX 與 PDF 產出；2. CRM 平穩滾動/WON 與 LOST 手風琴抽屜與 max-h-[800px]；3. 贏單轉單 SO-xxxx ➜ 導航平滑滾動與 Amber Ring 光暈脈衝聚焦；4. 拆批出貨指定 WH-STORE/跨倉扣庫/歷程出貨倉標註/WH-MAIN 鎖庫同步釋放；5. 拆兩批出貨之 100x150 普通出貨單連續 2 頁列印與單批單頁列印；6. 庫存頁匯出盤點底冊 Excel (.xlsx) 與會計報表中心收斂為 3 大純財務報表；test_playwright_iteration0923_1455.py 全數 PASS | PASS |
| 2026-09-23 | 前端測試性規範與測試合約架構落地 | 完成全系統核心 HTML/Jinja2 樣板 data-testid 規格化埋設、建立 tests/ui_manifest.yaml 元件清冊 SSOT、實作 tests/test_ui_manifest_contract.py 自動化合約適應度函式 (3/3 PASS)、開發 scripts/dump_a11y_tree.py Playwright 極速無障礙與 ARIA 樹探勘工具，架構邊界 0 違規全數 PASS | PASS |
| 2026-09-24 | BOM 導入轉採購單防呆與四級成本重構 | 完成 BOM 自帶供應商/單價解析 (BomExcelParser)、四級成本回退鏈 (BomComparisonService.compare_bom: 歷史最低價 ➔ BOM自帶 ➔ 主檔標準成本 ➔ None待詢價)、消除 0 元估算扭曲；採購分割開單剛性過濾未指定廠商與單價為 0 品項 (create_pos_from_bom_endpoint)、全無效拋 400 阻擋、部分有效開單並於 Toast 回報排除筆數；UI 標註待詢價與開單狀態；新增單元與整合測試，全系統 171/171 PASS，架構邊界 0 違規 | PASS |
| 2026-09-24 | 測試架構物理分流與 Playwright 隔離硬性防呆 | 完成 tests/ 物理隔離分流（tests/unit/ 42 檔與 tests/e2e/ 13 檔）、拆分 tests/e2e/conftest.py 解除全域 Playwright 模組載入污染、配置 pytest.ini (testpaths=tests/unit, norecursedirs=e2e, pythonpath=.)，bare pytest 預設僅執行極速單元測試 (171/171 PASS 耗時數秒)，指定 pytest tests/e2e 才收集並啟動真實瀏覽器 (13/13 PASS)，check_boundaries 0 違規 | PASS |
| 2026-09-24 | BOM 歷史最優報價過濾修復 (排除無效佔位廠商與 0 元紀錄) | 修復 BomComparisonService.get_supplier_quotes_for_sku 歷史報價查詢：加入 poi.unit_cost > 0、排除佔位名稱 ('未指定供應商' / None / 空白) 與已取消採購單 (po.status != 'CANCELLED')；取消資料庫歷史殘留之 6 張未指定供應商佔位草稿單；新增 test_historical_quotes_filter_zero_cost_and_placeholder_suppliers (172/172 PASS)，確認新入庫「台科電子」成功匹配為最優推薦 | PASS |
| 2026-09-24 | 分倉安全存量架構與多倉行內編輯 (Per-Warehouse Safety Stock) | 建立 warehouse_stock_levels 表與 Alembic 遷移 (002)，解耦 products.safety_stock 全域單一數值；調撥與採購驗收首次進倉預設安全量 10 與自訂設定支援；多倉庫存頁 (/inventory) 支援 HTMX 零構建行內點擊編輯與即時 OOB 狀態標籤刷新；排程 scan_low_safety_stock 消除未配貨分倉 CROSS JOIN 虛警；新增 test_warehouse_safety_stock.py (6/6 PASS)，全系統 178/178 PASS，架構邊界 0 違規 | PASS |
| 2026-09-24 | 體驗優化迭代 (Batch 1 庫存與儀表板名稱優先翻轉) | 完成 dashboard.html 低存量卡片品名大字置頂與 SKU 弱化標籤化、近期訂單表頭正名為「客戶名稱 / 下單時間」、stock_table.html 與 stock_row.html 欄位排版翻轉為商品名稱優先於品號 (SKU)；新增 test_iteration0924_batch1.py (3/3 PASS)，全系統 181/181 PASS，架構邊界 0 違規 | PASS |
| 2026-09-24 | 體驗優化迭代 (Batch 2 採購中心名稱優先翻轉) | 完成 procurement.html 開單物料選項改為「品名 (SKU) - 目前成本」、表頭正名為「採購物料 (品名 / SKU)」、po_row.html 物料列品名加粗在前且 SKU 弱化標籤置於括號、receive_po_modal.html 入庫彈窗與 procurement_bom_result.html BOM 比價表品名優先；新增 test_iteration0924_batch2.py (4/4 PASS)，全系統 185/185 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-24 | 體驗優化迭代 (Batch 3 銷售訂單與履約彈窗名稱優先翻轉) | 完成 orders.html 表頭正名為「客戶名稱 / 下單時間」、ship_confirm_modal.html 與 partial_ship_modal.html 抬頭顯示「客戶：客戶名稱 (ID)」及物料明細「商品品名 / SKU」品名加粗在前、deliveries_modal.html 表頭正名為「商品品名 (SKU)」與歷程物料品名優先；新增 test_iteration0924_batch3.py (5/5 PASS)，全系統 190/190 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-24 | 體驗優化迭代 (Batch 4 外部通路、報價單與會計名稱翻轉) | 完成 LINE Bot 收據卡與查單卡優先顯示中文品名、QuoteDocumentEngine Word 與 PDF 報價單明細表頭正名為「商品名稱 / 規格料號 (SKU)」且品名欄位優先、accounting.html AR 與 AP 帳齡表將客戶/廠商名稱前置並粗體強化；新增 test_iteration0924_batch4.py (4/4 PASS)，全系統 194/194 PASS，check_boundaries 0 違規 | PASS |
| 2026-09-24 | 高層級名稱翻轉 (Playwright Headed UI 4大情境全量驗收) | 依據 iteration-0924-high-level-name.md 啟動 Headed 模式（headless=False, slow_mo=300ms）真實視窗端到端全量驗收 4 大情境：1. 儀表板低存量品名粗體大字置頂與 SKU 弱化標籤化、近期訂單表頭客戶名稱、多倉庫存總覽表格欄位順序商品名稱優先於品號；2. 採購開單表頭正名與物料選單「品名 (SKU) - 成本」、採購單列品名粗體在前、驗收入庫彈窗與 BOM 比價結果品名優先；3. 訂單清單客戶名稱 (CUST-xxxx)、一鍵出貨確認彈窗、拆批出貨彈窗與出貨單歷程彈窗全數預解析中文品名與客戶名稱；4. 會計 AR/AP 帳齡表客戶/廠商名稱排於單號之前並加粗、CRM 報價單 DOCX 與 PDF 欄位排版正名「商品名稱」在前、LINE Bot 收據與查單卡優先顯示中文品名；新增 test_playwright_iteration0924.py (1/1 PASS)，check_boundaries 0 違規 | PASS |










