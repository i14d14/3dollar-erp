from __future__ import annotations
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import BinaryIO, List, Optional, Union
import fitz  # PyMuPDF

from src.ai_wrapper.invoice.models import ExtractedInvoiceItem, ExtractedTaiwanInvoice


class TaiwanPdfInvoiceParser:
    """Native PDF parser for Taiwan Electronic Invoices using PyMuPDF (fitz)."""

    def parse(self, file_source: Union[bytes, BinaryIO, str, Path]) -> ExtractedTaiwanInvoice:
        """Extract text layer from PDF and parse structured e-invoice data."""
        if isinstance(file_source, bytes):
            doc = fitz.open(stream=file_source, filetype="pdf")
        elif hasattr(file_source, "read"):
            doc = fitz.open(stream=file_source.read(), filetype="pdf")
        else:
            doc = fitz.open(str(file_source))

        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"

        return self._extract_from_text(full_text)

    def _extract_from_text(self, text: str) -> ExtractedTaiwanInvoice:
        warnings: List[str] = []

        # 1. Invoice Number: 2 uppercase letters + optional dash/space + 8 digits
        inv_match = re.search(r"\b([A-Z]{2})[-\s]?([0-9]{8})\b", text)
        if inv_match:
            invoice_number = f"{inv_match.group(1)}-{inv_match.group(2)}"
        else:
            invoice_number = "UNKNOWN"
            warnings.append("未能識別出標準台灣電子發票字軌號碼 (如 AB-12345678)")

        # 2. Random Code: 4 digits
        random_match = re.search(r"隨機碼\s*[:：]?\s*([0-9]{4})", text)
        if not random_match:
            # Try searching near invoice number or standalone 4 digits preceded by random keywords
            random_match = re.search(r"\b([0-9]{4})\b", text)
        random_code = random_match.group(1) if random_match else None

        # 3. Seller & Buyer Tax ID (8 digits)
        seller_tax_id = None
        seller_match = re.search(r"賣方(?:統一編號|統編)?\s*[:：]?\s*([0-9]{8})", text)
        if seller_match:
            seller_tax_id = seller_match.group(1)
        else:
            # Fallback search for any 8-digit numbers labeled with 賣方
            s_fallback = re.search(r"賣方[^\n\r0-9]*([0-9]{8})", text)
            if s_fallback:
                seller_tax_id = s_fallback.group(1)

        buyer_tax_id = None
        buyer_match = re.search(r"買方(?:統一編號|統編)?\s*[:：]?\s*([0-9]{8})", text)
        if buyer_match:
            buyer_tax_id = buyer_match.group(1)
        else:
            b_fallback = re.search(r"買方[^\n\r0-9]*([0-9]{8})", text)
            if b_fallback:
                buyer_tax_id = b_fallback.group(1)

        # 4. Seller & Buyer Names
        seller_name = None
        for line in text.split("\n"):
            line_s = line.strip()
            if any(line_s.endswith(sfx) or sfx in line_s for sfx in ["股份有限公司", "有限公司", "企業社", "實業", "工業", "行銷", "科技"]):
                if not any(k in line_s for k in ["買方", "統一編號", "發票", "證明聯", "3Dollar", "ERP"]):
                    seller_name = line_s
                    break

        if not seller_name:
            s_name_match = re.search(r"賣方(?:名稱|營業人)?\s*[:：]?\s*([^\n\r,0-9]{2,30})", text)
            if s_name_match:
                cand = s_name_match.group(1).strip()
                if not any(k in cand for k in ["統編", "統一編號"]):
                    seller_name = cand

        buyer_name = None
        b_name_match = re.search(r"買方(?:名稱|營業人)\s*[:：]?\s*([^\n\r,:：0-9]{2,30})", text)
        if not b_name_match:
            b_name_match = re.search(r"買方\s*[:：]\s*([^\n\r,:：0-9]{2,30})", text)
        if b_name_match:
            cand = b_name_match.group(1).strip()
            if not any(k in cand for k in ["統編", "統一編號"]) and not cand.isdigit():
                buyer_name = cand
        if buyer_name:
            buyer_name = re.sub(r"^[:：\s]+", "", buyer_name).strip()
            if len(buyer_name) < 2 or all(c in ":：- " for c in buyer_name):
                buyer_name = None

        # 5. Date Extraction (ROC or Gregorian)
        invoice_date = None
        # First check explicit "開立日期: YYYY-MM-DD" or "日期: YYYY-MM-DD"
        labeled_date_match = re.search(
            r"(?:開立日期|發票日期|交易日期|日期)\s*[:：]?\s*(20[2-9][0-9])[-/.年](0?[1-9]|1[0-2])[-/.月]([12][0-9]|3[01]|0?[1-9])\b",
            text,
        )
        if labeled_date_match:
            y, m, d = labeled_date_match.groups()
            invoice_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        else:
            west_date_match = re.search(
                r"\b(20[2-9][0-9])[-/.年](0?[1-9]|1[0-2])[-/.月]([12][0-9]|3[01]|0?[1-9])\b",
                text,
            )
            if west_date_match:
                y, m, d = west_date_match.groups()
                invoice_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
            else:
                # ROC date: 115-09-14 or 115年09月14日
                roc_date_match = re.search(
                    r"(?:開立日期|發票日期|交易日期|日期)\s*[:：]?\s*([0-9]{2,3})[年/-](0?[1-9]|1[0-2])[月/-]([12][0-9]|3[01]|0?[1-9])\b",
                    text,
                )
                if roc_date_match:
                    roc_y, m, d = roc_date_match.groups()
                    west_y = int(roc_y) + 1911
                    invoice_date = f"{west_y:04d}-{int(m):02d}-{int(d):02d}"

        # 6. Amounts
        total_amount = Decimal("0.0")
        tot_match = re.search(r"(?:總計|總金額|合計|應付金額)\s*[:：]?\s*(?:NT\$|NTD|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text)
        if tot_match:
            try:
                total_amount = Decimal(tot_match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        sales_amount = Decimal("0.0")
        sales_match = re.search(r"(?:應稅銷售額|銷售額|未稅金額|小計)\s*[:：]?\s*(?:NT\$|NTD|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text)
        if sales_match:
            try:
                sales_amount = Decimal(sales_match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        tax_amount = Decimal("0.0")
        tax_match = re.search(r"(?:營業稅|稅額)\s*[:：]?\s*(?:NT\$|NTD|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)", text)
        if tax_match:
            try:
                tax_amount = Decimal(tax_match.group(1).replace(",", ""))
            except InvalidOperation:
                pass

        # If sales and tax are missing but total is present, derive Taiwan 5% VAT
        if total_amount > Decimal("0.0") and sales_amount == Decimal("0.0") and tax_amount == Decimal("0.0"):
            sales_amount = (total_amount / Decimal("1.05")).quantize(Decimal("1"))
            tax_amount = total_amount - sales_amount

        # Validate math: total == sales + tax
        is_math_valid = True
        if total_amount > 0 and (sales_amount > 0 or tax_amount > 0):
            if abs(total_amount - (sales_amount + tax_amount)) > Decimal("1.0"):
                is_math_valid = False
                warnings.append(
                    f"金額校驗異常：總計 ({total_amount}) 不等於銷售額 ({sales_amount}) 加稅額 ({tax_amount})"
                )

        if total_amount == Decimal("0.0"):
            warnings.append("未能成功提取發票總金額")

        # 7. Extract items
        items: List[ExtractedInvoiceItem] = []
        # Look for table rows: Name Qty Price Amount
        item_patterns = [
            r"([^\n\r0-9]+)\s+([0-9]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)\s+([0-9,]+(?:\.[0-9]+)?)",
        ]
        for line in text.split("\n"):
            line = line.strip()
            # Ignore headers/footers
            if any(k in line for k in ["品名", "總計", "銷售額", "統編", "隨機碼", "開立日期", "證明聯"]):
                continue
            for pat in item_patterns:
                m = re.match(pat, line)
                if m:
                    try:
                        desc = m.group(1).strip()
                        q = Decimal(m.group(2).replace(",", ""))
                        p = Decimal(m.group(3).replace(",", ""))
                        amt = Decimal(m.group(4).replace(",", ""))
                        items.append(ExtractedInvoiceItem(description=desc, qty=q, unit_price=p, amount=amt))
                    except (InvalidOperation, ValueError):
                        pass

        # If no items parsed from line regex, create a default summary line item from total
        if not items and total_amount > 0:
            items.append(
                ExtractedInvoiceItem(
                    description="採購品項彙總",
                    qty=Decimal("1.0"),
                    unit_price=sales_amount,
                    amount=sales_amount,
                )
            )

        return ExtractedTaiwanInvoice(
            invoice_number=invoice_number,
            seller_tax_id=seller_tax_id,
            seller_name=seller_name,
            buyer_tax_id=buyer_tax_id,
            buyer_name=buyer_name,
            invoice_date=invoice_date,
            sales_amount=sales_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            random_code=random_code,
            items=items,
            is_math_valid=is_math_valid,
            validation_warnings=warnings,
        )
