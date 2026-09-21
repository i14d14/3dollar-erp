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


@router.get("/{order_id}/partial-ship-modal", response_class=HTMLResponse)
async def get_partial_ship_modal_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    order_service: OrderService = Depends(get_order_service),
):
    try:
        order = order_service.get_order(order_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單: {e}")

    return templates.TemplateResponse(
        request=request,
        name="partials/partial_ship_modal.html",
        context={"order": order},
    )


@router.post("/{order_id}/ship-partial", response_class=HTMLResponse)
async def ship_partial_order_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    order_service: OrderService = Depends(get_order_service),
):
    form = await request.form()
    items_to_ship = []
    order = order_service.get_order(order_id)
    for item in order.items:
        key = f"qty_{item.item_id}"
        if key in form and form[key]:
            val = Decimal(str(form[key]))
            if val > Decimal("0.0"):
                items_to_ship.append((item.item_id, val))

    try:
        order_service.ship_order(
            order_id=order_id,
            warehouse_id="WH-MAIN",
            recipient_name="收件客戶",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區信義路五段7號",
            items_to_ship=items_to_ship if items_to_ship else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    return templates.TemplateResponse(
        request=request,
        name="partials/order_row.html",
        context={"order": dto},
    )


@router.get("/{order_id}/deliveries")
async def get_order_deliveries_endpoint(
    order_id: str,
    order_service: OrderService = Depends(get_order_service),
):
    deliveries = order_service.get_order_deliveries(order_id)
    return [
        {
            "do_id": d.do_id,
            "order_id": d.order_id,
            "warehouse_id": d.warehouse_id,
            "tracking_number": d.tracking_number,
            "allocations": [
                {
                    "sku": a.sku,
                    "allocated_qty": float(a.allocated_qty),
                }
                for a in d.allocations
            ],
        }
        for d in deliveries
    ]


@router.get("/{order_id}/deliveries-modal", response_class=HTMLResponse)
async def get_deliveries_modal_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    order_service: OrderService = Depends(get_order_service),
):
    try:
        order = order_service.get_order(order_id)
        deliveries = order_service.get_order_deliveries(order_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單出貨紀錄: {e}")

    return templates.TemplateResponse(
        request=request,
        name="partials/deliveries_modal.html",
        context={"order": order, "deliveries": deliveries},
    )


@router.get("/{order_id}/a4-label-modal", response_class=HTMLResponse)
async def get_a4_label_modal_endpoint(
    order_id: str,
    request: Request,
    do_id: Optional[str] = None,
    templates: Jinja2Templates = Depends(get_templates),
    order_service: OrderService = Depends(get_order_service),
):
    try:
        order = order_service.get_order(order_id)
        deliveries = order_service.get_order_deliveries(order_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單資料: {e}")

    return templates.TemplateResponse(
        request=request,
        name="partials/a4_label_modal.html",
        context={
            "order": order,
            "deliveries": deliveries,
            "selected_do_id": do_id,
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
    do_id: Optional[str] = None,
    db: Database = Depends(get_db),
):
    with db.transaction() as conn:
        if do_id and do_id.strip():
            row = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number FROM delivery_orders WHERE order_id = ? AND do_id = ?",
                (order_id, do_id.strip()),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number FROM delivery_orders WHERE order_id = ? ORDER BY rowid DESC LIMIT 1",
                (order_id,),
            ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="找不到該出貨單 (Shipping delivery order not found)")

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
        headers={"Content-Disposition": f"inline; filename=shipping_label_{row['do_id']}.pdf"},
    )


@router.get("/{order_id}/label_a4.pdf")
async def download_shipping_label_a4(
    order_id: str,
    start_pos: int = 1,
    do_id: Optional[str] = None,
    db: Database = Depends(get_db),
):
    if not (1 <= start_pos <= 4):
        raise HTTPException(status_code=400, detail="起印格位 (start_pos) 必須在 1 到 4 之間")

    with db.transaction() as conn:
        if do_id and do_id.strip():
            rows = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number FROM delivery_orders WHERE order_id = ? AND do_id = ?",
                (order_id, do_id.strip()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT do_id, order_id, warehouse_id, tracking_number FROM delivery_orders WHERE order_id = ? ORDER BY rowid ASC",
                (order_id,),
            ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="找不到該訂單之出貨單據 (Delivery order not found)")

    printer = PdfPrinterAdapter()
    labels = [
        ShippingLabelData(
            do_id=r["do_id"],
            order_id=r["order_id"],
            recipient_name="收件客戶",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區信義路五段7號",
            tracking_number=r["tracking_number"] or "TRK-UNKNOWN",
        )
        for r in rows
    ]

    pdf_bytes = printer.generate_a4_shipping_labels_pdf(labels, layout="2x2", start_position=start_pos)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=shipping_label_a4_{order_id}.pdf"},
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
