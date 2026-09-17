from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from src.core.ports.event_bus_port import EventBusPort
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.base_models import DomainEvent
from src.shared.database import Database, default_db


class AccountingEventHandler:
    """Listens to ERP domain events and automatically transforms them into balanced double-entry vouchers."""

    def __init__(
        self,
        accounting_service: AccountingService,
        db: Database = default_db,
    ) -> None:
        self.accounting_service = accounting_service
        self.db = db

    def handle_goods_received(self, event: DomainEvent) -> None:
        """Handle ERP_GOODS_RECEIVED: create AP and debit inventory, credit AP."""
        payload = event.payload
        grn_id = payload.get("grn_id")
        po_id = payload.get("po_id")
        total_amount = Decimal(str(payload.get("total_amount", 0.0)))

        # Look up supplier name from PO
        supplier_name = "未知供應商"
        with self.db.transaction() as conn:
            po_row = conn.execute(
                "SELECT supplier_name FROM purchase_orders WHERE po_id = ?",
                (po_id,),
            ).fetchone()
            if po_row:
                supplier_name = po_row["supplier_name"]

        # 1. Create AP record
        self.accounting_service.create_accounts_payable(
            po_id=po_id,
            grn_id=grn_id,
            supplier_name=supplier_name,
            amount=total_amount,
        )

        # 2. Record journal entry: Dr 1201 存貨, Cr 2144 應付帳款
        if total_amount > Decimal("0.0"):
            self.accounting_service.create_journal_entry(
                entry_date=date.today(),
                source_event="ERP_GOODS_RECEIVED",
                reference_id=grn_id,
                description=f"採購入庫入帳 (GRN: {grn_id}, 廠商: {supplier_name})",
                lines=[
                    ("1201", total_amount, Decimal("0.0")),
                    ("2144", Decimal("0.0"), total_amount),
                ],
            )

    def handle_order_shipped(self, event: DomainEvent) -> None:
        """Handle ERP_ORDER_SHIPPED: recognize COGS (Dr 5111 銷貨成本, Cr 1201 存貨)."""
        payload = event.payload
        order_id = payload.get("order_id")
        do_id = payload.get("do_id")

        # Calculate actual inventory cost from stock_ledger for this DO
        total_cost = Decimal("0.0")
        with self.db.transaction() as conn:
            cost_row = conn.execute(
                """
                SELECT SUM(ABS(qty_delta) * unit_cost) AS total_cost
                FROM stock_ledger
                WHERE reference_id = ?
                """,
                (do_id,),
            ).fetchone()

            if cost_row and cost_row["total_cost"] is not None:
                total_cost = Decimal(str(cost_row["total_cost"])).quantize(Decimal("0.01"))
            else:
                # Fallback: calculate from order items join products cost_price
                items = conn.execute(
                    """
                    SELECT soi.qty, p.cost_price
                    FROM sales_order_items soi
                    JOIN products p ON soi.sku = p.sku
                    WHERE soi.order_id = ?
                    """,
                    (order_id,),
                ).fetchall()
                for item in items:
                    total_cost += Decimal(str(item["qty"])) * Decimal(str(item["cost_price"]))

        if total_cost > Decimal("0.0"):
            self.accounting_service.create_journal_entry(
                entry_date=date.today(),
                source_event="ERP_ORDER_SHIPPED",
                reference_id=do_id,
                description=f"訂單出貨認列銷貨成本 (DO: {do_id}, SO: {order_id})",
                lines=[
                    ("5111", total_cost, Decimal("0.0")),
                    ("1201", Decimal("0.0"), total_cost),
                ],
            )

    def handle_invoice_issued(self, event: DomainEvent) -> None:
        """Handle ERP_INVOICE_ISSUED: recognize Revenue & AR (Dr 1144 應收帳款, Cr 4111 銷貨收入, Cr 2201 銷項稅額)."""
        payload = event.payload
        invoice_id = payload.get("invoice_id")
        order_id = payload.get("order_id")
        invoice_number = payload.get("invoice_number", "")
        total_amount = Decimal(str(payload.get("total_amount", 0.0)))

        # Look up invoice for tax details
        tax_amount = Decimal("0.0")
        with self.db.transaction() as conn:
            inv_row = conn.execute(
                "SELECT tax_amount FROM invoices WHERE invoice_id = ?",
                (invoice_id,),
            ).fetchone()
            if inv_row and inv_row["tax_amount"] is not None:
                tax_amount = Decimal(str(inv_row["tax_amount"]))

        sales_amount = total_amount - tax_amount

        lines = [
            ("1144", total_amount, Decimal("0.0")),
            ("4111", Decimal("0.0"), sales_amount),
        ]
        if tax_amount > Decimal("0.0"):
            lines.append(("2201", Decimal("0.0"), tax_amount))

        if total_amount > Decimal("0.0"):
            self.accounting_service.create_journal_entry(
                entry_date=date.today(),
                source_event="ERP_INVOICE_ISSUED",
                reference_id=invoice_id,
                description=f"電子發票開立認列營收 (發票: {invoice_number}, 訂單: {order_id})",
                lines=lines,
            )


def register_accounting_event_handlers(
    event_bus: EventBusPort,
    accounting_service: Optional[AccountingService] = None,
    db: Database = default_db,
) -> AccountingEventHandler:
    """Wire up domain event listeners for TanGii accounting."""
    acct_svc = accounting_service or AccountingService(db=db)
    handler = AccountingEventHandler(accounting_service=acct_svc, db=db)

    event_bus.subscribe("ERP_GOODS_RECEIVED", handler.handle_goods_received)
    event_bus.subscribe("ERP_ORDER_SHIPPED", handler.handle_order_shipped)
    event_bus.subscribe("ERP_INVOICE_ISSUED", handler.handle_invoice_issued)

    return handler
