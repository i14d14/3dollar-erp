from __future__ import annotations
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.routes.dashboard import router as dashboard_router
from src.channel_ui.web.routes.inventory import router as inventory_router
from src.channel_ui.web.routes.orders import router as orders_router
from src.channel_ui.web.view_service import WebViewService
from src.shared.database import Database, default_db

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def create_app(db: Optional[Database] = None) -> FastAPI:
    app = FastAPI(
        title="3Dollar ERP Web Admin",
        description="Zero-Build SSR Admin Web GUI for Dinkoko ERP (FastAPI + HTMX + Tailwind)",
        version="1.0.0",
    )

    app_db = db or default_db
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    view_service = WebViewService(db=app_db)

    app.state.db = app_db
    app.state.templates = templates
    app.state.view_service = view_service

    # Custom exception handler for HTMX requests
    @app.exception_handler(HTTPException)
    async def htmx_http_exception_handler(request: Request, exc: HTTPException):
        # If request is from HTMX, return a visual error toast/banner
        if request.headers.get("HX-Request") == "true":
            return HTMLResponse(
                content=f"""
                <div class="p-3 my-2 text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg flex items-center justify-between">
                  <span class="font-medium">⚠️ 執行失敗: {exc.detail}</span>
                  <button onclick="this.parentElement.remove()" class="text-rose-500 hover:text-rose-700 font-bold ml-2">&times;</button>
                </div>
                """,
                status_code=exc.status_code,
            )
        # Default fallback
        return HTMLResponse(
            content=f"<h1>Error {exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )

    # Register routes
    app.include_router(dashboard_router)
    app.include_router(orders_router)
    app.include_router(inventory_router)

    return app


app = create_app()
