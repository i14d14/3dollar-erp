from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

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
        accounting_service.create_journal_entry(
            entry_date=parsed_date,
            source_event="MANUAL",
            reference_id="MANUAL",
            description=description.strip(),
            lines=parsed_lines,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        status_code=200,
        headers={"HX-Redirect": "/accounting?tab=journal"},
    )


@router.post("/ar/{ar_id}/settle")
async def settle_ar(
    request: Request,
    ar_id: str,
    amount: Optional[str] = Form(None),
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
        accounting_service.settle_receivable(ar_id=ar_id, amount=settle_amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return Response(
        status_code=200,
        headers={"HX-Redirect": "/accounting?tab=aging"},
    )


@router.post("/ap/{ap_id}/settle")
async def settle_ap(
    request: Request,
    ap_id: str,
    amount: Optional[str] = Form(None),
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
        accounting_service.settle_payable(ap_id=ap_id, amount=settle_amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
