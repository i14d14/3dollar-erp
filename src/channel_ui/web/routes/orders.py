from __future__ import annotations
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import (
    get_db,
    get_invoice_service,
    get_order_service,
    get_templates,
    get_view_service,
)
from src.channel_ui.web.view_service import WebViewService
from src.core.adapters.mock_invoice_adapter import MockInvoiceProvider
from src.core.adapters.pdf_printer_adapter import PdfPrinterAdapter
from src.core.domain.invoice import Invoice, InvoiceStatus, TaxType
from src.core.ports.printer_port import ShippingLabelData
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.shared.database import Database

router = APIRouter(prefix="/orders")


@router.get("", response_class=HTMLResponse)
async def orders_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    orders = view_service.list_orders()
    return templates.TemplateResponse(
        request=request,
        name="orders.html",
        context={
            "active_page": "orders",
            "orders": orders,
        },
    )


@router.post("/{order_id}/confirm", response_class=HTMLResponse)
async def confirm_order_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    order_service: OrderService = Depends(get_order_service),
):
    try:
        order_service.confirm_order(order_id=order_id, warehouse_id="WH-MAIN")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    return templates.TemplateResponse(
        request=request,
        name="partials/order_row.html",
        context={
            "order": dto,
        },
    )


@router.post("/{order_id}/ship", response_class=HTMLResponse)
async def ship_order_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    order_service: OrderService = Depends(get_order_service),
):
    try:
        order_service.ship_order(
            order_id=order_id,
            warehouse_id="WH-MAIN",
            recipient_name="收件客戶",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區信義路五段7號",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    return templates.TemplateResponse(
        request=request,
        name="partials/order_row.html",
        context={
            "order": dto,
        },
    )


@router.post("/{order_id}/invoice", response_class=HTMLResponse)
async def issue_invoice_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    invoice_service: InvoiceService = Depends(get_invoice_service),
):
    try:
        invoice_service.issue_invoice_for_order(
            order_id=order_id,
            tax_type=TaxType.TAXABLE,
            buyer_name="測試買受人",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    return templates.TemplateResponse(
        request=request,
        name="partials/order_row.html",
        context={
            "order": dto,
        },
    )


@router.get("/{order_id}/label.pdf")
async def download_shipping_label(
    order_id: str,
    db: Database = Depends(get_db),
):
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT do_id, order_id, warehouse_id, tracking_number FROM delivery_orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Shipping delivery order not found for this order")

    printer = PdfPrinterAdapter()
    label_data = ShippingLabelData(
        do_id=row["do_id"],
        order_id=row["order_id"],
        recipient_name="收件客戶",
        recipient_phone="0912-345-678",
        shipping_address="台北市信義區信義路五段7號",
        tracking_number=row["tracking_number"] or "TRK-UNKNOWN",
    )
    pdf_bytes = printer.generate_shipping_label_pdf(label_data)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=shipping_label_{order_id}.pdf"},
    )


@router.get("/{order_id}/invoice.pdf")
async def download_invoice_pdf(
    order_id: str,
    db: Database = Depends(get_db),
):
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT invoice_id, order_id, invoice_number, random_code, tax_type,
                   total_amount, tax_amount, buyer_tax_id, buyer_name, qrcode_l, qrcode_r, status
            FROM invoices WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Electronic invoice not found for this order")

    invoice = Invoice(
        invoice_id=row["invoice_id"],
        order_id=row["order_id"],
        invoice_number=row["invoice_number"],
        random_code=row["random_code"],
        tax_type=TaxType(row["tax_type"]),
        total_amount=Decimal(str(row["total_amount"])),
        tax_amount=Decimal(str(row["tax_amount"])),
        buyer_tax_id=row["buyer_tax_id"],
        buyer_name=row["buyer_name"],
        qrcode_l=row["qrcode_l"],
        qrcode_r=row["qrcode_r"],
        status=InvoiceStatus(row["status"]),
    )

    provider = MockInvoiceProvider()
    pdf_bytes = provider.render_invoice_pdf(invoice)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=invoice_{order_id}.pdf"},
    )
