"""001_initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-20 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Warehouses & Products
    op.create_table(
        "warehouses",
        sa.Column("warehouse_id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "products",
        sa.Column("sku", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_unit", sa.String(), server_default="PCS", nullable=False),
        sa.Column("cost_price", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("selling_price", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("safety_stock", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # 2. Stock Ledger & Locks
    op.create_table(
        "stock_ledger",
        sa.Column("ledger_id", sa.String(), primary_key=True),
        sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("qty_delta", sa.Numeric(), nullable=False),
        sa.Column("balance_after", sa.Numeric(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(), nullable=False),
        sa.Column("reference_type", sa.String(), nullable=False),
        sa.Column("reference_id", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "stock_locks",
        sa.Column("lock_id", sa.String(), primary_key=True),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("locked_qty", sa.Numeric(), nullable=False),
        sa.Column("status", sa.String(), server_default="LOCKED", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # 3. Procurement: PO & GRN
    op.create_table(
        "purchase_orders",
        sa.Column("po_id", sa.String(), primary_key=True),
        sa.Column("supplier_name", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), server_default="WH-MAIN", nullable=False),
        sa.Column("status", sa.String(), server_default="DRAFT", nullable=False),
        sa.Column("total_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "purchase_order_items",
        sa.Column("po_item_id", sa.String(), primary_key=True),
        sa.Column("po_id", sa.String(), sa.ForeignKey("purchase_orders.po_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(), nullable=False),
        sa.Column("subtotal", sa.Numeric(), nullable=False),
    )

    op.create_table(
        "goods_receipt_notes",
        sa.Column("grn_id", sa.String(), primary_key=True),
        sa.Column("po_id", sa.String(), sa.ForeignKey("purchase_orders.po_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("received_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # 4. Sales Orders & Items
    op.create_table(
        "sales_orders",
        sa.Column("order_id", sa.String(), primary_key=True),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("warehouse_id", sa.String(), server_default="WH-MAIN", nullable=False),
        sa.Column("channel", sa.String(), server_default="DIRECT", nullable=False),
        sa.Column("status", sa.String(), server_default="DRAFT", nullable=False),
        sa.Column("total_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "sales_order_items",
        sa.Column("item_id", sa.String(), primary_key=True),
        sa.Column("order_id", sa.String(), sa.ForeignKey("sales_orders.order_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("subtotal", sa.Numeric(), nullable=False),
        sa.Column("shipped_quantity", sa.Numeric(), server_default="0", nullable=False),
    )

    # 5. Delivery Orders & Allocations (1:N)
    op.create_table(
        "delivery_orders",
        sa.Column("do_id", sa.String(), primary_key=True),
        sa.Column("order_id", sa.String(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("warehouse_id", sa.String(), sa.ForeignKey("warehouses.warehouse_id"), nullable=False),
        sa.Column("tracking_number", sa.String(), nullable=True),
        sa.Column("shipped_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_delivery_orders_order_id", "delivery_orders", ["order_id"])

    op.create_table(
        "delivery_allocations",
        sa.Column("allocation_id", sa.String(), primary_key=True),
        sa.Column("do_id", sa.String(), sa.ForeignKey("delivery_orders.do_id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", sa.String(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("item_id", sa.String(), sa.ForeignKey("sales_order_items.item_id"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("allocated_qty", sa.Numeric(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_delivery_allocations_order", "delivery_allocations", ["order_id"])
    op.create_index("idx_delivery_allocations_do", "delivery_allocations", ["do_id"])

    # 6. Invoices, AR, AP
    op.create_table(
        "invoices",
        sa.Column("invoice_id", sa.String(), primary_key=True),
        sa.Column("order_id", sa.String(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("invoice_number", sa.String(), unique=True, nullable=False),
        sa.Column("random_code", sa.String(), nullable=False),
        sa.Column("tax_type", sa.String(), server_default="1", nullable=False),
        sa.Column("total_amount", sa.Numeric(), nullable=False),
        sa.Column("tax_amount", sa.Numeric(), nullable=False),
        sa.Column("buyer_tax_id", sa.String(), nullable=True),
        sa.Column("buyer_name", sa.String(), nullable=True),
        sa.Column("qrcode_l", sa.String(), nullable=True),
        sa.Column("qrcode_r", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="ISSUED", nullable=False),
        sa.Column("issued_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_invoices_order_id", "invoices", ["order_id"])

    op.create_table(
        "accounts_receivable",
        sa.Column("ar_id", sa.String(), primary_key=True),
        sa.Column("order_id", sa.String(), sa.ForeignKey("sales_orders.order_id"), nullable=False),
        sa.Column("invoice_id", sa.String(), sa.ForeignKey("invoices.invoice_id"), nullable=False),
        sa.Column("customer_id", sa.String(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("paid_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("status", sa.String(), server_default="UNPAID", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_ar_order_id", "accounts_receivable", ["order_id"])

    op.create_table(
        "accounts_payable",
        sa.Column("ap_id", sa.String(), primary_key=True),
        sa.Column("po_id", sa.String(), sa.ForeignKey("purchase_orders.po_id"), nullable=False),
        sa.Column("grn_id", sa.String(), sa.ForeignKey("goods_receipt_notes.grn_id"), nullable=True),
        sa.Column("supplier_name", sa.String(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("paid_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("status", sa.String(), server_default="UNPAID", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # 7. TanGii Accounting: Accounts & Journal
    accounts_table = op.create_table(
        "accounts",
        sa.Column("account_code", sa.String(), primary_key=True),
        sa.Column("account_name", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1"),
    )

    # Seed Standard Accounts
    op.bulk_insert(
        accounts_table,
        [
            {"account_code": "1101", "account_name": "現金", "account_type": "ASSET"},
            {"account_code": "1102", "account_name": "銀行存款", "account_type": "ASSET"},
            {"account_code": "1144", "account_name": "應收帳款", "account_type": "ASSET"},
            {"account_code": "1201", "account_name": "存貨", "account_type": "ASSET"},
            {"account_code": "2144", "account_name": "應付帳款", "account_type": "LIABILITY"},
            {"account_code": "2201", "account_name": "銷項稅額", "account_type": "LIABILITY"},
            {"account_code": "3101", "account_name": "業主資本", "account_type": "EQUITY"},
            {"account_code": "4111", "account_name": "銷貨收入", "account_type": "REVENUE"},
            {"account_code": "5111", "account_name": "銷貨成本", "account_type": "EXPENSE"},
            {"account_code": "6101", "account_name": "營業費用", "account_type": "EXPENSE"},
        ],
    )

    op.create_table(
        "journal_entries",
        sa.Column("entry_id", sa.String(), primary_key=True),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("source_event", sa.String(), nullable=False),
        sa.Column("reference_id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "journal_lines",
        sa.Column("line_id", sa.String(), primary_key=True),
        sa.Column("entry_id", sa.String(), sa.ForeignKey("journal_entries.entry_id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_code", sa.String(), sa.ForeignKey("accounts.account_code"), nullable=False),
        sa.Column("debit", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("credit", sa.Numeric(), server_default="0", nullable=False),
    )

    # 8. LiLai CRM
    op.create_table(
        "crm_contacts",
        sa.Column("contact_id", sa.String(), primary_key=True),
        sa.Column("company_name", sa.String(), nullable=False),
        sa.Column("tax_id", sa.String(), nullable=True),
        sa.Column("contact_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "crm_deals",
        sa.Column("deal_id", sa.String(), primary_key=True),
        sa.Column("contact_id", sa.String(), sa.ForeignKey("crm_contacts.contact_id"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), server_default="LEAD", nullable=False),
        sa.Column("expected_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("converted_order_id", sa.String(), sa.ForeignKey("sales_orders.order_id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "crm_quotes",
        sa.Column("quote_id", sa.String(), primary_key=True),
        sa.Column("deal_id", sa.String(), sa.ForeignKey("crm_deals.deal_id"), nullable=False),
        sa.Column("quote_number", sa.String(), unique=True, nullable=False),
        sa.Column("total_amount", sa.Numeric(), server_default="0", nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("docx_path", sa.String(), nullable=True),
        sa.Column("pdf_path", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "crm_quote_items",
        sa.Column("item_id", sa.String(), primary_key=True),
        sa.Column("quote_id", sa.String(), sa.ForeignKey("crm_quotes.quote_id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(), sa.ForeignKey("products.sku"), nullable=False),
        sa.Column("qty", sa.Numeric(), nullable=False),
        sa.Column("unit_price", sa.Numeric(), nullable=False),
        sa.Column("subtotal", sa.Numeric(), nullable=False),
    )


def downgrade() -> None:
    tables = [
        "crm_quote_items", "crm_quotes", "crm_deals", "crm_contacts",
        "journal_lines", "journal_entries", "accounts",
        "accounts_payable", "accounts_receivable", "invoices",
        "delivery_allocations", "delivery_orders", "sales_order_items", "sales_orders",
        "goods_receipt_notes", "purchase_order_items", "purchase_orders",
        "stock_locks", "stock_ledger", "products", "warehouses",
    ]
    for table in tables:
        op.drop_table(table)
