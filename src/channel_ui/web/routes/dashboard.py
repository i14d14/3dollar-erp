from __future__ import annotations
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.view_service import WebViewService

router = APIRouter()


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_view_service(request: Request) -> WebViewService:
    return request.app.state.view_service


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    summary = view_service.get_dashboard_summary()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_page": "dashboard",
            "summary": summary,
        },
    )
