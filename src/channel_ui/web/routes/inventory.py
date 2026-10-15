from __future__ import annotations
import datetime
import io
import uuid
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import (
    get_db,
    get_inventory_service,
    get_templates,
    get_view_service,
)
from src.channel_ui.web.toast_helper import render_toast_oob
from src.channel_ui.web.view_service import WebViewService
from src.core.services.inventory_service import InventoryService
from src.extended_core.accounting.services.excel_report_generator import AdvancedReportGenerator
from src.shared.database import Database

router = APIRouter(prefix="/inventory")


@router.get("/export/stock-valuation.xlsx")
async def export_stock_valuation_excel(
    db: Database = Depends(get_db),
):
    """匯出雙倉庫存盤點與估值底冊 Excel 活頁簿。"""
    generator = AdvancedReportGenerator(db=db)
    content = generator.generate_stock_inventory_valuation_excel()
    filename = f"stock_valuation_{datetime.date.today().isoformat()}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    stocks = view_service.list_inventory_stocks()
    ledger_movements = view_service.list_recent_ledger_movements()
    warehouses = view_service.list_warehouses_for_select()
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={
            "active_page": "inventory",
            "stocks": stocks,
            "ledger_movements": ledger_movements,
            "warehouses": warehouses,
        },
    )


@router.post("/transfer", response_class=HTMLResponse)
async def transfer_stock_endpoint(
    request: Request,
    from_warehouse_id: str = Form(...),
    to_warehouse_id: str = Form(...),
    sku: str = Form(...),
    qty: float = Form(...),
    to_safety_stock: Optional[int] = Form(None),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    clean_sku = sku.strip().upper()
    qty_dec = Decimal(str(qty))
    ref_id = f"TRF-{uuid.uuid4().hex[:8].upper()}"
    try:
        inventory_service.transfer_stock(
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            sku=clean_sku,
            qty=qty_dec,
            reference_id=ref_id,
            notes=f"Web Admin UI Transfer ({from_warehouse_id} -> {to_warehouse_id})",
            to_safety_stock=to_safety_stock,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    from_wh = inventory_service.get_warehouse(from_warehouse_id)
    to_wh = inventory_service.get_warehouse(to_warehouse_id)
    from_name = from_wh.name if from_wh else from_warehouse_id
    to_name = to_wh.name if to_wh else to_warehouse_id
    qty_display = int(qty_dec) if qty_dec == int(qty_dec) else qty_dec

    stocks = view_service.list_inventory_stocks()
    recent_ledger = view_service.list_recent_ledger_movements()

    stock_html = templates.get_template("partials/stock_table.html").render({
        "request": request,
        "stocks": stocks,
    })
    ledger_html = templates.get_template("partials/ledger_table.html").render({
        "request": request,
        "ledger_movements": recent_ledger,
        "oob": True,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"調撥成功！已由 {from_name} 調撥 {qty_display} 件 {clean_sku} 至 {to_name}",
        type="success",
        undo_url="/inventory/transfer/undo",
        undo_label="撤回調撥",
        undo_target="#stock-table-container",
        undo_swap="outerHTML",
        undo_vals={"ref_id": ref_id},
        ttl_seconds=6,
    )

    return HTMLResponse(content=f"{stock_html}\n{ledger_html}\n{toast_html}")


@router.post("/transfer/undo", response_class=HTMLResponse)
async def undo_transfer_endpoint(
    request: Request,
    ref_id: str = Form(...),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    clean_ref_id = ref_id.strip()
    try:
        inventory_service.revert_transfer(reference_id=clean_ref_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    stocks = view_service.list_inventory_stocks()
    recent_ledger = view_service.list_recent_ledger_movements()

    stock_html = templates.get_template("partials/stock_table.html").render({
        "request": request,
        "stocks": stocks,
    })
    ledger_html = templates.get_template("partials/ledger_table.html").render({
        "request": request,
        "ledger_movements": recent_ledger,
        "oob": True,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回調撥 ({clean_ref_id})，庫存已原路歸還。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )

    return HTMLResponse(content=f"{stock_html}\n{ledger_html}\n{toast_html}")


@router.get("/safety-stock/edit", response_class=HTMLResponse)
async def edit_safety_stock_cell_endpoint(
    warehouse_id: str,
    sku: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    clean_sku = sku.strip().upper()
    safety = inventory_service.get_warehouse_safety_stock(warehouse_id, clean_sku)
    return templates.TemplateResponse(
        request=request,
        name="partials/safety_stock_edit.html",
        context={
            "warehouse_id": warehouse_id,
            "sku": clean_sku,
            "safety_stock": safety,
        },
    )


@router.get("/safety-stock/cancel", response_class=HTMLResponse)
async def cancel_safety_stock_cell_endpoint(
    warehouse_id: str,
    sku: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    clean_sku = sku.strip().upper()
    safety = inventory_service.get_warehouse_safety_stock(warehouse_id, clean_sku)
    return templates.TemplateResponse(
        request=request,
        name="partials/safety_stock_cell.html",
        context={
            "warehouse_id": warehouse_id,
            "sku": clean_sku,
            "safety_stock": safety,
        },
    )


@router.post("/safety-stock", response_class=HTMLResponse)
async def update_safety_stock_endpoint(
    request: Request,
    warehouse_id: str = Form(...),
    sku: str = Form(...),
    safety_stock: int = Form(...),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    inventory_service: InventoryService = Depends(get_inventory_service),
):
    clean_sku = sku.strip().upper()
    try:
        updated_val = inventory_service.upsert_warehouse_safety_stock(
            warehouse_id=warehouse_id,
            sku=clean_sku,
            safety_stock=safety_stock,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    stock_row_dto = view_service.get_inventory_stock_row(warehouse_id, clean_sku)
    if not stock_row_dto:
        raise HTTPException(status_code=404, detail=f"查無庫存項目 {warehouse_id} / {clean_sku}")

    wh = inventory_service.get_warehouse(warehouse_id)
    wh_name = wh.name if wh else warehouse_id

    row_html = templates.get_template("partials/stock_row.html").render({
        "request": request,
        "item": stock_row_dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功將【{wh_name}】之商品【{clean_sku}】安全存量更新為 {updated_val}！",
        type="success",
        ttl_seconds=5,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")

