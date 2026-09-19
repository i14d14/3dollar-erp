# 3Dollar ERP 專案即時狀態 (Project Status Living SSOT)

> [!IMPORTANT]
> **SSOT 邊界守則**：本文件為**專案執行狀態與進度 (Where & Now)** 的唯一真相來源。
> 所有規格標準、雙軌研發邊界（青春版 MVP 裁切 vs 樂觀完整版）與架構插槽規範，唯一權威來源為 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)。任何任務開工前，必須同時查閱此處進度與 `ROADMAP.md` 規格。

### 專案進度儀表板 (Dashboard)

* **專案名稱**：3Dollar ERP (三圓科技產品架構複製)
* **當前衝刺階段**：Day 5 衝刺中 (LINE Bot 智能通路入口 - 待完成)
* **研發策略模式**：雙軌制（青春版基準 MVP 交付優先，架構插槽預留樂觀完整版）
* **整體完成度**：57.1% [█████░░░░░]
* **當前焦點任務**：Day 5 LINE Bot 智能通路入口（待完成真機對接與上線驗證）
* **當前阻礙 (Blockers)**：無阻礙 (None)
* **最後更新時間**：2026-09-19

---

## 里程碑詳細追蹤 (Milestone Tracking)

### [x] Day 1: 核心架構與資料基底 (Core Architecture & Data Foundations) - 已驗收
- [x] **Task 1.1**: 專案結構初始化（Modular Monolith 領域模組骨架與基礎配置）
- [x] **Task 1.2**: 關聯式資料庫 Schema 建模（多倉庫存、單據流轉、交易日誌、借貸傳票）
- [x] **Task 1.3**: 設定架構邊界防護與相依性檢查器（AST 規則防護與 test_architecture_rules.py）
- [x] **Task 1.4**: 實作基礎 Data Access / Repository 層與資料庫連接驗證測試

### [x] Day 2: Dinkoko ERP 核心流程 (Core Engine) - 已驗收
> 規格詳細定義：[`ROADMAP.md#第一層核心層dinkoko-erp---營運與單據中樞`](file:///d:/3dollar_erp/ROADMAP.md#第一層核心層dinkoko-erp---營運與單據中樞)
- [x] **Task 2.1**: 多倉庫存管理與調撥邏輯（落實 ROADMAP 青春版 MVP：主倉/門市雙倉流水、虛擬鎖庫、防負庫存）
- [x] **Task 2.2**: 採購進貨流程與入庫單據處理（落實 ROADMAP 青春版 MVP：PO $\rightarrow$ GRN 移動平均成本計價）
- [x] **Task 2.3**: 訂單管理與出貨扣庫一條龍（落實 ROADMAP 青春版 MVP：一鍵轉出貨單 DO、PDF 標籤）
- [x] **Task 2.4**: 台灣電子發票開立與四單自動對帳（落實 ROADMAP 青春版 MVP：MIG 3.2.1 MockProvider、SO 1:1 DO 1:1 INV 1:1 AR 剛性對帳）
- [x] **Task 2.5**: 每日自動化排程引擎（落實 ROADMAP 青春版 MVP：低安全存量掃描、逾期應收單據掃描）
- [x] **Task 2.6**: Dinkoko ERP 營運管理 Web GUI 垂直切片（落實 Zero-Build SSR：儀表板 KPI、訂單與出貨 HTMX 局部更新、物流標籤與發票 PDF 串流、多倉調撥表）

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

### [ ] Day 5: LINE Bot 智能通路入口 (Channel & UI) - 未完成 (待真機驗收)
> 規格詳細定義：[`ROADMAP.md#2-外部客戶輕量通路line-bot-智能對話入口`](file:///d:/3dollar_erp/ROADMAP.md#2-外部客戶輕量通路line-bot-智能對話入口)
- [x] **Task 5.1**: Webhook 簽名防偽與事件分流（HMAC-SHA256 數位簽名檢驗、MessageEvent 與 PostbackEvent 派發）
- [x] **Task 5.2**: Flex Message 視覺卡片構建器（遵循 LINE 官方 Pydantic 模型，商品型錄輪播卡、訂單成立收據卡、出貨/發票進度卡）
- [x] **Task 5.3**: 一鍵穿透下單與鎖庫流程（Postback 一鍵下單 `channel_id="LINE"`，呼叫 OrderService 建立訂單並鎖庫，庫存不足自動取消並回傳繁中防呆通知）
- [x] **Task 5.4**: 自助文字查單與進度回報（解析「查單 SO-xxx」，查詢訂單狀態、出貨單 DO、物流追蹤碼與電子發票號碼）
- [x] **Task 5.5**: 緊湊型 Rich Menu 圖文選單配置規範（2500x843 畫布、3 格佈局 JSON 與 Pydantic 模型產生器）
- [x] **Task 5.6**: 全鏈路離線仿真測試體系（`LineMessagingPort` 與 `MockLineMessagingAdapter`，無外部網路/真實密鑰依賴之 E2E 仿真測試 14/14 PASS）
- [ ] **Task 5.7**: 真機對接與上線驗證（.env 換發 Stateless Token v3、Cloudflare Quick Tunnel TPE01 Webhook 綁定、LINE OA 後台關閉自動回覆、2500x843 亮色極簡 Rich Menu 上傳綁定、手機端 @337keuin E2E 實機抽測）

### 後續衝刺清單 (Day 6 ~ Day 7 待啟動)
> 具體業務規格、驗收標準與雙軌裁切定義嚴格收錄於 [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md)，此處不展開單一行標題以杜絕假性滿足：
* **Day 6**: AI 增強外掛與檔案自動化（BOM 表 Excel 解析比價、原生 PDF 電子發票抽取、報表匯出）
* **Day 7**: 全鏈路端到端整合與驗收（商機 $\rightarrow$ 報價 $\rightarrow$ 下單 $\rightarrow$ 出貨扣庫 $\rightarrow$ 會計出表 E2E 驗收與種子資料）


---

## 驗收日誌 (Verification Log)

| 時間戳記 | 階段 / 任務 | 驗收內容與成果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- |
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



