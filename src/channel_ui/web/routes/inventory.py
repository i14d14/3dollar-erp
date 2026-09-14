from __future__ import annotations
import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.view_service import WebViewService
from src.core.services.inventory_service import InventoryService
from src.shared.database import Database

router = APIRouter(prefix="/inventory")


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_view_service(request: Request) -> WebViewService:
    return request.app.state.view_service


def get_db(request: Request) -> Database:
    return request.app.state.db


@router.get("", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    stocks = view_service.list_inventory_stocks()
    ledger_movements = view_service.list_recent_ledger_movements()
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={
            "active_page": "inventory",
            "stocks": stocks,
            "ledger_movements": ledger_movements,
        },
    )


@router.post("/transfer", response_class=HTMLResponse)
async def transfer_stock_endpoint(
    request: Request,
    from_warehouse_id: str = Form(...),
    to_warehouse_id: str = Form(...),
    sku: str = Form(...),
    qty: float = Form(...),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    db: Database = Depends(get_db),
):
    inventory_service = InventoryService(db=db)
    ref_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
    try:
        inventory_service.transfer_stock(
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            sku=sku.strip().upper(),
            qty=Decimal(str(qty)),
            reference_id=ref_id,
            notes=f"Web Admin UI Transfer ({from_warehouse_id} -> {to_warehouse_id})",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    stocks = view_service.list_inventory_stocks()
    return templates.TemplateResponse(
        request=request,
        name="partials/stock_table.html",
        context={
            "stocks": stocks,
        },
    )
