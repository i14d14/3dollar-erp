from __future__ import annotations
import datetime
from decimal import Decimal
import io
from typing import Any, Dict, List, Optional

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
import fitz  # PyMuPDF

from src.extended_core.crm.models import Contact, Deal, Quote


class QuoteDocumentEngine:
    """Engine for generating commercial quotations in both DOCX (python-docx) and PDF (PyMuPDF) formats."""

    @staticmethod
    def generate_docx(
        contact: Contact,
        deal: Deal,
        quote: Quote,
        items_detail: List[Dict[str, Any]],
    ) -> bytes:
        """Generate a professionally styled quotation document (.docx) using python-docx."""
        doc = docx.Document()

        # Page margins
        for section in doc.sections:
            section.top_margin = Inches(0.8)
            section.bottom_margin = Inches(0.8)
            section.left_margin = Inches(0.8)
            section.right_margin = Inches(0.8)

        # Title / Header
        p_title = doc.add_paragraph()
        p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_title = p_title.add_run("3Dollar ERP • 哩來 CRM 商業報價單")
        run_title.font.name = "微軟正黑體"
        run_title.font.size = Pt(20)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(30, 41, 59)  # Slate-800

        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_sub = p_sub.add_run("COMMERCIAL QUOTATION / PROPOSAL")
        run_sub.font.name = "Calibri"
        run_sub.font.size = Pt(10)
        run_sub.font.color.rgb = RGBColor(100, 116, 139)

        doc.add_paragraph().paragraph_format.space_after = Pt(6)

        # Metadata Table: Customer info (Left) & Quotation info (Right)
        meta_table = doc.add_table(rows=5, cols=2)
        meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        meta_table.autofit = False
        meta_table.style = "Table Grid"

        left_data = [
            f"客戶名稱：{contact.company_name}",
            f"統一編號：{contact.tax_id or '未提供'}",
            f"聯絡人員：{contact.contact_name}",
            f"聯絡電話：{contact.phone or '未提供'}",
            f"電子郵件：{contact.email or '未提供'}",
        ]
        valid_date_str = quote.valid_until.strftime("%Y-%m-%d") if isinstance(quote.valid_until, (datetime.date, datetime.datetime)) else str(quote.valid_until)
        right_data = [
            f"報價單號：{quote.quote_number}",
            f"商機案名：{deal.title}",
            f"報價日期：{datetime.date.today().strftime('%Y-%m-%d')}",
            f"有效期限：{valid_date_str}",
            f"單據狀態：{quote.status.value}",
        ]

        for i in range(5):
            cell_l = meta_table.cell(i, 0)
            cell_r = meta_table.cell(i, 1)
            cell_l.width = Inches(3.3)
            cell_r.width = Inches(3.3)
            
            p_l = cell_l.paragraphs[0]
            p_l.paragraph_format.space_after = Pt(2)
            r_l = p_l.add_run(left_data[i])
            r_l.font.name = "微軟正黑體"
            r_l.font.size = Pt(9.5)

            p_r = cell_r.paragraphs[0]
            p_r.paragraph_format.space_after = Pt(2)
            r_r = p_r.add_run(right_data[i])
            r_r.font.name = "微軟正黑體"
            r_r.font.size = Pt(9.5)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Line Items Table
        headers = ["項次", "品號", "商品名稱", "數量", "單價 (NT$)", "小計 (NT$)"]
        item_table = doc.add_table(rows=1 + len(items_detail), cols=6)
        item_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        item_table.autofit = False
        item_table.style = "Table Grid"

        col_widths = [Inches(0.6), Inches(1.3), Inches(2.2), Inches(0.7), Inches(1.0), Inches(1.0)]

        # Header formatting
        for col_idx, text in enumerate(headers):
            cell = item_table.cell(0, col_idx)
            cell.width = col_widths[col_idx]
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col_idx >= 3 else WD_ALIGN_PARAGRAPH.LEFT
            if col_idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(text)
            run.font.name = "微軟正黑體"
            run.font.size = Pt(9.5)
            run.font.bold = True

        total_net = Decimal("0.0")
        for row_idx, item in enumerate(items_detail, start=1):
            sku = item.get("sku", "")
            name = item.get("name", sku)
            qty = Decimal(str(item.get("qty", "0")))
            price = Decimal(str(item.get("unit_price", "0")))
            subtotal = Decimal(str(item.get("subtotal", qty * price)))
            total_net += subtotal

            row_data = [
                str(row_idx),
                sku,
                name,
                f"{qty:,.0f}" if qty % 1 == 0 else f"{qty:,.2f}",
                f"{price:,.2f}",
                f"{subtotal:,.2f}",
            ]
            for col_idx, val in enumerate(row_data):
                cell = item_table.cell(row_idx, col_idx)
                cell.width = col_widths[col_idx]
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT if col_idx >= 3 else WD_ALIGN_PARAGRAPH.LEFT
                if col_idx == 0:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run(val)
                run.font.name = "微軟正黑體"
                run.font.size = Pt(9)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Financial Summary
        tax = (total_net * Decimal("0.05")).quantize(Decimal("1"))
        grand_total = total_net + tax

        p_sum = doc.add_paragraph()
        p_sum.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p_sum.paragraph_format.space_after = Pt(2)
        r1 = p_sum.add_run(f"未稅合計 (Subtotal)： NT$ {total_net:,.2f}\n")
        r1.font.name = "微軟正黑體"
        r1.font.size = Pt(10)

        r2 = p_sum.add_run(f"營業稅額 (VAT 5%)： NT$ {tax:,.2f}\n")
        r2.font.name = "微軟正黑體"
        r2.font.size = Pt(10)

        r3 = p_sum.add_run(f"含稅總計 (Grand Total)： NT$ {grand_total:,.2f}")
        r3.font.name = "微軟正黑體"
        r3.font.size = Pt(12)
        r3.font.bold = True
        r3.font.color.rgb = RGBColor(79, 70, 229)  # Indigo-600

        doc.add_paragraph().paragraph_format.space_after = Pt(12)

        # Terms and Signatures
        terms_p = doc.add_paragraph()
        terms_p.paragraph_format.space_after = Pt(4)
        r_terms_t = terms_p.add_run("商業約定條款：\n")
        r_terms_t.font.bold = True
        r_terms_t.font.size = Pt(9.5)
        terms_text = (
            "1. 報價單有效期間內確認訂購，享有上述報價優惠；逾期請洽業務人員重新評估。\n"
            "2. 付款方式：交貨驗收後 30 天內電匯結清款項。\n"
            "3. 本報價單經客戶簽名或蓋章回傳後即生效力，視為正式合約附隨採購意向書。"
        )
        r_terms_c = terms_p.add_run(terms_text)
        r_terms_c.font.size = Pt(8.5)
        r_terms_c.font.color.rgb = RGBColor(71, 85, 105)

        sig_table = doc.add_table(rows=2, cols=2)
        sig_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        sig_table.cell(0, 0).width = Inches(3.3)
        sig_table.cell(0, 1).width = Inches(3.3)
        sig_table.cell(1, 0).width = Inches(3.3)
        sig_table.cell(1, 1).width = Inches(3.3)

        s1 = sig_table.cell(0, 0).paragraphs[0].add_run("報價單位（賣方蓋章）：\n三圓科技股份有限公司")
        s1.font.name = "微軟正黑體"
        s1.font.size = Pt(9.5)
        s1.font.bold = True

        s2 = sig_table.cell(0, 1).paragraphs[0].add_run(f"確認客戶（買方簽署）：\n{contact.company_name}")
        s2.font.name = "微軟正黑體"
        s2.font.size = Pt(9.5)
        s2.font.bold = True

        sig_table.cell(1, 0).paragraphs[0].add_run("經辦簽章：__________________\n日期：____ 年 ____ 月 ____ 日").font.size = Pt(9)
        sig_table.cell(1, 1).paragraphs[0].add_run("主管覆核：__________________\n日期：____ 年 ____ 月 ____ 日").font.size = Pt(9)

        stream = io.BytesIO()
        doc.save(stream)
        return stream.getvalue()

    @staticmethod
    def generate_pdf(
        contact: Contact,
        deal: Deal,
        quote: Quote,
        items_detail: List[Dict[str, Any]],
    ) -> bytes:
        """Generate a tamper-proof A4 commercial quotation PDF using PyMuPDF (fitz)."""
        doc = fitz.open()
        # A4: 595.3 x 841.9 pt
        page = doc.new_page(width=595.3, height=841.9)
        margin = 40.0
        width = 595.3
        
        # Outer Border Box
        page.draw_rect(fitz.Rect(margin, margin, width - margin, 800), color=(0.8, 0.8, 0.8), width=0.8)

        # Header Title Bar
        page.draw_rect(fitz.Rect(margin, margin, width - margin, 95), fill=(0.12, 0.16, 0.23), stroke_opacity=0)
        page.insert_text(fitz.Point(margin + 20, margin + 25), "3Dollar ERP  •  哩來 (LiLai) CRM", fontsize=11, fontname="china-t", color=(0.7, 0.75, 0.85))
        page.insert_text(fitz.Point(margin + 20, margin + 45), "商業報價單 / COMMERCIAL QUOTATION", fontsize=15, fontname="china-t", color=(1.0, 1.0, 1.0))

        # Metadata Section
        y_meta = 120
        # Left side: Customer
        page.insert_text(fitz.Point(margin + 15, y_meta), "【買方 / 客戶資料】", fontsize=10, fontname="china-t", color=(0.2, 0.2, 0.3))
        page.insert_text(fitz.Point(margin + 15, y_meta + 18), f"客戶名稱: {contact.company_name}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(margin + 15, y_meta + 34), f"統一編號: {contact.tax_id or '未提供'}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(margin + 15, y_meta + 50), f"聯絡人員: {contact.contact_name}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(margin + 15, y_meta + 66), f"聯絡電話: {contact.phone or '未提供'}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(margin + 15, y_meta + 82), f"電子信箱: {contact.email or '未提供'}", fontsize=9, fontname="china-t")

        # Right side: Quote & Deal
        x_right = width / 2 + 10
        valid_date_str = quote.valid_until.strftime("%Y-%m-%d") if isinstance(quote.valid_until, (datetime.date, datetime.datetime)) else str(quote.valid_until)
        page.insert_text(fitz.Point(x_right, y_meta), "【單據 / 商機資訊】", fontsize=10, fontname="china-t", color=(0.2, 0.2, 0.3))
        page.insert_text(fitz.Point(x_right, y_meta + 18), f"報價單號: {quote.quote_number}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(x_right, y_meta + 34), f"商機案名: {deal.title}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(x_right, y_meta + 50), f"報價日期: {datetime.date.today().strftime('%Y-%m-%d')}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(x_right, y_meta + 66), f"有效期限: {valid_date_str}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(x_right, y_meta + 82), f"單據狀態: {quote.status.value}", fontsize=9, fontname="china-t")

        # Separator Line
        y_table_top = y_meta + 102
        page.draw_line(fitz.Point(margin + 10, y_table_top), fitz.Point(width - margin - 10, y_table_top), color=(0.8, 0.8, 0.8), width=1.0)

        # Table Header
        y_header = y_table_top + 16
        page.draw_rect(fitz.Rect(margin + 10, y_table_top + 4, width - margin - 10, y_table_top + 24), fill=(0.95, 0.96, 0.98), stroke_opacity=0)
        page.insert_text(fitz.Point(margin + 15, y_header), "#", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.4))
        page.insert_text(fitz.Point(margin + 45, y_header), "品號 (SKU)", fontsize=9, fontname="china-t", color=(0.3, 0.3, 0.4))
        page.insert_text(fitz.Point(margin + 155, y_header), "品名與規格", fontsize=9, fontname="china-t", color=(0.3, 0.3, 0.4))
        page.insert_text(fitz.Point(width - margin - 190, y_header), "數量", fontsize=9, fontname="china-t", color=(0.3, 0.3, 0.4))
        page.insert_text(fitz.Point(width - margin - 125, y_header), "單價 (NT$)", fontsize=9, fontname="china-t", color=(0.3, 0.3, 0.4))
        page.insert_text(fitz.Point(width - margin - 65, y_header), "小計 (NT$)", fontsize=9, fontname="china-t", color=(0.3, 0.3, 0.4))

        # Items Rows
        curr_y = y_header + 20
        total_net = Decimal("0.0")
        for idx, it in enumerate(items_detail, start=1):
            sku = it.get("sku", "")
            name = it.get("name", sku)
            qty = Decimal(str(it.get("qty", "0")))
            price = Decimal(str(it.get("unit_price", "0")))
            subtotal = Decimal(str(it.get("subtotal", qty * price)))
            total_net += subtotal

            page.insert_text(fitz.Point(margin + 15, curr_y), str(idx), fontsize=8.5, fontname="helv")
            page.insert_text(fitz.Point(margin + 45, curr_y), sku, fontsize=8.5, fontname="helv")
            name_display = name[:16] + "..." if len(name) > 18 else name
            page.insert_text(fitz.Point(margin + 155, curr_y), name_display, fontsize=8.5, fontname="china-t")
            page.insert_text(fitz.Point(width - margin - 190, curr_y), f"{qty:,.0f}" if qty % 1 == 0 else f"{qty:,.2f}", fontsize=8.5, fontname="helv")
            page.insert_text(fitz.Point(width - margin - 125, curr_y), f"{price:,.2f}", fontsize=8.5, fontname="helv")
            page.insert_text(fitz.Point(width - margin - 65, curr_y), f"{subtotal:,.2f}", fontsize=8.5, fontname="helv")

            page.draw_line(fitz.Point(margin + 10, curr_y + 6), fitz.Point(width - margin - 10, curr_y + 6), color=(0.92, 0.92, 0.92), width=0.5)
            curr_y += 20

        # Totals
        tax = (total_net * Decimal("0.05")).quantize(Decimal("1"))
        grand_total = total_net + tax

        curr_y += 10
        page.insert_text(fitz.Point(width - margin - 220, curr_y), f"未稅小計 (Subtotal):", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(width - margin - 75, curr_y), f"NT$ {total_net:,.2f}", fontsize=9, fontname="helv")

        curr_y += 16
        page.insert_text(fitz.Point(width - margin - 220, curr_y), f"營業稅 (VAT 5%):", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(width - margin - 75, curr_y), f"NT$ {tax:,.2f}", fontsize=9, fontname="helv")

        curr_y += 18
        page.draw_rect(fitz.Rect(width - margin - 230, curr_y - 12, width - margin - 10, curr_y + 8), fill=(0.93, 0.94, 0.99), stroke_opacity=0)
        page.insert_text(fitz.Point(width - margin - 220, curr_y), f"含稅總計 (Grand Total):", fontsize=10, fontname="china-t", color=(0.2, 0.2, 0.8))
        page.insert_text(fitz.Point(width - margin - 85, curr_y), f"NT$ {grand_total:,.2f}", fontsize=11, fontname="helv", color=(0.2, 0.2, 0.8))

        # Terms & Conditions
        y_terms = 650
        page.draw_line(fitz.Point(margin + 10, y_terms), fitz.Point(width - margin - 10, y_terms), color=(0.8, 0.8, 0.8), width=0.8)
        page.insert_text(fitz.Point(margin + 15, y_terms + 18), "商業約定條款：", fontsize=9, fontname="china-t", color=(0.2, 0.2, 0.3))
        page.insert_text(fitz.Point(margin + 15, y_terms + 34), "1. 報價單有效期間內確認訂購，享有上述報價優惠；逾期請洽業務人員重新評估。", fontsize=8, fontname="china-t", color=(0.4, 0.4, 0.4))
        page.insert_text(fitz.Point(margin + 15, y_terms + 48), "2. 付款方式：雙方確認訂單出貨後 30 天內電匯結清款項。", fontsize=8, fontname="china-t", color=(0.4, 0.4, 0.4))
        page.insert_text(fitz.Point(margin + 15, y_terms + 62), "3. 本報價單經客戶簽名回傳後即生效力，視為正式合約附隨採購意向書。", fontsize=8, fontname="china-t", color=(0.4, 0.4, 0.4))

        # Signatures
        y_sig = 740
        page.draw_line(fitz.Point(margin + 10, y_sig), fitz.Point(width - margin - 10, y_sig), color=(0.8, 0.8, 0.8), width=0.8)
        page.insert_text(fitz.Point(margin + 15, y_sig + 18), "賣方簽章：三圓科技股份有限公司", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(margin + 15, y_sig + 36), "經辦簽核：____________________   日期：____/____/____", fontsize=8, fontname="china-t")

        page.insert_text(fitz.Point(x_right, y_sig + 18), f"買方簽署：{contact.company_name}", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(x_right, y_sig + 36), "客戶簽認：____________________   日期：____/____/____", fontsize=8, fontname="china-t")

        return doc.tobytes()
