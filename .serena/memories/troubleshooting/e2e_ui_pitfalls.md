# E2E & UI 垂直切片踩坑與修復經驗 (滿血版第 1 批)

1. **UI 垂直切片需同步交付**：後端新增拆批出貨等 API 時，必須同步補齊前端 UI 互動元件 (如 partial_ship_modal.html 與對應路由)，避免僅有 API 無法進行真實真人操作。
2. **HTML5 原生驗證攔截問題**：表單輸入框若設有 max 屬性，在測試超額輸入時會被 Chromium 原生驗證阻擋提交，導致無法抵達後端觸發繁體中文 Toast 提示。需在表單標籤加入 `novalidate` 確保後端驗證與防呆機制正常觸發。
3. **SQLite 舊 DB 約束遺留**：早期建立的 erp.db 若欄位帶有 1:1 時代的 UNIQUE 約束 (如 delivery_orders.order_id)，在升級為 1:N 關聯時會造成唯一性衝突，需確保資料庫結構同步重建/遷移。
4. **Playwright 子字串斷言盲點**：`PARTIALLY_SHIPPED` 包含 `SHIPPED`，若使用包含匹配會導致狀態判定過早通過進而造成時序錯誤。應改用精準比對 (如 `span:text-is('SHIPPED')`)。