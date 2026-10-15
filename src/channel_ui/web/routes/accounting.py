from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

from src.channel_ui.web.toast_helper import render_toast_oob
from src.extended_core.accounting.reports.excel_exporter import (
    export_income_statement_xlsx,
    export_trial_balance_xlsx,
)

router = APIRouter(prefix="/accounting", tags=["accounting"])


@router.get("", response_class=HTMLResponse)
async def accounting_page(
    request: Request,
    tab: str = "trial_balance",
):
    templates = request.app.state.templates
    view_service = request.app.state.view_service

    kpis = view_service.get_accounting_kpis()
    trial_balance = view_service.get_trial_balance_view()
    income_statement = view_service.get_income_statement_view()
    ar_aging = view_service.get_aging_view("RECEIVABLE")
    ap_aging = view_service.get_aging_view("PAYABLE")
    journal_entries = view_service.get_journal_entries_view(limit=50)
    accounts = view_service.get_active_accounts()

    return templates.TemplateResponse(
        request=request,
        name="accounting.html",
        context={
            "active_page": "accounting",
            "active_tab": tab,
            "kpis": kpis,
            "trial_balance": trial_balance,
            "income_statement": income_statement,
            "ar_aging": ar_aging,
            "ap_aging": ap_aging,
            "journal_entries": journal_entries,
            "accounts": accounts,
        },
    )


@router.post("/journal-entries")
async def create_manual_journal_entry(
    request: Request,
    entry_date: str = Form(...),
    description: str = Form(...),
    account_code_1: str = Form(...),
    debit_1: str = Form("0"),
    credit_1: str = Form("0"),
    account_code_2: str = Form(...),
    debit_2: str = Form("0"),
    credit_2: str = Form("0"),
    account_code_3: Optional[str] = Form(None),
    debit_3: str = Form("0"),
    credit_3: str = Form("0"),
):
    view_service = request.app.state.view_service
    accounting_service = view_service.accounting_service

    try:
        parsed_date = datetime.date.fromisoformat(entry_date)
    except Exception:
        raise HTTPException(status_code=400, detail="無效的傳票日期格式 (YYYY-MM-DD)")

    raw_lines = [
        (account_code_1, debit_1, credit_1),
        (account_code_2, debit_2, credit_2),
    ]
    if account_code_3 and account_code_3.strip():
        raw_lines.append((account_code_3, debit_3, credit_3))

    parsed_lines = []
    for code, dr_str, cr_str in raw_lines:
        try:
            dr = Decimal(dr_str.strip() or "0")
            cr = Decimal(cr_str.strip() or "0")
        except Exception:
            raise HTTPException(status_code=400, detail=f"科目 {code} 金額格式不正確")

        if dr > 0 or cr > 0:
            parsed_lines.append((code.strip(), dr, cr))

    if not parsed_lines:
        raise HTTPException(status_code=400, detail="傳票必須至少包含一筆借貸分錄")

    try:
        entry = accounting_service.create_journal_entry(
            entry_date=parsed_date,
            source_event="MANUAL",
            reference_id="MANUAL",
            description=description.strip(),
            lines=parsed_lines,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    entry_total = sum(l.debit for l in entry.lines)

    if request.headers.get("HX-Request") == "true":
        templates = request.app.state.templates
        kpis = view_service.get_accounting_kpis()
        trial_balance = view_service.get_trial_balance_view()
        income_statement = view_service.get_income_statement_view()
        ar_aging = view_service.get_aging_view("RECEIVABLE")
        ap_aging = view_service.get_aging_view("PAYABLE")
        journal_entries = view_service.get_journal_entries_view(limit=50)
        accounts = view_service.get_active_accounts()

        page_html = templates.get_template("accounting.html").render({
            "request": request,
            "active_page": "accounting",
            "active_tab": "journal",
            "kpis": kpis,
            "trial_balance": trial_balance,
            "income_statement": income_statement,
            "ar_aging": ar_aging,
            "ap_aging": ap_aging,
            "journal_entries": journal_entries,
            "accounts": accounts,
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"手動傳票建立成功！傳票編號：{entry.entry_id}，借貸各 NT$ {entry_total:,.2f}",
            type="success",
            undo_url=f"/accounting/journal-entries/{entry.entry_id}/undo",
            undo_label="撤回傳票",
            undo_target="#accounting-container",
            undo_select="#accounting-container",
            undo_swap="outerHTML",
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return Response(
        status_code=200,
        headers={"HX-Redirect": "/accounting?tab=journal"},
    )


@router.post("/journal-entries/{entry_id}/undo", response_class=HTMLResponse)
async def undo_manual_journal_entry(
    request: Request,
    entry_id: str,
):
    """紅字反向沖銷手動傳票，還原試算表借貸平衡。"""
    templates = request.app.state.templates
    view_service = request.app.state.view_service
    accounting_service = view_service.accounting_service

    try:
        rev_entry = accounting_service.reverse_journal_entry(entry_id=entry_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    kpis = view_service.get_accounting_kpis()
    trial_balance = view_service.get_trial_balance_view()
    income_statement = view_service.get_income_statement_view()
    ar_aging = view_service.get_aging_view("RECEIVABLE")
    ap_aging = view_service.get_aging_view("PAYABLE")
    journal_entries = view_service.get_journal_entries_view(limit=50)
    accounts = view_service.get_active_accounts()

    page_html = templates.get_template("accounting.html").render({
        "request": request,
        "active_page": "accounting",
        "active_tab": "journal",
        "kpis": kpis,
        "trial_balance": trial_balance,
        "income_statement": income_statement,
        "ar_aging": ar_aging,
        "ap_aging": ap_aging,
        "journal_entries": journal_entries,
        "accounts": accounts,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回傳票 ({entry_id})，已立案紅字反向沖銷傳票 ({rev_entry.entry_id})，借貸總額已平衡歸零。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")



@router.get("/ar/{ar_id}/settle-modal", response_class=HTMLResponse)
async def get_ar_settle_modal(request: Request, ar_id: str):
    """取得應收帳款沖銷收款 Tailwind 二階確認彈窗。"""
    templates = request.app.state.templates
    db = request.app.state.db
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT ar.ar_id, ar.order_id, ar.customer_id, ar.amount, ar.paid_amount,
                   COALESCE(c.company_name, ar.customer_id) AS partner_name
            FROM accounts_receivable ar
            LEFT JOIN crm_contacts c ON ar.customer_id = c.contact_id
            WHERE ar.ar_id = ?
            """,
            (ar_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="查無應收帳款單據")

    total_amount = float(row["amount"])
    paid_amount = float(row["paid_amount"])
    outstanding = total_amount - paid_amount

    item = {
        "item_id": row["ar_id"],
        "reference_id": row["order_id"],
        "partner_name": row["partner_name"],
        "partner_id": row["customer_id"],
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding,
    }
    return templates.TemplateResponse(
        request=request,
        name="partials/settle_confirm_modal.html",
        context={"settle_type": "AR", "item": item},
    )


@router.get("/ap/{ap_id}/settle-modal", response_class=HTMLResponse)
async def get_ap_settle_modal(request: Request, ap_id: str):
    """取得應付帳款沖銷付款 Tailwind 二階確認彈窗。"""
    templates = request.app.state.templates
    db = request.app.state.db
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT ap_id, po_id, supplier_name, amount, paid_amount
            FROM accounts_payable
            WHERE ap_id = ?
            """,
            (ap_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="查無應付帳款單據")

    total_amount = float(row["amount"])
    paid_amount = float(row["paid_amount"])
    outstanding = total_amount - paid_amount

    item = {
        "item_id": row["ap_id"],
        "reference_id": row["po_id"],
        "partner_name": row["supplier_name"],
        "partner_id": "",
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "outstanding_amount": outstanding,
    }
    return templates.TemplateResponse(
        request=request,
        name="partials/settle_confirm_modal.html",
        context={"settle_type": "AP", "item": item},
    )


@router.post("/ar/{ar_id}/settle")
async def settle_ar(
    request: Request,
    ar_id: str,
    amount: Optional[str] = Form(None),
    payment_account: str = Form("1101"),
):
    view_service = request.app.state.view_service
    accounting_service = view_service.accounting_service

    settle_amount = None
    if amount and amount.strip():
        try:
            settle_amount = Decimal(amount.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="沖銷金額無效")

    db = request.app.state.db
    customer_name = None
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT c.company_name
            FROM accounts_receivable ar
            LEFT JOIN crm_contacts c ON ar.customer_id = c.contact_id
            WHERE ar.ar_id = ?
            """,
            (ar_id,),
        ).fetchone()
        if row and row["company_name"]:
            customer_name = row["company_name"]

    try:
        entry = accounting_service.settle_receivable(
            ar_id=ar_id,
            amount=settle_amount,
            payment_account=payment_account,
            customer_name=customer_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        templates = request.app.state.templates
        kpis = view_service.get_accounting_kpis()
        trial_balance = view_service.get_trial_balance_view()
        income_statement = view_service.get_income_statement_view()
        ar_aging = view_service.get_aging_view("RECEIVABLE")
        ap_aging = view_service.get_aging_view("PAYABLE")
        journal_entries = view_service.get_journal_entries_view(limit=50)
        accounts = view_service.get_active_accounts()

        page_html = templates.get_template("accounting.html").render({
            "request": request,
            "active_page": "accounting",
            "active_tab": "aging",
            "kpis": kpis,
            "trial_balance": trial_balance,
            "income_statement": income_statement,
            "ar_aging": ar_aging,
            "ap_aging": ap_aging,
            "journal_entries": journal_entries,
            "accounts": accounts,
        })
        entry_total = sum(l.debit for l in entry.lines)
        account_label = "1101 現金" if payment_account == "1101" else "1102 銀行存款"
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"已成功沖銷結清應收帳款 ({ar_id})！拋轉傳票：{entry.entry_id}，沖銷金額：NT$ {entry_total:,.2f} ({account_label})",
            type="success",
            undo_url=None,
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return Response(
        status_code=200,
        headers={"HX-Redirect": "/accounting?tab=aging"},
    )


@router.post("/ap/{ap_id}/settle")
async def settle_ap(
    request: Request,
    ap_id: str,
    amount: Optional[str] = Form(None),
    payment_account: str = Form("1101"),
):
    view_service = request.app.state.view_service
    accounting_service = view_service.accounting_service

    settle_amount = None
    if amount and amount.strip():
        try:
            settle_amount = Decimal(amount.strip())
        except Exception:
            raise HTTPException(status_code=400, detail="沖銷金額無效")

    try:
        entry = accounting_service.settle_payable(
            ap_id=ap_id,
            amount=settle_amount,
            payment_account=payment_account,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        templates = request.app.state.templates
        kpis = view_service.get_accounting_kpis()
        trial_balance = view_service.get_trial_balance_view()
        income_statement = view_service.get_income_statement_view()
        ar_aging = view_service.get_aging_view("RECEIVABLE")
        ap_aging = view_service.get_aging_view("PAYABLE")
        journal_entries = view_service.get_journal_entries_view(limit=50)
        accounts = view_service.get_active_accounts()

        page_html = templates.get_template("accounting.html").render({
            "request": request,
            "active_page": "accounting",
            "active_tab": "aging",
            "kpis": kpis,
            "trial_balance": trial_balance,
            "income_statement": income_statement,
            "ar_aging": ar_aging,
            "ap_aging": ap_aging,
            "journal_entries": journal_entries,
            "accounts": accounts,
        })
        entry_total = sum(l.credit for l in entry.lines)
        account_label = "1101 現金" if payment_account == "1101" else "1102 銀行存款"
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"已成功沖銷支付應付帳款 ({ap_id})！拋轉傳票：{entry.entry_id}，支付金額：NT$ {entry_total:,.2f} ({account_label})",
            type="success",
            undo_url=None,
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return Response(
        status_code=200,
        headers={"HX-Redirect": "/accounting?tab=aging"},
    )


@router.get("/export/trial-balance.xlsx")
async def export_trial_balance(request: Request):
    view_service = request.app.state.view_service
    tb = view_service.accounting_service.get_trial_balance()
    xlsx_data = export_trial_balance_xlsx(tb)

    return Response(
        content=xlsx_data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=trial_balance_{datetime.date.today().isoformat()}.xlsx"},
    )


@router.get("/export/income-statement.xlsx")
async def export_income_statement(request: Request):
    view_service = request.app.state.view_service
    stmt = view_service.accounting_service.get_income_statement()
    xlsx_data = export_income_statement_xlsx(stmt)

    return Response(
        content=xlsx_data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=income_statement_{datetime.date.today().isoformat()}.xlsx"},
    )


@router.get("/reports/executive-financial")
async def download_accounting_executive_financial_report(request: Request):
    """串流下載 4合1 全方位財務與營運整合報表 (.xlsx)。"""
    import io
    from fastapi.responses import StreamingResponse
    from src.extended_core.accounting.services.excel_report_generator import AdvancedReportGenerator
    from src.shared.database import Database, default_db

    db: Database = getattr(request.app.state, "db", default_db)
    generator = AdvancedReportGenerator(db=db)
    content = generator.generate_comprehensive_financial_report()

    today_str = datetime.date.today().strftime("%Y%m%d")
    filename = f"3dollar_financial_executive_{today_str}.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

