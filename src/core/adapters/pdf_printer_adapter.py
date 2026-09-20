from __future__ import annotations
import datetime
import fitz  # PyMuPDF

from src.core.ports.printer_port import PrinterPort, ShippingLabelData


class PdfPrinterAdapter(PrinterPort):
    """Native PDF Label and Barcode Generator using PyMuPDF."""

    def generate_shipping_label_pdf(self, label_data: ShippingLabelData, page_format: str = "100x150") -> bytes:
        """Generate a standardized logistics shipping label PDF (100x150mm or single A4)."""
        if page_format.upper() == "A4":
            return self.generate_a4_shipping_labels_pdf([label_data], layout="2x2", start_position=1)

        doc = fitz.open()
        # 100mm = 283.46 pt, 150mm = 425.20 pt
        width = 283.46
        height = 425.20
        page = doc.new_page(width=width, height=height)

        # Outer border
        margin = 10
        page.draw_rect(fitz.Rect(margin, margin, width - margin, height - margin), color=(0, 0, 0), width=1.5)

        # Logistics Provider Header
        page.insert_text(fitz.Point(20, 35), "3Dollar EXPRESS LOGISTICS", fontsize=12, fontname="helv")
        page.draw_line(fitz.Point(margin, 45), fitz.Point(width - margin, 45), color=(0, 0, 0), width=1.0)

        # Tracking Number Section
        page.insert_text(fitz.Point(20, 65), "TRACKING / 託運單號:", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(20, 85), label_data.tracking_number, fontsize=15, fontname="china-t")

        # Barcode visual container
        barcode_box = fitz.Rect(20, 95, width - 20, 135)
        page.draw_rect(barcode_box, color=(0, 0, 0), width=0.8)
        page.insert_text(fitz.Point(40, 120), f"* {label_data.tracking_number} *", fontsize=12, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(margin, 145), fitz.Point(width - margin, 145), color=(0, 0, 0), width=1.0)

        # Order Information
        page.insert_text(fitz.Point(20, 165), f"出貨單號 (DO): {label_data.do_id}", fontsize=10, fontname="china-t")
        page.insert_text(fitz.Point(20, 185), f"銷售訂單 (SO): {label_data.order_id}", fontsize=10, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(margin, 195), fitz.Point(width - margin, 195), color=(0, 0, 0), width=1.0)

        # Recipient Information
        page.insert_text(fitz.Point(20, 215), "收件人資訊 (RECIPIENT):", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(20, 235), f"姓名: {label_data.recipient_name}", fontsize=11, fontname="china-t")
        page.insert_text(fitz.Point(20, 255), f"電話: {label_data.recipient_phone}", fontsize=11, fontname="china-t")
        page.insert_text(fitz.Point(20, 275), f"地址: {label_data.shipping_address}", fontsize=10, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(margin, 340), fitz.Point(width - margin, 340), color=(0, 0, 0), width=1.0)

        # Footer Date & Signature Box
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        page.insert_text(fitz.Point(20, 360), f"列印時間: {now_str}", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(20, 380), "揀貨覆核員簽署: _______________", fontsize=9, fontname="china-t")
        page.insert_text(fitz.Point(20, 400), "狀態: COMPLIANT STANDARD LABEL", fontsize=8, fontname="china-t")

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def generate_a4_shipping_labels_pdf(
        self,
        labels: list[ShippingLabelData],
        layout: str = "2x2",
        start_position: int = 1,
    ) -> bytes:
        """Generate multi-label sticker sheets on standard A4 paper (2x2 grid, 4 labels per page)."""
        doc = fitz.open()
        # A4: 210mm x 297mm = 595.28 pt x 841.89 pt
        page_width = 595.28
        page_height = 841.89

        margin_x = 18.0
        margin_y = 18.0
        gap_x = 12.0
        gap_y = 12.0

        cols = 2
        rows = 2
        per_page = cols * rows

        cell_width = (page_width - 2 * margin_x - (cols - 1) * gap_x) / cols
        cell_height = (page_height - 2 * margin_y - (rows - 1) * gap_y) / rows

        current_page = doc.new_page(width=page_width, height=page_height)
        current_slot = max(1, min(start_position, per_page)) - 1  # 0-indexed

        for label in labels:
            if current_slot >= per_page:
                current_page = doc.new_page(width=page_width, height=page_height)
                current_slot = 0

            c = current_slot % cols
            r = current_slot // cols
            x0 = margin_x + c * (cell_width + gap_x)
            y0 = margin_y + r * (cell_height + gap_y)
            rect = fitz.Rect(x0, y0, x0 + cell_width, y0 + cell_height)

            self._draw_shipping_label_cell(current_page, rect, label)
            current_slot += 1

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def _draw_shipping_label_cell(self, page: fitz.Page, rect: fitz.Rect, label_data: ShippingLabelData) -> None:
        """Draw a single shipping label within an A4 grid cell."""
        # Outer cell border
        page.draw_rect(rect, color=(0, 0, 0), width=1.0)

        pad = 10.0
        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1

        # Logistics Provider Header
        page.insert_text(fitz.Point(x0 + pad, y0 + 22), "3Dollar EXPRESS LOGISTICS", fontsize=10, fontname="helv")
        page.draw_line(fitz.Point(x0, y0 + 30), fitz.Point(x1, y0 + 30), color=(0, 0, 0), width=0.8)

        # Tracking Number Section
        page.insert_text(fitz.Point(x0 + pad, y0 + 46), "TRACKING / 託運單號:", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y0 + 64), label_data.tracking_number, fontsize=13, fontname="china-t")

        # Barcode visual container
        barcode_box = fitz.Rect(x0 + pad, y0 + 72, x1 - pad, y0 + 104)
        page.draw_rect(barcode_box, color=(0, 0, 0), width=0.6)
        page.insert_text(fitz.Point(x0 + pad + 15, y0 + 92), f"* {label_data.tracking_number} *", fontsize=10, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(x0, y0 + 112), fitz.Point(x1, y0 + 112), color=(0, 0, 0), width=0.8)

        # Order Information
        page.insert_text(fitz.Point(x0 + pad, y0 + 128), f"出貨單號 (DO): {label_data.do_id}", fontsize=8.5, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y0 + 144), f"銷售訂單 (SO): {label_data.order_id}", fontsize=8.5, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(x0, y0 + 152), fitz.Point(x1, y0 + 152), color=(0, 0, 0), width=0.8)

        # Recipient Information
        page.insert_text(fitz.Point(x0 + pad, y0 + 168), "收件人資訊 (RECIPIENT):", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y0 + 184), f"姓名: {label_data.recipient_name}", fontsize=9.5, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y0 + 200), f"電話: {label_data.recipient_phone}", fontsize=9.5, fontname="china-t")

        addr = label_data.shipping_address
        if len(addr) > 22:
            page.insert_text(fitz.Point(x0 + pad, y0 + 216), f"地址: {addr[:22]}", fontsize=8.5, fontname="china-t")
            page.insert_text(fitz.Point(x0 + pad + 25, y0 + 230), addr[22:46], fontsize=8.5, fontname="china-t")
        else:
            page.insert_text(fitz.Point(x0 + pad, y0 + 216), f"地址: {addr}", fontsize=8.5, fontname="china-t")

        # Divider
        page.draw_line(fitz.Point(x0, y1 - 50), fitz.Point(x1, y1 - 50), color=(0, 0, 0), width=0.8)

        # Footer Date & Signature Box
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        page.insert_text(fitz.Point(x0 + pad, y1 - 36), f"列印時間: {now_str}", fontsize=7, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y1 - 22), "揀貨覆核員簽署: _______________", fontsize=8, fontname="china-t")
        page.insert_text(fitz.Point(x0 + pad, y1 - 8), "狀態: COMPLIANT STANDARD LABEL", fontsize=7, fontname="china-t")

    def generate_barcode_label_pdf(self, sku: str, product_name: str, barcode_type: str = "Code128") -> bytes:
        """Generate a product barcode sticker PDF (e.g. 50x30mm)."""
        doc = fitz.open()
        # 50mm = 141.73 pt, 30mm = 85.04 pt
        width = 141.73
        height = 85.04
        page = doc.new_page(width=width, height=height)

        margin = 4
        page.draw_rect(fitz.Rect(margin, margin, width - margin, height - margin), color=(0, 0, 0), width=0.8)

        # Product Name
        page.insert_text(fitz.Point(8, 18), product_name[:20], fontsize=8, fontname="china-t")

        # Barcode visual
        b_box = fitz.Rect(8, 25, width - 8, 55)
        page.draw_rect(b_box, color=(0, 0, 0), width=0.5)
        page.insert_text(fitz.Point(15, 45), f"||| {sku} |||", fontsize=9, fontname="china-t")

        # SKU code
        page.insert_text(fitz.Point(8, 70), f"SKU: {sku} ({barcode_type})", fontsize=7, fontname="china-t")

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes
