-- 3Dollar ERP Core Relational Schema (SQLite Compatible with ANSI SQL)
PRAGMA foreign_keys = ON;

-- 1. Warehouses & Products
CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_unit TEXT NOT NULL DEFAULT 'PCS',
    cost_price NUMERIC NOT NULL DEFAULT 0,
    selling_price NUMERIC NOT NULL DEFAULT 0,
    safety_stock INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Stock Ledger (Append-Only Double Entry Ledger)
CREATE TABLE IF NOT EXISTS stock_ledger (
    ledger_id TEXT PRIMARY KEY,
    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
    sku TEXT NOT NULL REFERENCES products(sku),
    qty_delta NUMERIC NOT NULL,
    balance_after NUMERIC NOT NULL,
    unit_cost NUMERIC NOT NULL,
    reference_type TEXT NOT NULL, -- 'PURCHASE', 'SALE', 'TRANSFER', 'ADJUSTMENT'
    reference_id TEXT NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Stock Virtual Locks (Reserved inventory for pending orders)
CREATE TABLE IF NOT EXISTS stock_locks (
    lock_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
    sku TEXT NOT NULL REFERENCES products(sku),
    locked_qty NUMERIC NOT NULL,
    status TEXT NOT NULL DEFAULT 'LOCKED', -- 'LOCKED', 'RELEASED', 'FULFILLED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Procurement: Purchase Orders (PO) and Goods Receipt Notes (GRN)
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id TEXT PRIMARY KEY,
    supplier_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT', -- 'DRAFT', 'SUBMITTED', 'RECEIVED', 'CANCELLED'
    total_amount NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    po_item_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL REFERENCES purchase_orders(po_id) ON DELETE CASCADE,
    sku TEXT NOT NULL REFERENCES products(sku),
    qty NUMERIC NOT NULL,
    unit_cost NUMERIC NOT NULL,
    subtotal NUMERIC NOT NULL
);

CREATE TABLE IF NOT EXISTS goods_receipt_notes (
    grn_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Sales Orders (SO)
CREATE TABLE IF NOT EXISTS sales_orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'DIRECT', -- 'DIRECT', 'LINE', 'CRM'
    status TEXT NOT NULL DEFAULT 'DRAFT',   -- 'DRAFT', 'CONFIRMED', 'SHIPPED', 'COMPLETED', 'CANCELLED'
    total_amount NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_order_items (
    item_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES sales_orders(order_id) ON DELETE CASCADE,
    sku TEXT NOT NULL REFERENCES products(sku),
    qty NUMERIC NOT NULL,
    unit_price NUMERIC NOT NULL,
    subtotal NUMERIC NOT NULL
);

-- 6. Delivery Orders (DO) - One-click shipment
CREATE TABLE IF NOT EXISTS delivery_orders (
    do_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE REFERENCES sales_orders(order_id),
    warehouse_id TEXT NOT NULL REFERENCES warehouses(warehouse_id),
    tracking_number TEXT,
    shipped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Electronic Invoices (Taiwan MIG 3.2.1 Standardized Mock)
CREATE TABLE IF NOT EXISTS invoices (
    invoice_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE REFERENCES sales_orders(order_id),
    invoice_number TEXT NOT NULL UNIQUE, -- e.g., 'AB-12345678'
    random_code TEXT NOT NULL,           -- 4 digits
    tax_type TEXT NOT NULL DEFAULT '1',  -- '1': 應稅 5%, '2': 零稅率, '3': 免稅
    total_amount NUMERIC NOT NULL,
    tax_amount NUMERIC NOT NULL,
    buyer_tax_id TEXT,                  -- 8 digits or blank
    buyer_name TEXT,
    qrcode_l TEXT,
    qrcode_r TEXT,
    status TEXT NOT NULL DEFAULT 'ISSUED', -- 'ISSUED', 'VOID', 'ALLOWANCE'
    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Accounts Receivable (AR) & Accounts Payable (AP) - Cash Flow Control
CREATE TABLE IF NOT EXISTS accounts_receivable (
    ar_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL UNIQUE REFERENCES sales_orders(order_id),
    invoice_id TEXT NOT NULL REFERENCES invoices(invoice_id),
    customer_id TEXT NOT NULL,
    due_date DATE NOT NULL,
    amount NUMERIC NOT NULL,
    paid_amount NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'UNPAID', -- 'UNPAID', 'PARTIAL', 'PAID', 'OVERDUE'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts_payable (
    ap_id TEXT PRIMARY KEY,
    po_id TEXT NOT NULL REFERENCES purchase_orders(po_id),
    grn_id TEXT REFERENCES goods_receipt_notes(grn_id),
    supplier_name TEXT NOT NULL,
    due_date DATE NOT NULL,
    amount NUMERIC NOT NULL,
    paid_amount NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'UNPAID', -- 'UNPAID', 'PARTIAL', 'PAID', 'OVERDUE'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. TanGii (探吉) Accounting: Chart of Accounts & General Ledger
CREATE TABLE IF NOT EXISTS accounts (
    account_code TEXT PRIMARY KEY, -- '1101' 現金, '1144' 應收帳款, '1201' 存貨, '2144' 應付帳款, '4111' 銷貨收入, '5111' 銷貨成本
    account_name TEXT NOT NULL,
    account_type TEXT NOT NULL,    -- 'ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE'
    is_active INTEGER DEFAULT 1
);

-- Standard Chart of Accounts Seed (Taiwan GAAP / EAS)
INSERT OR IGNORE INTO accounts (account_code, account_name, account_type) VALUES
('1101', '現金', 'ASSET'),
('1102', '銀行存款', 'ASSET'),
('1144', '應收帳款', 'ASSET'),
('1201', '存貨', 'ASSET'),
('2144', '應付帳款', 'LIABILITY'),
('2201', '銷項稅額', 'LIABILITY'),
('3101', '業主資本', 'EQUITY'),
('4111', '銷貨收入', 'REVENUE'),
('5111', '銷貨成本', 'EXPENSE'),
('6101', '營業費用', 'EXPENSE');

CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id TEXT PRIMARY KEY,
    entry_date DATE NOT NULL,
    source_event TEXT NOT NULL,    -- 'ERP_FULFILLMENT', 'ERP_PROCUREMENT', 'MANUAL'
    reference_id TEXT NOT NULL,    -- e.g. order_id or grn_id
    description TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS journal_lines (
    line_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL REFERENCES journal_entries(entry_id) ON DELETE CASCADE,
    account_code TEXT NOT NULL REFERENCES accounts(account_code),
    debit NUMERIC NOT NULL DEFAULT 0,
    credit NUMERIC NOT NULL DEFAULT 0,
    CHECK (debit >= 0 AND credit >= 0 AND (debit > 0 OR credit > 0))
);

-- 10. LiLai (哩來) CRM: Contacts, Deals, Quotes
CREATE TABLE IF NOT EXISTS crm_contacts (
    contact_id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    tax_id TEXT,
    contact_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_deals (
    deal_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES crm_contacts(contact_id),
    title TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'LEAD', -- 'LEAD', 'DISCOVERY', 'PROPOSAL', 'WON', 'LOST'
    expected_amount NUMERIC NOT NULL DEFAULT 0,
    converted_order_id TEXT REFERENCES sales_orders(order_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crm_quotes (
    quote_id TEXT PRIMARY KEY,
    deal_id TEXT NOT NULL REFERENCES crm_deals(deal_id),
    quote_number TEXT NOT NULL UNIQUE,
    total_amount NUMERIC NOT NULL DEFAULT 0,
    valid_until DATE NOT NULL,
    docx_path TEXT,
    pdf_path TEXT,
    status TEXT NOT NULL DEFAULT 'DRAFT', -- 'DRAFT', 'SENT', 'ACCEPTED', 'REJECTED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
