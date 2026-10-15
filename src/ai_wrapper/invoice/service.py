from __future__ import annotations
import datetime
import uuid
from decimal import Decimal
from typing import Optional

from src.ai_wrapper.invoice.models import ExtractedTaiwanInvoice, InvoiceMatchResult
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.shared.database import Database, default_db


class InvoiceIntakeService:
    """Service to match parsed PDF invoices against procurement and record Accounts Payable."""

    def __init__(self, db: Database = default_db, accounting_service: Optional[AccountingService] = None) -> None:
        self.db = db
        self.accounting_service = accounting_service or AccountingService(db=db)

    def match_invoice(self, invoice: ExtractedTaiwanInvoice) -> InvoiceMatchResult:
        """Check for duplicates and find matching open purchase orders."""
        with self.db.transaction() as conn:
            existing_ap_id = None
            is_duplicate = False

            # 1. Primary dupe check: by exact invoice number in general ledger / intake notes
            if invoice.invoice_number and invoice.invoice_number != "UNKNOWN":
                existing_entry = conn.execute(
                    "SELECT entry_id, reference_id FROM journal_entries WHERE description LIKE ? ORDER BY created_at DESC LIMIT 1",
                    (f"%發票: {invoice.invoice_number}%",),
                ).fetchone()
                if existing_entry:
                    is_duplicate = True
                    existing_ap_id = existing_entry["reference_id"]
            else:
                # 2. Fallback dupe check (only if invoice_number is unknown/missing): by supplier_name and exact amount
                existing_ap = conn.execute(
                    "SELECT ap_id, supplier_name, amount FROM accounts_payable WHERE supplier_name = ? AND amount = ?",
                    (invoice.seller_name or "", float(invoice.total_amount)),
                ).fetchone()
                if existing_ap:
                    is_duplicate = True
                    existing_ap_id = existing_ap["ap_id"]

            # Find matching open purchase order (excluding already invoiced POs and synthetic PO-INV-*)
            matched_po = None
            if invoice.seller_name:
                po_row = conn.execute(
                    """
                    SELECT po.po_id, po.supplier_name, po.total_amount
                    FROM purchase_orders po
                    LEFT JOIN accounts_payable ap ON po.po_id = ap.po_id
                    WHERE po.supplier_name LIKE ?
                      AND ap.ap_id IS NULL
                      AND po.po_id NOT LIKE 'PO-INV-%'
                    ORDER BY po.created_at DESC LIMIT 1
                    """,
                    (f"%{invoice.seller_name}%",),
                ).fetchone()
                if po_row:
                    matched_po = po_row["po_id"]

            status = "NEW"
            if is_duplicate:
                status = "ALREADY_RECORDED"
            elif matched_po:
                status = "MATCHED_PO"
            elif not invoice.is_math_valid:
                status = "MATH_ERROR"

            return InvoiceMatchResult(
                extracted=invoice,
                matched_po_id=matched_po,
                matched_supplier=invoice.seller_name,
                existing_ap_id=existing_ap_id,
                status=status,
            )

    def create_ap_from_invoice(
        self,
        invoice: ExtractedTaiwanInvoice,
        po_id: Optional[str] = None,
        supplier_name: Optional[str] = None,
        due_days: int = 30,
    ) -> str:
        """Create Accounts Payable (AP) and General Ledger entry from parsed electronic invoice."""
        supplier = supplier_name or invoice.seller_name or "外部供應商"
        amount = invoice.total_amount

        # Check duplicate invoice number before creating AP or Journal Entry
        if invoice.invoice_number and invoice.invoice_number != "UNKNOWN":
            with self.db.transaction() as conn:
                existing_entry = conn.execute(
                    "SELECT entry_id, reference_id FROM journal_entries WHERE description LIKE ? LIMIT 1",
                    (f"%發票: {invoice.invoice_number}%",),
                ).fetchone()
                if existing_entry:
                    raise ValueError(f"發票號碼 {invoice.invoice_number} 已經於系統中註冊入帳，嚴禁重複登記！")

        with self.db.transaction() as conn:
            target_po_id = po_id
            if not target_po_id:
                # If no PO specified, create an automatic procurement record for foreign invoice intake
                target_po_id = f"PO-INV-{uuid.uuid4().hex[:8].upper()}"
                conn.execute(
                    """
                    INSERT INTO purchase_orders (po_id, supplier_name, status, total_amount)
                    VALUES (?, ?, 'RECEIVED', ?)
                    """,
                    (target_po_id, supplier, float(amount)),
                )

        # Call AccountingService to record AP
        ap = self.accounting_service.create_accounts_payable(
            po_id=target_po_id,
            supplier_name=supplier,
            amount=amount,
            due_days=due_days,
        )

        # Record double-entry journal entry:
        # Dr: 1201 存貨 (or 6101 營業費用) / Cr: 2144 應付帳款
        today = datetime.date.today()
        sales_part = invoice.sales_amount if invoice.sales_amount > 0 else amount
        tax_part = invoice.tax_amount if invoice.tax_amount > 0 else Decimal("0.0")

        # Ensure debits equal credit
        if sales_part + tax_part != amount:
            sales_part = amount
            tax_part = Decimal("0.0")

        lines = [
            ("1201", sales_part, Decimal("0.0")),  # Dr 存貨
        ]
        if tax_part > 0:
            lines.append(("1201", tax_part, Decimal("0.0")))  # or 進項稅額 if exists, else inventory cost

        lines.append(("2144", Decimal("0.0"), amount))  # Cr 應付帳款

        self.accounting_service.create_journal_entry(
            entry_date=today,
            source_event="AI_INVOICE_INTAKE",
            reference_id=ap.ap_id,
            description=f"PDF 電子發票自動辨識建檔 (發票: {invoice.invoice_number}, 供應商: {supplier})",
            lines=[
                ("1201", amount, Decimal("0.0")),
                ("2144", Decimal("0.0"), amount),
            ],
        )

        return ap.ap_id
