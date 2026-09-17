from __future__ import annotations
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import (
    get_crm_service,
    get_templates,
    get_view_service,
)
from src.channel_ui.web.view_service import WebViewService
from src.extended_core.crm.models import DealStage
from src.extended_core.crm.services.crm_service import CrmService

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("", response_class=HTMLResponse)
async def crm_page(
    request: Request,
    tab: str = "kanban",
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """哩來 (LiLai) CRM 首頁：展示商機四段看板、客戶主檔清單與即時業務 KPI。"""
    summary = view_service.get_crm_summary()
    kanban = view_service.get_crm_kanban()
    contacts = view_service.list_contacts_with_stats()
    products = view_service.list_active_products_for_quote()

    return templates.TemplateResponse(
        request=request,
        name="crm.html",
        context={
            "active_page": "crm",
            "active_tab": tab,
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        },
    )


@router.post("/contacts", response_class=HTMLResponse)
async def create_contact_endpoint(
    request: Request,
    company_name: str = Form(...),
    contact_name: str = Form(...),
    tax_id: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """新增客戶主檔，支援統編檢驗。"""
    try:
        crm_service.create_contact(
            company_name=company_name,
            contact_name=contact_name,
            tax_id=tax_id if tax_id and tax_id.strip() else None,
            email=email if email and email.strip() else None,
            phone=phone if phone and phone.strip() else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        contacts = view_service.list_contacts_with_stats()
        kanban = view_service.get_crm_kanban()
        products = view_service.list_active_products_for_quote()
        return templates.TemplateResponse(
            request=request,
            name="crm.html",
            context={
                "active_page": "crm",
                "active_tab": "contacts",
                "summary": summary,
                "kanban": kanban,
                "contacts": contacts,
                "products": products,
                "success_message": f"成功建立客戶：{company_name}",
            },
        )

    return RedirectResponse(url="/crm?tab=contacts", status_code=303)


@router.post("/deals", response_class=HTMLResponse)
async def create_deal_endpoint(
    request: Request,
    contact_id: str = Form(...),
    title: str = Form(...),
    expected_amount: str = Form("0"),
    stage: str = Form("LEAD"),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """新增商機。"""
    try:
        amt = Decimal(expected_amount) if expected_amount else Decimal("0.0")
        crm_service.create_deal(
            contact_id=contact_id,
            title=title,
            expected_amount=amt,
            stage=DealStage(stage),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        return templates.TemplateResponse(
            request=request,
            name="crm.html",
            context={
                "active_page": "crm",
                "active_tab": "kanban",
                "summary": summary,
                "kanban": kanban,
                "contacts": contacts,
                "products": products,
                "success_message": f"成功建立商機：{title}",
            },
        )

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)


@router.post("/deals/{deal_id}/stage", response_class=HTMLResponse)
async def advance_deal_stage_endpoint(
    deal_id: str,
    request: Request,
    stage: str = Form(...),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """推進或變更商機階段。"""
    try:
        new_stage = DealStage(stage)
        crm_service.advance_deal_stage(deal_id=deal_id, new_stage=new_stage)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        return templates.TemplateResponse(
            request=request,
            name="crm.html",
            context={
                "active_page": "crm",
                "active_tab": "kanban",
                "summary": summary,
                "kanban": kanban,
                "contacts": contacts,
                "products": products,
                "success_message": f"商機 {deal_id} 已變更階段為 {new_stage.value}",
            },
        )

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)


@router.post("/deals/{deal_id}/quotes", response_class=HTMLResponse)
async def create_quote_endpoint(
    deal_id: str,
    request: Request,
    sku_1: str = Form(...),
    qty_1: str = Form("1"),
    price_1: str = Form("0"),
    sku_2: Optional[str] = Form(None),
    qty_2: Optional[str] = Form(None),
    price_2: Optional[str] = Form(None),
    valid_days: int = Form(30),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """為商機建立報價單，自動推進至 PROPOSAL 方案報價階段。"""
    try:
        items: List[Tuple[str, Decimal, Decimal]] = [
            (sku_1, Decimal(qty_1), Decimal(price_1))
        ]
        if sku_2 and qty_2 and price_2:
            if sku_2.strip() and Decimal(qty_2) > Decimal("0.0"):
                items.append((sku_2.strip(), Decimal(qty_2), Decimal(price_2)))

        quote = crm_service.create_quote(
            deal_id=deal_id,
            items=items,
            valid_days=valid_days,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        return templates.TemplateResponse(
            request=request,
            name="crm.html",
            context={
                "active_page": "crm",
                "active_tab": "kanban",
                "summary": summary,
                "kanban": kanban,
                "contacts": contacts,
                "products": products,
                "success_message": f"成功建立報價單 {quote.quote_number}，金額 NT$ {quote.total_amount:,.2f}",
            },
        )

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)


@router.get("/quotes/{quote_id}/docx")
async def download_quote_docx_endpoint(
    quote_id: str,
    crm_service: CrmService = Depends(get_crm_service),
):
    """串流下載 Word (.docx) 商業報價單。"""
    try:
        docx_bytes = crm_service.generate_quote_docx(quote_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="quotation_{quote_id}.docx"',
        },
    )


@router.get("/quotes/{quote_id}/pdf")
async def view_quote_pdf_endpoint(
    quote_id: str,
    crm_service: CrmService = Depends(get_crm_service),
):
    """瀏覽器原生預覽與下載 A4 報價單 PDF。"""
    try:
        pdf_bytes = crm_service.generate_quote_pdf(quote_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="quotation_{quote_id}.pdf"',
        },
    )


@router.post("/deals/{deal_id}/convert-to-order", response_class=HTMLResponse)
async def convert_deal_endpoint(
    deal_id: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """贏單 (WON) 一鍵穿透拋轉為 ERP 銷售訂單 (SO)。"""
    try:
        so, won_deal = crm_service.convert_deal_to_erp_order(deal_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        return templates.TemplateResponse(
            request=request,
            name="crm.html",
            context={
                "active_page": "crm",
                "active_tab": "kanban",
                "summary": summary,
                "kanban": kanban,
                "contacts": contacts,
                "products": products,
                "success_message": f"商機已成功拋轉為 ERP 銷售訂單 {so.order_id} (NT$ {so.total_amount:,.2f})！",
            },
        )

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)
