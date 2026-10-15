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
from src.channel_ui.web.toast_helper import render_toast_oob
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
        order = order_service.get_order(order_id)
        order_service.confirm_order(order_id=order_id, warehouse_id=order.warehouse_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    row_html = templates.get_template("partials/order_row.html").render({
        "request": request,
        "order": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"訂單 {order_id} 鎖庫確認成功！庫存已保留。",
        type="success",
        undo_url=f"/orders/{order_id}/confirm/undo",
        undo_label="撤回鎖庫",
        undo_target=f"#order-row-{order_id}",
        undo_swap="outerHTML",
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")


@router.post("/{order_id}/confirm/undo", response_class=HTMLResponse)
async def undo_confirm_order_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    order_service: OrderService = Depends(get_order_service),
):
    """撤回訂單鎖庫確認，復原至 DRAFT 狀態並釋放庫存鎖定。"""
    try:
        order_service.revert_order_confirmation(order_id=order_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    row_html = templates.get_template("partials/order_row.html").render({
        "request": request,
        "order": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回訂單 {order_id} 鎖庫確認，庫存已原路釋放。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")


@router.get("/{order_id}/ship-modal", response_class=HTMLResponse)
async def get_ship_confirm_modal_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """渲染一鍵出貨前置確認對話框。"""
    try:
        modal_ctx = view_service.get_ship_modal_context(order_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單: {e}")

    return templates.TemplateResponse(
        request=request,
        name="partials/ship_confirm_modal.html",
        context=modal_ctx,
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
        order = order_service.get_order(order_id)
        do, _ = order_service.ship_order(
            order_id=order_id,
            warehouse_id=order.warehouse_id,
            recipient_name="收件客戶",
            recipient_phone="0912-345-678",
            shipping_address="台北市信義區信義路五段7號",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    row_html = templates.get_template("partials/order_row.html").render({
        "request": request,
        "order": dto,
    })
    modal_close_html = '<div id="order-modal-container" hx-swap-oob="innerHTML:#order-modal-container"></div>'
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"訂單 {order_id} 出貨成功！出貨單號：{do.do_id}，實體庫存已扣減並完成銷貨成本入帳。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{modal_close_html}\n{toast_html}")


@router.get("/{order_id}/partial-ship-modal", response_class=HTMLResponse)
async def get_partial_ship_modal_endpoint(
    order_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """渲染拆批出貨前置數量分配對話框。"""
    try:
        modal_ctx = view_service.get_ship_modal_context(order_id)
        warehouses = view_service.list_warehouses_for_select()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單: {e}")

    modal_ctx["warehouses"] = warehouses
    return templates.TemplateResponse(
        request=request,
        name="partials/partial_ship_modal.html",
        context=modal_ctx,
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
    shipping_wh = str(form.get("warehouse_id") or order.warehouse_id or "WH-MAIN").strip()
    for item in order.items:
        key = f"qty_{item.item_id}"
        if key in form and form[key]:
            val = Decimal(str(form[key]))
            if val > Decimal("0.0"):
                items_to_ship.append((item.item_id, val))

    try:
        do, _ = order_service.ship_order(
            order_id=order_id,
            warehouse_id=shipping_wh,
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

    row_html = templates.get_template("partials/order_row.html").render({
        "request": request,
        "order": dto,
    })
    modal_close_html = '<div id="order-modal-container" hx-swap-oob="innerHTML:#order-modal-container"></div>'
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"訂單 {order_id} 拆批出貨成功！出貨單號：{do.do_id}（出貨倉：{shipping_wh}），實體庫存已扣減並完成銷貨成本入帳。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{modal_close_html}\n{toast_html}")



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
    view_service: WebViewService = Depends(get_view_service),
):
    try:
        order = order_service.get_order(order_id)
        deliveries = view_service.get_order_deliveries_view(order_id)
        cust_dto = view_service.get_order_row(order_id)
        customer_name = cust_dto.customer_name if cust_dto else None
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"找不到訂單出貨紀錄: {e}")

    return templates.TemplateResponse(
        request=request,
        name="partials/deliveries_modal.html",
        context={"order": order, "deliveries": deliveries, "customer_name": customer_name},
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
        inv, _, _ = invoice_service.issue_invoice_for_order(
            order_id=order_id,
            tax_type=TaxType.TAXABLE,
            buyer_name="測試買受人",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_order_row(order_id)
    if not dto:
        raise HTTPException(status_code=404, detail="Order not found")

    row_html = templates.get_template("partials/order_row.html").render({
        "request": request,
        "order": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"電子發票開立成功！發票號碼：{inv.invoice_number}，已自動計入營業稅與銷貨收入。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")



@router.get("/{order_id}/label.pdf")
async def download_shipping_label(
    order_id: str,
    do_id: Optional[str] = None,
    db: Database = Depends(get_db),
):
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
        raise HTTPException(status_code=404, detail="找不到該出貨單 (Shipping delivery order not found)")

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
    pdf_bytes = printer.generate_shipping_labels_pdf(labels, page_format="100x150")
    filename = f"shipping_label_{rows[0]['do_id']}.pdf" if len(rows) == 1 else f"shipping_labels_{order_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"},
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
