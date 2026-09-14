from __future__ import annotations
import datetime
import sqlite3
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from src.core.adapters.mock_invoice_adapter import MockInvoiceProvider
from src.core.domain.invoice import AccountsReceivable, ARStatus, Invoice, InvoiceStatus, TaxType
from src.core.domain.order import OrderStatus
from src.core.ports.event_bus_port import EventBusPort
from src.core.ports.invoice_port import InvoicePort, IssueInvoiceRequest
from src.shared.base_models import DomainEvent, DomainModel
from src.shared.database import Database, default_db
from src.shared.event_bus import default_event_bus


class ReconciliationReport(DomainModel):
    order_id: str
    is_reconciled: bool
    so_exists: bool
    do_exists: bool
    inv_exists: bool
    ar_exists: bool
    so_amount: Decimal
    inv_amount: Decimal
    ar_amount: Decimal
    discrepancies: List[str] = []


class InvoiceService:
    def __init__(
        self,
        db: Database = default_db,
        invoice_provider: Optional[InvoicePort] = None,
        event_bus: EventBusPort = default_event_bus,
    ) -> None:
        self.db = db
        self.invoice_provider = invoice_provider or MockInvoiceProvider()
        self.event_bus = event_bus

    def issue_invoice_for_order(
        self,
        order_id: str,
        tax_type: TaxType = TaxType.TAXABLE,
        buyer_tax_id: Optional[str] = None,
        buyer_name: Optional[str] = None,
        due_days: int = 30,
    ) -> Tuple[Invoice, AccountsReceivable, bytes]:
        """Issue electronic invoice for an order, record AR, render 5.7cm PDF, and emit event."""
        with self.db.transaction() as conn:
            # 1. Fetch Sales Order
            order_row = conn.execute(
                "SELECT order_id, customer_id, status, total_amount FROM sales_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not order_row:
                raise ValueError(f"Sales order {order_id} not found")

            # Check if invoice already issued (1:1 constraint)
            existing_inv = conn.execute(
                "SELECT invoice_id FROM invoices WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if existing_inv:
                raise ValueError(f"Invoice already issued for order {order_id}: {existing_inv['invoice_id']}")

            total_amount = Decimal(str(order_row["total_amount"]))
            customer_id = order_row["customer_id"]

            # 2. Issue invoice via provider (MIG 3.2.1 compliant)
            req = IssueInvoiceRequest(
                order_id=order_id,
                total_amount=total_amount,
                tax_type=tax_type,
                buyer_tax_id=buyer_tax_id,
                buyer_name=buyer_name,
            )
            invoice = self.invoice_provider.issue_invoice(req)

            # 3. Store Invoice in database
            conn.execute(
                """
                INSERT INTO invoices (
                    invoice_id, order_id, invoice_number, random_code, tax_type,
                    total_amount, tax_amount, buyer_tax_id, buyer_name, qrcode_l, qrcode_r, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice.invoice_id,
                    invoice.order_id,
                    invoice.invoice_number,
                    invoice.random_code,
                    invoice.tax_type.value,
                    float(invoice.total_amount),
                    float(invoice.tax_amount),
                    invoice.buyer_tax_id,
                    invoice.buyer_name,
                    invoice.qrcode_l,
                    invoice.qrcode_r,
                    invoice.status.value,
                ),
            )

            # 4. Create 1:1 Accounts Receivable (AR) record
            ar_id = f"AR-{uuid.uuid4().hex[:10].upper()}"
            due_date = datetime.date.today() + datetime.timedelta(days=due_days)

            conn.execute(
                """
                INSERT INTO accounts_receivable (ar_id, order_id, invoice_id, customer_id, due_date, amount, paid_amount, status)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    ar_id,
                    order_id,
                    invoice.invoice_id,
                    customer_id,
                    due_date.isoformat(),
                    float(total_amount),
                    ARStatus.UNPAID.value,
                ),
            )

        # 5. Render 5.7cm wide receipt PDF
        pdf_bytes = self.invoice_provider.render_invoice_pdf(invoice)

        ar = AccountsReceivable(
            ar_id=ar_id,
            order_id=order_id,
            invoice_id=invoice.invoice_id,
            customer_id=customer_id,
            due_date=due_date,
            amount=total_amount,
            paid_amount=Decimal("0.0"),
            status=ARStatus.UNPAID,
        )

        # 6. Publish domain event
        event = DomainEvent(
            event_name="ERP_INVOICE_ISSUED",
            payload={
                "invoice_id": invoice.invoice_id,
                "order_id": order_id,
                "ar_id": ar_id,
                "invoice_number": invoice.invoice_number,
                "total_amount": float(total_amount),
                "customer_id": customer_id,
                "due_date": due_date.isoformat(),
            },
        )
        self.event_bus.publish(event)

        return invoice, ar, pdf_bytes

    def verify_four_way_reconciliation(self, order_id: str) -> ReconciliationReport:
        """Rigid 4-way reconciliation check: SO 1:1 DO 1:1 INV 1:1 AR."""
        discrepancies: List[str] = []

        with self.db.transaction() as conn:
            # Check SO
            so_row = conn.execute(
                "SELECT order_id, status, total_amount FROM sales_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            so_exists = so_row is not None
            so_amount = Decimal(str(so_row["total_amount"])) if so_row else Decimal("0.0")

            if not so_exists:
                discrepancies.append(f"Sales Order '{order_id}' does not exist.")

            # Check DO
            do_row = conn.execute(
                "SELECT do_id, warehouse_id FROM delivery_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            do_exists = do_row is not None
            if not do_exists:
                discrepancies.append(f"Delivery Order missing for SO '{order_id}'.")

            # Check Invoice
            inv_row = conn.execute(
                "SELECT invoice_id, total_amount, status FROM invoices WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            inv_exists = inv_row is not None
            inv_amount = Decimal(str(inv_row["total_amount"])) if inv_row else Decimal("0.0")
            if not inv_exists:
                discrepancies.append(f"Invoice missing for SO '{order_id}'.")

            # Check AR
            ar_row = conn.execute(
                "SELECT ar_id, invoice_id, amount, status FROM accounts_receivable WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            ar_exists = ar_row is not None
            ar_amount = Decimal(str(ar_row["amount"])) if ar_row else Decimal("0.0")
            if not ar_exists:
                discrepancies.append(f"Accounts Receivable missing for SO '{order_id}'.")

            # Cross-verify monetary amounts
            if so_exists and inv_exists and so_amount != inv_amount:
                discrepancies.append(f"Amount mismatch: SO amount ({so_amount}) != INV amount ({inv_amount}).")
            if inv_exists and ar_exists and inv_amount != ar_amount:
                discrepancies.append(f"Amount mismatch: INV amount ({inv_amount}) != AR amount ({ar_amount}).")

            # Cross-verify linkage
            if inv_exists and ar_exists and ar_row["invoice_id"] != inv_row["invoice_id"]:
                discrepancies.append(
                    f"Linkage mismatch: AR references '{ar_row['invoice_id']}' but INV is '{inv_row['invoice_id']}'."
                )

        is_reconciled = len(discrepancies) == 0 and (so_exists and do_exists and inv_exists and ar_exists)

        return ReconciliationReport(
            order_id=order_id,
            is_reconciled=is_reconciled,
            so_exists=so_exists,
            do_exists=do_exists,
            inv_exists=inv_exists,
            ar_exists=ar_exists,
            so_amount=so_amount,
            inv_amount=inv_amount,
            ar_amount=ar_amount,
            discrepancies=discrepancies,
        )
