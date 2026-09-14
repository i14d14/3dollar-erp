from __future__ import annotations
import datetime
import random
import uuid
from decimal import Decimal
from typing import Optional
import fitz  # PyMuPDF

from src.core.domain.invoice import Invoice, InvoiceStatus, TaxType
from src.core.ports.invoice_port import InvoicePort, IssueInvoiceRequest


class MockInvoiceProvider(InvoicePort):
    """Mock Taiwan Electronic Invoice Provider conforming to MIG 3.2.1 format."""

    def __init__(self, seller_tax_id: str = "88888888", seller_name: str = "3Dollar ERP Corp.") -> None:
        self.seller_tax_id = seller_tax_id
        self.seller_name = seller_name

    def _generate_invoice_number(self) -> str:
        """Generate a valid Taiwan e-invoice number: 2 uppercase letters + 8 digits."""
        letters = "AB"
        number = "".join([str(random.randint(0, 9)) for _ in range(8)])
        return f"{letters}-{number}"

    def _generate_random_code(self) -> str:
        """Generate a 4-digit random security code."""
        return f"{random.randint(1000, 9999)}"

    def issue_invoice(self, request: IssueInvoiceRequest) -> Invoice:
        invoice_id = f"INV-{uuid.uuid4().hex[:12].upper()}"
        invoice_number = self._generate_invoice_number()
        random_code = self._generate_random_code()

        # Tax calculation
        if request.tax_type == TaxType.TAXABLE:
            # In Taiwan B2B/B2C, total = sales + tax. Tax = round(total / 1.05 * 0.05)
            sales_amount = (request.total_amount / Decimal("1.05")).quantize(Decimal("1"))
            tax_amount = request.total_amount - sales_amount
        else:
            tax_amount = Decimal("0.0")

        # ROC Date format (YYYMMDD) e.g., 1150914
        now = datetime.datetime.now()
        roc_year = now.year - 1911
        roc_date_str = f"{roc_year:03d}{now.month:02d}{now.day:02d}"

        # MIG 3.2.1 Left QR code format
        # InvNum(10) + Date(7) + Random(4) + SalesHex(8) + TotalHex(8) + BuyerTaxId(8) + SellerTaxId(8) + Encrypt(24)
        sales_hex = f"{int(request.total_amount - tax_amount):08X}"
        total_hex = f"{int(request.total_amount):08X}"
        buyer_id = request.buyer_tax_id.strip() if request.buyer_tax_id else "00000000"
        mock_encrypt = uuid.uuid4().hex[:24].upper()
        qrcode_l = f"{invoice_number.replace('-', '')}{roc_date_str}{random_code}{sales_hex}{total_hex}{buyer_id}{self.seller_tax_id}{mock_encrypt}:**"
        qrcode_r = f"**{self.seller_name}:{int(request.total_amount)}:1:1"

        return Invoice(
            invoice_id=invoice_id,
            order_id=request.order_id,
            invoice_number=invoice_number,
            random_code=random_code,
            tax_type=request.tax_type,
            total_amount=request.total_amount,
            tax_amount=tax_amount,
            buyer_tax_id=request.buyer_tax_id,
            buyer_name=request.buyer_name,
            qrcode_l=qrcode_l,
            qrcode_r=qrcode_r,
            status=InvoiceStatus.ISSUED,
        )

    def render_invoice_pdf(self, invoice: Invoice) -> bytes:
        """Render standard 5.7cm wide (161.57 pt) Taiwan e-invoice receipt PDF using PyMuPDF."""
        doc = fitz.open()
        # 57mm width = 161.57 points, 140mm height = 396.85 points
        width = 161.57
        height = 396.85
        page = doc.new_page(width=width, height=height)

        # Draw header
        page.insert_text(fitz.Point(12, 25), self.seller_name, fontsize=8, fontname="helv")
        page.insert_text(fitz.Point(12, 42), "電子發票證明聯", fontsize=10, fontname="china-t")
        page.insert_text(fitz.Point(12, 56), "(MIG 3.2.1)", fontsize=8, fontname="helv")

        # Period & Invoice number
        now = datetime.datetime.now()
        roc_year = now.year - 1911
        period_month = now.month if now.month % 2 == 0 else now.month + 1
        period_str = f"{roc_year:03d}年{period_month - 1:02d}-{period_month:02d}月"
        page.insert_text(fitz.Point(12, 72), period_str, fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(12, 88), invoice.invoice_number, fontsize=11, fontname="helv")

        # Separator line
        page.draw_line(fitz.Point(10, 96), fitz.Point(150, 96), color=(0, 0, 0), width=0.8)

        # Metadata
        page.insert_text(fitz.Point(12, 110), f"開立日期: {now.strftime('%Y-%m-%d %H:%M')}", fontsize=7, fontname="china-t")
        page.insert_text(fitz.Point(12, 124), f"隨機碼: {invoice.random_code}", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 138), f"總計: NT$ {int(invoice.total_amount)}", fontsize=8, fontname="china-t")

        seller_str = f"賣方: {self.seller_tax_id}"
        buyer_str = f"買方: {invoice.buyer_tax_id or '個人消費'}"
        page.insert_text(fitz.Point(12, 152), seller_str, fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(12, 166), buyer_str, fontsize=8, fontname="china-t")

        # Mock 1D Barcode Box
        barcode_rect = fitz.Rect(12, 178, 148, 203)
        page.draw_rect(barcode_rect, color=(0, 0, 0), width=0.5)
        page.insert_text(fitz.Point(20, 194), f"||| {invoice.invoice_number} |||", fontsize=8, fontname="helv")

        # Mock Dual QR Codes (Left and Right)
        qr_left = fitz.Rect(12, 215, 72, 275)
        qr_right = fitz.Rect(82, 215, 142, 275)
        page.draw_rect(qr_left, color=(0, 0, 0), width=0.5)
        page.draw_rect(qr_right, color=(0, 0, 0), width=0.5)
        page.insert_text(fitz.Point(22, 248), "[QR-L]", fontsize=8, fontname="helv")
        page.insert_text(fitz.Point(92, 248), "[QR-R]", fontsize=8, fontname="helv")

        # Footer notes
        page.draw_line(fitz.Point(10, 290), fitz.Point(150, 290), color=(0, 0, 0), width=0.5)
        page.insert_text(fitz.Point(12, 308), f"訂單編號: {invoice.order_id}", fontsize=7, fontname="china-t")
        page.insert_text(fitz.Point(12, 322), "營業人統一編號審驗合格", fontsize=7, fontname="china-t")

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
