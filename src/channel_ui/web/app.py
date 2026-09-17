from __future__ import annotations
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.demo_seed import seed_demo_data
from src.channel_ui.web.routes.accounting import router as accounting_router
from src.channel_ui.web.routes.crm import router as crm_router
from src.channel_ui.web.routes.dashboard import router as dashboard_router
from src.channel_ui.web.routes.inventory import router as inventory_router
from src.channel_ui.web.routes.orders import router as orders_router

from src.channel_ui.web.view_service import WebViewService
from src.core.ports.event_bus_port import EventBusPort
from src.extended_core.accounting.services.event_handlers import register_accounting_event_handlers
from src.shared.database import Database, default_db
from src.shared.event_bus import EventBus

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


import re


def format_user_error_message(detail: str) -> str:
    """Normalize any raw domain exception or English error message into friendly Traditional Chinese."""
    if not detail:
        return "操作未完成"
    s = str(detail).strip()

    # Pattern: Cannot lock stock for order X: Insufficient available stock for SKU Y in W. Available: A, Required: R
    m = re.search(
        r"Cannot lock stock for order ([^:]+):\s*Insufficient available stock for SKU ([^ ]+) in ([^.]+)\.\s*Available:\s*(\d+(?:\.\d+)?),\s*Required:\s*(\d+(?:\.\d+)?)",
        s,
    )
    if m:
        return f"無法鎖定訂單 {m.group(1)} 庫存：倉庫 {m.group(3)} 之商品 {m.group(2)} 可用庫存不足（可用量：{m.group(4)}，需求量：{m.group(5)}）"

    # Pattern: Transfer rejected: Insufficient available stock in W for SKU. Available: A, Requested: R
    m2 = re.search(
        r"Transfer rejected:\s*Insufficient available stock in ([^ ]+) for ([^.]+)\.\s*Available:\s*(\d+(?:\.\d+)?),\s*Requested:\s*(\d+(?:\.\d+)?)",
        s,
    )
    if m2:
        return f"調撥失敗：倉庫 {m2.group(1)} 之商品 {m2.group(2)} 可用庫存不足（可用量：{m2.group(3)}，需求量：{m2.group(4)}）"

    # Pattern: Cannot ship order X: status is 'Y', expected 'Z'
    m3 = re.search(r"Cannot ship order ([^:]+):\s*status is '([^']+)', expected '([^']+)'", s)
    if m3:
        return f"無法出貨訂單 {m3.group(1)}：目前狀態為 '{m3.group(2)}'，僅 '{m3.group(3)}' 狀態可執行出貨扣庫"

    # Pattern: Cannot confirm order X: status is 'Y', expected 'Z'
    m4 = re.search(r"Cannot confirm order ([^:]+):\s*status is '([^']+)', expected '([^']+)'", s)
    if m4:
        return f"無法確認訂單 {m4.group(1)}：目前狀態為 '{m4.group(2)}'，僅 '{m4.group(3)}' 狀態可進行鎖庫確認"

    # Pattern: Cannot cancel order X: already Y
    m_cancel = re.search(r"Cannot cancel order ([^:]+):\s*already ([^ ]+)", s)
    if m_cancel:
        return f"無法取消訂單 {m_cancel.group(1)}：單據目前為 '{m_cancel.group(2)}' 狀態，不可取消"

    # Pattern: Product with SKU 'X' does not exist
    m5 = re.search(r"Product with SKU '([^']+)' does not exist", s)
    if m5:
        return f"商品品號 '{m5.group(1)}' 不存在"

    # Pattern: Warehouse 'X' does not exist
    m6 = re.search(r"Warehouse '([^']+)' does not exist", s)
    if m6:
        return f"倉庫 '{m6.group(1)}' 不存在"

    # Pattern: Sales order X not found
    m7 = re.search(r"Sales order ([^ ]+) not found", s)
    if m7:
        return f"查無銷售訂單 {m7.group(1)}"

    # Pattern: Invoice already issued for order X
    m8 = re.search(r"Invoice already issued for order ([^:]+)", s)
    if m8:
        return f"訂單 {m8.group(1)} 已開立過發票，不可重複開立"

    # CRM Domain Error Translations
    if "Tax ID must be 8 digits" in s or "統一編號" in s:
        return "統一編號格式錯誤：必須為 8 位純數字"
    if "Contact not found" in s or "指定的客戶不存在" in s or "查無客戶" in s:
        return "查無指定之客戶資料"
    if "Deal not found" in s or "查無商機" in s:
        return "查無指定之商機資料"
    if "Quote not found" in s or "查無報價單" in s:
        return "查無指定之報價單資料"
    if "Quote with items required" in s or "缺乏有效報價單與明細" in s:
        return "此商機尚未建立任何報價單明細，無法執行拋轉 ERP 銷售訂單"
    if "Deal already converted" in s or "不可重複轉單" in s:
        return "此商機先前已成功拋轉為 ERP 銷售訂單，不可重複轉單"
    if "stage is locked" in s or "狀態已鎖定為贏單" in s:
        return "商機已拋轉為 ERP 訂單，狀態已鎖定為贏單，不可任意變更"

    # Strip any trailing English tag in parentheses e.g. " (Insufficient available stock)"
    s = re.sub(r"\s*\([A-Za-z0-9_\- :.,]+\)$", "", s)

    return s



def create_app(db: Optional[Database] = None, event_bus: Optional[EventBusPort] = None) -> FastAPI:
    app = FastAPI(
        title="3Dollar ERP Web Admin",
        description="Zero-Build SSR Admin Web GUI for Dinkoko ERP (FastAPI + HTMX + Tailwind)",
        version="1.0.0",
    )

    app_db = db or default_db
    app_bus = event_bus or EventBus()
    register_accounting_event_handlers(event_bus=app_bus, db=app_db)
    seed_demo_data(app_db, event_bus=app_bus)
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    view_service = WebViewService(db=app_db)

    app.state.db = app_db
    app.state.event_bus = app_bus
    app.state.templates = templates
    app.state.view_service = view_service

    # Custom exception handler for HTMX requests
    @app.exception_handler(HTTPException)
    async def htmx_http_exception_handler(request: Request, exc: HTTPException):
        # If request is from HTMX, return a visual error toast/banner to #toast-container via OOB swap
        if request.headers.get("HX-Request") == "true":
            user_msg = format_user_error_message(exc.detail)
            return HTMLResponse(
                content=f"""
                <div id="toast-container" hx-swap-oob="innerHTML:#toast-container">
                  <div class="p-3 my-2 text-xs text-rose-800 bg-rose-50 border border-rose-300 rounded-lg flex items-center justify-between shadow-sm">
                    <div class="flex items-center gap-2">
                      <span class="text-rose-600 font-bold text-sm">⚠️</span>
                      <span class="font-medium">執行失敗: {user_msg}</span>
                    </div>
                    <button onclick="document.getElementById('toast-container').innerHTML=''" class="text-rose-400 hover:text-rose-700 font-bold ml-2 text-base leading-none">&times;</button>
                  </div>
                </div>
                """,
                status_code=exc.status_code,
                headers={"HX-Reswap": "none"},
            )
        # Default fallback
        return HTMLResponse(
            content=f"<h1>Error {exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )

    # Generic catch-all exception handler to prevent raw tracebacks from leaking to UI
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        if request.headers.get("HX-Request") == "true":
            return HTMLResponse(
                content=f"""
                <div id="toast-container" hx-swap-oob="innerHTML:#toast-container">
                  <div class="p-3 my-2 text-xs text-rose-800 bg-rose-50 border border-rose-300 rounded-lg flex items-center justify-between shadow-sm">
                    <div class="flex items-center gap-2">
                      <span class="text-rose-600 font-bold text-sm">🚨</span>
                      <span class="font-medium">系統發生非預期異常，已記錄日誌，請稍後再試。</span>
                    </div>
                    <button onclick="document.getElementById('toast-container').innerHTML=''" class="text-rose-400 hover:text-rose-700 font-bold ml-2 text-base leading-none">&times;</button>
                  </div>
                </div>
                """,
                status_code=500,
                headers={"HX-Reswap": "none"},
            )
        return HTMLResponse(
            content="<h1>500 Internal Server Error</h1><p>系統發生非預期異常</p>",
            status_code=500,
        )

    # Register routes
    app.include_router(dashboard_router)
    app.include_router(orders_router)
    app.include_router(inventory_router)
    app.include_router(accounting_router)
    app.include_router(crm_router)

    return app



app = create_app()
