from __future__ import annotations
from decimal import Decimal
from typing import List, Optional, Tuple
import urllib.parse

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import (
    get_crm_service,
    get_templates,
    get_view_service,
)
from src.channel_ui.web.toast_helper import render_toast_oob
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
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "contacts",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"成功建立客戶：{company_name}",
            type="success",
            undo_url=None,
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return RedirectResponse(url="/crm?tab=contacts", status_code=303)


@router.post("/contacts/{contact_id}", response_class=HTMLResponse)
async def update_contact_endpoint(
    contact_id: str,
    request: Request,
    contact_name: str = Form(...),
    tax_id: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """更新客戶主檔資料（嚴格禁止變更公司名稱）。"""
    try:
        updated = crm_service.update_contact(
            contact_id=contact_id,
            company_name=None,  # 嚴格禁止修改客戶公司名稱
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
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "contacts",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"成功更新客戶資料：{updated.company_name}",
            type="success",
            undo_url=None,
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return RedirectResponse(url="/crm?tab=contacts", status_code=303)


@router.post("/deals", response_class=HTMLResponse)
async def create_deal_endpoint(
    request: Request,
    contact_id: str = Form(...),
    title: str = Form(...),
    stage: str = Form("LEAD"),
    sku_1: Optional[str] = Form(None),
    qty_1: Optional[str] = Form("1"),
    price_1: Optional[str] = Form("0"),
    sku_2: Optional[str] = Form(None),
    qty_2: Optional[str] = Form("0"),
    price_2: Optional[str] = Form("0"),
    expected_amount: Optional[str] = Form(None),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """新增商機，支援物料品項與數量計價建檔。"""
    try:
        items: List[Tuple[str, Decimal, Decimal]] = []
        if sku_1 and sku_1.strip():
            items.append((sku_1.strip(), Decimal(qty_1 or "1"), Decimal(price_1 or "0")))
        if sku_2 and sku_2.strip() and Decimal(qty_2 or "0") > Decimal("0.0"):
            items.append((sku_2.strip(), Decimal(qty_2 or "0"), Decimal(price_2 or "0")))

        amt = Decimal(expected_amount) if (expected_amount and not items) else Decimal("0.0")
        deal = crm_service.create_deal(
            contact_id=contact_id,
            title=title,
            expected_amount=amt,
            stage=DealStage(stage),
            items=items if items else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "kanban",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"成功建立商機：{deal.title}（預估金額：NT$ {deal.expected_amount:,.2f}）",
            type="success",
            undo_url=f"/crm/deals/{deal.deal_id}/undo",
            undo_label="撤回建立",
            undo_target="#crm-container",
            undo_select="#crm-container",
            undo_swap="outerHTML",
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    msg_encoded = urllib.parse.quote(f"成功建立商機：{title}")
    return RedirectResponse(url=f"/crm?tab=kanban&msg={msg_encoded}", status_code=303)


@router.post("/deals/{deal_id}/undo", response_class=HTMLResponse)
async def undo_create_deal_endpoint(
    deal_id: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """撤回/刪除草稿商機。"""
    try:
        crm_service.delete_draft_deal(deal_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    summary = view_service.get_crm_summary()
    kanban = view_service.get_crm_kanban()
    contacts = view_service.list_contacts_with_stats()
    products = view_service.list_active_products_for_quote()

    page_html = templates.get_template("crm.html").render({
        "request": request,
        "active_page": "crm",
        "active_tab": "kanban",
        "summary": summary,
        "kanban": kanban,
        "contacts": contacts,
        "products": products,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回商機建立 ({deal_id})。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")



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
    deal = crm_service.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"查無商機 {deal_id}")
    old_stage = deal.stage.value

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
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "kanban",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"商機 {deal_id} 已變更階段為 {new_stage.value}",
            type="success",
            undo_url=f"/crm/deals/{deal_id}/stage/undo",
            undo_label="撤回階段",
            undo_target="#crm-container",
            undo_select="#crm-container",
            undo_swap="outerHTML",
            undo_vals={"prev_stage": old_stage},
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)


@router.post("/deals/{deal_id}/stage/undo", response_class=HTMLResponse)
async def undo_advance_deal_stage_endpoint(
    deal_id: str,
    request: Request,
    prev_stage: Optional[str] = Form(None),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """撤回商機階段變更，回退至前一階段。"""
    deal = crm_service.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"查無商機 {deal_id}")

    target_stage: Optional[DealStage] = None
    if prev_stage:
        try:
            target_stage = DealStage(prev_stage)
        except ValueError:
            target_stage = None

    if not target_stage:
        predecessors = {
            DealStage.WON: DealStage.PROPOSAL,
            DealStage.LOST: DealStage.PROPOSAL,
            DealStage.PROPOSAL: DealStage.DISCOVERY,
            DealStage.DISCOVERY: DealStage.LEAD,
            DealStage.LEAD: DealStage.LEAD,
        }
        target_stage = predecessors.get(deal.stage, DealStage.LEAD)

    try:
        crm_service.advance_deal_stage(deal_id=deal_id, new_stage=target_stage)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    summary = view_service.get_crm_summary()
    kanban = view_service.get_crm_kanban()
    contacts = view_service.list_contacts_with_stats()
    products = view_service.list_active_products_for_quote()

    page_html = templates.get_template("crm.html").render({
        "request": request,
        "active_page": "crm",
        "active_tab": "kanban",
        "summary": summary,
        "kanban": kanban,
        "contacts": contacts,
        "products": products,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回商機 {deal_id} 階段變更，已回復為 {target_stage.value}。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")


@router.post("/deals/{deal_id}/quotes", response_class=HTMLResponse)
async def create_quote_endpoint(
    deal_id: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """為商機建立報價單，支援動態多品項物料，並自動推進至 PROPOSAL 方案報價階段。"""
    form_data = await request.form()
    items: List[Tuple[str, Decimal, Decimal]] = []

    # Dynamic multi-item parsing
    skus = form_data.getlist("sku")
    qtys = form_data.getlist("qty")
    prices = form_data.getlist("price")

    if skus and qtys and prices:
        for s, q, p in zip(skus, qtys, prices):
            s_val = str(s).strip()
            if not s_val:
                continue
            try:
                q_val = Decimal(str(q))
                p_val = Decimal(str(p))
            except Exception:
                raise HTTPException(status_code=400, detail=f"物料 {s_val} 之數量或單價格式錯誤")
            if q_val <= Decimal("0.0"):
                raise HTTPException(status_code=400, detail=f"物料 {s_val} 之報價數量必須大於 0")
            if p_val < Decimal("0.0"):
                raise HTTPException(status_code=400, detail=f"物料 {s_val} 之報價單價不得為負數")
            items.append((s_val, q_val, p_val))

    # Backward-compatible fallback for legacy forms (sku_1, sku_2)
    if not items:
        sku_1 = str(form_data.get("sku_1", "")).strip()
        qty_1 = str(form_data.get("qty_1", "1")).strip()
        price_1 = str(form_data.get("price_1", "0")).strip()
        if sku_1:
            try:
                items.append((sku_1, Decimal(qty_1 or "1"), Decimal(price_1 or "0")))
            except Exception:
                raise HTTPException(status_code=400, detail="項次 1 格式錯誤")

        sku_2 = str(form_data.get("sku_2", "")).strip()
        qty_2 = str(form_data.get("qty_2", "0")).strip()
        price_2 = str(form_data.get("price_2", "0")).strip()
        if sku_2 and qty_2 and price_2:
            try:
                if Decimal(qty_2) > Decimal("0.0"):
                    items.append((sku_2, Decimal(qty_2), Decimal(price_2)))
            except Exception:
                pass

    if not items:
        raise HTTPException(status_code=400, detail="報價單必須包含至少一項有效商品")

    try:
        valid_days = int(form_data.get("valid_days", 30))
    except Exception:
        valid_days = 30

    try:
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
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "kanban",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"成功建立報價單 {quote.quote_number}，金額 NT$ {quote.total_amount:,.2f}",
            type="success",
            undo_url=f"/crm/quotes/{quote.quote_id}/undo",
            undo_label="撤回報價單",
            undo_target="#crm-container",
            undo_select="#crm-container",
            undo_swap="outerHTML show:none",
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return RedirectResponse(url="/crm?tab=kanban", status_code=303)


@router.post("/quotes/{quote_id}/undo", response_class=HTMLResponse)
async def undo_create_quote_endpoint(
    quote_id: str,
    request: Request,
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """撤回/刪除草稿報價單。"""
    try:
        crm_service.delete_quote(quote_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    summary = view_service.get_crm_summary()
    kanban = view_service.get_crm_kanban()
    contacts = view_service.list_contacts_with_stats()
    products = view_service.list_active_products_for_quote()

    page_html = templates.get_template("crm.html").render({
        "request": request,
        "active_page": "crm",
        "active_tab": "kanban",
        "summary": summary,
        "kanban": kanban,
        "contacts": contacts,
        "products": products,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回報價單 ({quote_id})，商機狀態已復原。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")



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


@router.get("/deals/{deal_id}/convert-modal", response_class=HTMLResponse)
async def get_convert_deal_modal_endpoint(
    deal_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    crm_service: CrmService = Depends(get_crm_service),
    view_service: WebViewService = Depends(get_view_service),
):
    """渲染贏單轉 ERP 訂單之確認對話框。"""
    deal = crm_service.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"查無商機 {deal_id}")

    contact = crm_service.get_contact(deal.contact_id)
    company_name = contact.company_name if contact else deal.contact_id

    # 優先繼承最新有效報價單之物料明細，無報價單時 fallback 至商機自帶明細
    quotes = crm_service.get_quotes_for_deal(deal_id)
    target_quote = quotes[0] if quotes else None

    deal_items = target_quote.items if (target_quote and target_quote.items) else deal.items
    total_amount = target_quote.total_amount if target_quote else (
        deal.expected_amount if deal.expected_amount > Decimal("0.0") else sum((it.subtotal for it in deal_items), Decimal("0.0"))
    )
    warehouses = view_service.list_warehouses_for_select()

    return templates.TemplateResponse(
        request=request,
        name="partials/convert_deal_modal.html",
        context={
            "deal": deal,
            "quote": target_quote,
            "deal_items": deal_items,
            "total_amount": total_amount,
            "company_name": company_name,
            "warehouses": warehouses,
        },
    )


@router.post("/deals/{deal_id}/convert-to-order", response_class=HTMLResponse)
async def convert_deal_endpoint(
    deal_id: str,
    request: Request,
    warehouse_id: str = Form("WH-MAIN"),
    crm_service: CrmService = Depends(get_crm_service),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """贏單 (WON) 一鍵穿透拋轉為 ERP 銷售訂單 (SO)。"""
    try:
        so, won_deal = crm_service.convert_deal_to_erp_order(
            deal_id=deal_id,
            warehouse_id=warehouse_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        summary = view_service.get_crm_summary()
        kanban = view_service.get_crm_kanban()
        contacts = view_service.list_contacts_with_stats()
        products = view_service.list_active_products_for_quote()
        page_html = templates.get_template("crm.html").render({
            "request": request,
            "active_page": "crm",
            "active_tab": "kanban",
            "summary": summary,
            "kanban": kanban,
            "contacts": contacts,
            "products": products,
        })
        modal_close_html = '<div id="modal-container" hx-swap-oob="innerHTML:#modal-container"></div>'
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"商機已成功拋轉為 ERP 銷售訂單 {so.order_id} (NT$ {so.total_amount:,.2f})！",
            type="success",
            undo_url=None,
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{modal_close_html}\n{toast_html}")

    msg_encoded = urllib.parse.quote(f"商機已成功拋轉為 ERP 銷售訂單 {so.order_id} (NT$ {so.total_amount:,.2f})！")
    return RedirectResponse(url=f"/crm?tab=kanban&msg={msg_encoded}", status_code=303)

