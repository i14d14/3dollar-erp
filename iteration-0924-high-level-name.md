# Iteration Plan: High-Level Human-Readable Name Priority (0924)

## 1. Executive Summary & Design Principles

### 1.1 Objective
Standardize the visual presentation across Dura ERP, TanGii Accounting, LiLai CRM, and LINE Bot customer channels so that human-readable entities (**Customer Name**, **Product Name**) are consistently prioritized as the primary visual anchor, with machine identifiers (**Customer ID**, **SKU**) positioned as secondary, muted attributes.

### 1.2 Architectural Guardrails & Decision Rationale
1. **Name Primary, ID Secondary (Best Practice)**:
   - Primary label: Prominent, high-contrast human-readable name (e.g. `台灣有機糙米`, `台積電股份有限公司`).
   - Secondary label: Muted, smaller monospace tag or badge preserving the exact identifier (e.g. `(SKU-001)`, `(CUST-002)`).
2. **Preserve Business Type Prefixes (Anti-Pattern Avoidance)**:
   - Strictly prohibit stripping prefixes (e.g., stripping `CUST-` or `SKU-`) on the UI.
   - Prefixes prevent cross-department communication ambiguity (avoiding confusion between Customer 101, Order 101, and Product 101), maintain global copy-paste search integrity, and prevent errors on printed physical documents.
   - Visual compromise: Weaken prefix prominence via typography (`text-xs text-slate-400 font-mono`) rather than truncating characters.
3. **Contract-First via View DTOs (Zero Raw Entity Leakage)**:
   - Comply with `AGENTS.md` Rule 5: Modals and presentation partials must receive tailored View DTOs containing pre-resolved names rather than raw domain models lacking text descriptions (e.g., domain `OrderItem` only holds `sku`).

---

## 2. Blast Radius & Risk Assessment

| Dimension | Impact Level | Analysis |
| :--- | :--- | :--- |
| **Database Schema** | **Zero (0%)** | No database migrations, no column additions, no altered constraints or foreign keys. |
| **Domain Services** | **Zero (0%)** | No modifications to financial posting, FIFO/moving-average costing, or inventory lock mechanics. |
| **View Service & DTOs** | **Low-Medium** | Enriching `WebViewService` query mappings to pass `product_name` and `customer_name` to fulfillment modals. |
| **UI Presentation** | **Medium** | Adjusting column ordering, table headers, and flex containers in ~8 Jinja2 HTML templates. |
| **External Channels** | **Low** | Enhancing LINE Bot Flex receipt bubbles to show product names before SKUs. |
| **Test Suite** | **Low** | Verifying string match assertions across unit and web route tests. |

---

## 3. Four-Batch Execution Breakdown

```
[Batch 1: Inventory & Dashboard] ──> [Batch 2: Procurement] ──> [Batch 3: Orders & Modals] ──> [Batch 4: LINE & Accounting]
```

### Batch 1: Inventory & Executive Dashboard (UI Read-Only)
* **Goal**: Establish the primary-name / secondary-ID visual pattern on high-visibility read screens.
* **Target Files**:
  - `src/channel_ui/web/templates/dashboard.html`
  - `src/channel_ui/web/templates/inventory.html`
  - `src/channel_ui/web/templates/partials/stock_row.html`
  - `src/channel_ui/web/templates/partials/stock_table.html`
* **Changes**:
  1. `dashboard.html`: In Low Stock Alert cards, elevate `product_name` to the primary bold title; render `sku` as a secondary muted monospace pill next to warehouse name.
  2. `stock_table.html`: Reorder table columns: `倉庫 (Warehouse)` $\rightarrow$ `商品名稱 (Product Name)` $\rightarrow$ `品號 (SKU)` $\rightarrow$ `現存量` $\rightarrow$ `鎖定量` $\rightarrow$ `可用量` $\rightarrow$ `安全存量`.
  3. `stock_row.html`: Swap column order so that `item.product_name` renders before `item.sku`.
* **Testing Scope**:
  - `pytest tests/test_inventory_service.py tests/test_web_routes.py -k "inventory or dashboard"`

---

### Batch 2: Procurement Center (Forms & Detail Rows)
* **Goal**: Enable rapid supplier item selection with clear product names in purchase order workflows.
* **Target Files**:
  - `src/channel_ui/web/templates/procurement.html`
  - `src/channel_ui/web/templates/partials/po_row.html`
  - `src/channel_ui/web/view_service.py`
* **Changes**:
  1. `procurement.html`:
     - In `#po-items-table`, update `<option>` format to `{{ p.name }} ({{ p.sku }}) - 目前成本: {{ p.cost_price_formatted }}`.
     - Update table header from `採購物料 (SKU / 品名)` to `採購物料 (品名 / SKU)`.
     - Ensure client-side dynamic row addition (`addProcurementItemRow`) reflects the new format.
  2. `po_row.html`:
     - Reorder item line display: render `item.product_name` in bold text first, followed by `item.sku` in muted monospace tag.
* **Testing Scope**:
  - `pytest tests/test_procurement_service.py tests/test_web_routes.py -k "procurement"`

---

### Batch 3: Sales Orders & Fulfillment Modals (Core Work)
* **Goal**: Eliminate raw domain model leakage in order shipment dialogs and ensure operators see product and customer names during critical shipping actions.
* **Target Files**:
  - `src/channel_ui/web/routes/orders.py`
  - `src/channel_ui/web/view_service.py`
  - `src/channel_ui/web/templates/orders.html`
  - `src/channel_ui/web/templates/partials/order_row.html`
  - `src/channel_ui/web/templates/partials/ship_confirm_modal.html`
  - `src/channel_ui/web/templates/partials/partial_ship_modal.html`
  - `src/channel_ui/web/templates/partials/deliveries_modal.html`
* **Changes**:
  1. `orders.html`: Update table header from `客戶代號 / 下單時間` to `客戶名稱 / 下單時間`.
  2. `order_row.html`: Maintain `{{ order.customer_name }} ({{ order.customer_id }})` pattern with clear styling.
  3. `routes/orders.py` & `view_service.py`:
     - Refactor `get_ship_confirm_modal_endpoint` and `get_partial_ship_modal_endpoint` to construct a dedicated modal DTO or enriched context mapping `sku` $\rightarrow$ `product_name` and `customer_id` $\rightarrow$ `customer_name`.
     - Refactor `get_order_deliveries_modal_endpoint` to resolve `product_name` for each allocation item.
  4. `ship_confirm_modal.html` & `partial_ship_modal.html`:
     - Header: Display `客戶：{{ customer_name }} ({{ order.customer_id }})`.
     - Item Grid: Header to `商品品名 / SKU`; render `item.product_name` as primary bold text with `item.sku` as secondary monospace subtitle.
  5. `deliveries_modal.html`:
     - Table header to `商品品名 (SKU)`; row item shows `alloc.product_name` with `(alloc.sku)`.
* **Testing Scope**:
  - `pytest tests/test_order_service.py tests/test_partial_shipping.py tests/test_web_routes.py -k "order or ship"`

---

### Batch 4: External Channels, Quotation Documents & Accounting
* **Goal**: Align customer-facing LINE notifications, CRM quote templates, and accounting receivables.
* **Target Files**:
  - `src/channel_ui/line_bot/flex_templates.py`
  - `src/channel_ui/line_bot/service.py`
  - `src/extended_core/crm/documents/quote_document_engine.py`
  - `src/channel_ui/web/templates/accounting.html`
* **Changes**:
  1. `flex_templates.py`:
     - In `build_order_receipt_flex` and `build_order_status_flex`, update item text to display `item.product_name` (falling back to SKU if name absent) with quantity, rather than raw SKU strings.
  2. `quote_document_engine.py`:
     - In Word/PDF generation, adjust line item table headers: `["項次", "商品名稱", "規格料號 (SKU)", "數量", "單價 (NT$)", "小計 (NT$)"]`.
  3. `accounting.html` & `view_service.py`:
     - In AR Aging table and settlement modal, resolve `customer_id` via `crm_contacts` so `partner_name` displays `客戶名稱 (CUST-xxxx)` (falling back to ID if unmapped), prioritizing human-readable customer name before AR ID.
  4. `accounting.html`, `accounting_service.py` & `routes/accounting.py`:
     - In journal entries voucher table, prioritize `account_name` before `account_code`, format manual voucher selects to `名稱 (代碼)`, and enrich `AR_RECEIPT` voucher descriptions with `公司名稱 (CUST-xxxx)`.
* **Testing Scope**:
  - `pytest tests/test_line_bot_e2e.py tests/test_crm_service.py tests/test_accounting_service.py`
  - Architecture fitness check: `python check_boundaries.py`

---

## 4. Verification Protocol (Action $\rightarrow$ Expected Outcome)

| Batch | Action (動作) | Expected Outcome (預期) |
| :--- | :--- | :--- |
| **Batch 1** | Navigate to `/inventory` and `/` (Dashboard). | 1. Dashboard Low Stock cards show product name as primary bold title, SKU secondary.<br>2. Inventory table shows Product Name before SKU column. |
| **Batch 2** | Navigate to `/procurement` and open SKU select dropdown. | 1. Dropdown options display `商品名稱 (SKU)` format.<br>2. Recent PO row displays product name before SKU. |
| **Batch 3** | Navigate to `/orders` and click 「一鍵出貨 (扣庫)」 or 「拆批出貨」. | 1. Modal header displays Customer Name with ID in parentheses.<br>2. Modal items table lists Product Name in bold with SKU sub-label. |
| **Batch 4** | Run LINE Bot simulated checkout & inspect `/accounting` AR aging. | 1. Receipt Flex card lists natural product names in shopping summary.<br>2. AR Aging table prominently displays customer name. |
| **All** | Run `python check_boundaries.py` and test suite. | Zero architectural boundary violations; 100% test pass rate. |
