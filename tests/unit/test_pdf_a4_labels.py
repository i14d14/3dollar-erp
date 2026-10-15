from __future__ import annotations
import fitz
from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter
from src.core.ports.printer_port import ShippingLabelData


def test_standard_100x150_label():
    printer = PdfPrinterAdapter()
    data = ShippingLabelData(
        do_id="DO-100",
        order_id="SO-100",
        recipient_name="王小明",
        recipient_phone="0912-345-678",
        shipping_address="台北市中正區忠孝西路一段1號",
        tracking_number="TRK-10001",
    )
    pdf_bytes = printer.generate_shipping_label_pdf(data)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    rect = page.rect
    assert round(rect.width, 1) == 283.5
    assert round(rect.height, 1) == 425.2
    text = page.get_text()
    assert "TRK-10001" in text
    assert "DO-100" in text
    assert "王小明" in text


def test_a4_shipping_label_single_and_dimensions():
    printer = PdfPrinterAdapter()
    data = ShippingLabelData(
        do_id="DO-200",
        order_id="SO-200",
        recipient_name="李大華",
        recipient_phone="0988-776-554",
        shipping_address="新北市板橋區縣民大道二段7號",
        tracking_number="TRK-20002",
    )
    pdf_bytes = printer.generate_shipping_label_pdf(data, page_format="A4")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 1
    page = doc[0]
    rect = page.rect
    assert round(rect.width, 1) == 595.3
    assert round(rect.height, 1) == 841.9
    text = page.get_text()
    assert "TRK-20002" in text
    assert "DO-200" in text
    assert "李大華" in text


def test_a4_shipping_labels_multipage_and_start_pos():
    printer = PdfPrinterAdapter()
    labels = [
        ShippingLabelData(
            do_id=f"DO-{i}",
            order_id=f"SO-{i}",
            recipient_name=f"客戶-{i}",
            recipient_phone="0900-000-000",
            shipping_address=f"測試地址 {i} 號",
            tracking_number=f"TRK-900{i}",
        )
        for i in range(1, 6)  # 5 labels -> overflows 4-up grid
    ]

    # Start from position 3 on first sheet -> slots 1, 2 empty, slots 3, 4 filled. Page 2 gets 3 labels.
    pdf_bytes = printer.generate_a4_shipping_labels_pdf(labels, layout="2x2", start_position=3)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert len(doc) == 2

    # Check text across pages
    page1_text = doc[0].get_text()
    assert "TRK-9001" in page1_text
    assert "TRK-9002" in page1_text
    assert "TRK-9003" not in page1_text

    page2_text = doc[1].get_text()
    assert "TRK-9003" in page2_text
    assert "TRK-9004" in page2_text
    assert "TRK-9005" in page2_text
