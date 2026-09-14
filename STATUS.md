# 3Dollar ERP 專案即時狀態 (Project Status Living SSOT)

## 專案進度儀表板 (Dashboard)

* **專案名稱**：3Dollar ERP (三元科技產品架構複製)
* **當前衝刺階段**：Day 1 / 核心架構與資料基底 (Core Architecture & Data Foundations)
* **整體完成度**：0% [░░░░░░░░░░]
* **當前焦點任務**：專案骨架建立、資料庫 Schema 定義、架構防護線設定
* **當前阻礙 (Blockers)**：無
* **最後更新時間**：2026-09-14

---

## 里程碑詳細追蹤 (Milestone Tracking)

### [ ] Day 1: 核心架構與資料基底 (Core Architecture & Data Foundations)
- [ ] **Task 1.1**: 專案結構初始化（建立 Modular Monolith 領域模組骨架與基礎配置）
- [ ] **Task 1.2**: 關聯式資料庫 Schema 建模（多倉庫存、單據流轉、交易日誌、借貸傳票）
- [ ] **Task 1.3**: 設定架構邊界防護與相依性檢查器（dependency-cruiser 規則防護）
- [ ] **Task 1.4**: 實作基礎 Data Access / Repository 層與資料庫連接驗證測試

### [ ] Day 2: Dinkoko ERP 核心流程 (Core Order & Inventory Engine)
- [ ] **Task 2.1**: 多倉庫存管理與調撥邏輯（含安全庫存警示與鎖庫扣庫機制）
- [ ] **Task 2.2**: 採購進貨流程與入庫單據處理
- [ ] **Task 2.3**: 訂單管理與出貨扣庫一條龍（一鍵轉出貨單、托運單）
- [ ] **Task 2.4**: 台灣電子發票開立串接與「訂單-出貨-發票-應收」四單自動對帳關聯
- [ ] **Task 2.5**: 每日自動化排程引擎（庫存同步、出貨通知批次觸發）

### [ ] Day 3: TanJee 會計與記帳系統 (Accounting & Financial Intelligence)
- [ ] **Task 3.1**: ERP 單據事件驅動自動拋轉會計傳票（借貸平衡檢查）
- [ ] **Task 3.2**: 應收／應付帳款模組與帳齡分析、催收清單生成
- [ ] **Task 3.3**: 專案與部門成本分攤核算引擎
- [ ] **Task 3.4**: 四大財務報表即時產出（損益表、資產負債表、現金流量表、試算表）
- [ ] **Task 3.5**: 多幣別即時匯率換算與匯兌損益計算

### [ ] Day 4: DanLee CRM 前段商機 (CRM Pipeline & Document Center)
- [ ] **Task 4.1**: 客戶名單管理、互動時間軸與 Lead Scoring 自動評分
- [ ] **Task 4.2**: 智能文件中心（合約 DOCX 範本動態套印、報價單 PDF 產出與版本控管）
- [ ] **Task 4.3**: 跟進防漏提醒機制（Day 0 / 3 / 7 自動通知）與 Email 互動追蹤
- [ ] **Task 4.4**: 商機成交管線（成交確認後一鍵推進 ERP 生成待處理訂單）

### [ ] Day 5: LINE Bot 智能通路入口 (Channel & UI Conversation Layer)
- [ ] **Task 5.1**: LINE Messaging API v3 Webhook 骨架與簽名驗證
- [ ] **Task 5.2**: LINE Bot 智能下單（Flex Message 商品型錄、購物車與穿透寫入 ERP 訂單）
- [ ] **Task 5.3**: LINE Bot 智能客服（關鍵字與常見問題導引、無縫真人轉接介面）
- [ ] **Task 5.4**: LINE Bot 智能打卡（LIFF v2 GPS 定位打卡、ID Token 驗證、請假加班簽核）
- [ ] **Task 5.5**: LINE Rich Menu 圖文選單配置與分眾切換

### [ ] Day 6: AI 增強外掛與檔案自動化 (AI Wrapper & File Automation)
- [ ] **Task 6.1**: 發票 OCR 批量辨識與採購單自動建檔
- [ ] **Task 6.2**: BOM 表 Excel 批量解析與多通路採購比價自動化
- [ ] **Task 6.3**: 銀行網銀對帳單（Excel/CSV）明細與系統應收應付自動勾稽
- [ ] **Task 6.4**: Agentic RAG 內部知識庫（DOCX/PDF 規範手冊切片向量化與問答）
- [ ] **Task 6.5**: 獨立租戶雲端部署機制與每月客製功能點數管理

### [ ] Day 7: 全鏈路端到端整合與驗收 (E2E Integration & Demo Readiness)
- [ ] **Task 7.1**: 全鏈路 E2E 貫穿驗證（潛客 -> 報價 -> LINE下單 -> ERP出貨扣庫 -> 會計傳票與財報）
- [ ] **Task 7.2**: 邊界與異常容錯測試（負庫存防止、重試等冪性、第三方平台逾時）
- [ ] **Task 7.3**: 展示環境資料種子（Seed Data）與快速啟動腳本配置
- [ ] **Task 7.4**: 最終驗收報告產出與交付文檔完備

---

## 驗收日誌 (Verification Log)

| 時間戳記 | 階段 / 任務 | 驗收內容與成果 | 狀態 |
| :--- | :--- | :--- | :---: |
| 2026-09-14 | 初始化 | 完成專案 Roadmap 與 Living SSOT 狀態追蹤機制建置 | PASS |
| 2026-09-14 | 版本控管 | 初始化 Git 儲存庫與配置多語言環境 .gitignore | PASS |
