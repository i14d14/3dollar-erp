from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import get_templates
from src.shared.database import Database, default_db

router = APIRouter(prefix="/demo", tags=["demo"])


@router.get("/line", response_class=HTMLResponse)
async def line_simulator_page(
    request: Request,
    order_id: str,
    templates: Jinja2Templates = Depends(get_templates),
):
    """Render simulated LINE Mobile chat view with real order Flex Card for automated video demos."""
    db = default_db
    with db.transaction() as conn:
        # Fetch order
        so = conn.execute(
            "SELECT total_amount, status FROM sales_orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        total_amount = f"{float(so['total_amount']):,.0f}" if so else "50,000"

        # Fetch DO & tracking number
        do_row = conn.execute(
            "SELECT do_id, tracking_number FROM delivery_orders WHERE order_id = ? ORDER BY rowid DESC LIMIT 1",
            (order_id,),
        ).fetchone()
        do_id = do_row["do_id"] if do_row else "DO-202609-001"
        tracking_number = do_row["tracking_number"] if do_row else "SF-889123456"

        # Fetch invoice
        inv_row = conn.execute(
            "SELECT invoice_number FROM invoices WHERE order_id = ? LIMIT 1",
            (order_id,),
        ).fetchone()
        invoice_number = inv_row["invoice_number"] if inv_row else "AB-88992211"

    return templates.TemplateResponse(
        request=request,
        name="line_simulator.html",
        context={
            "order_id": order_id,
            "total_amount": total_amount,
            "do_id": do_id,
            "tracking_number": tracking_number,
            "invoice_number": invoice_number,
        },
    )
