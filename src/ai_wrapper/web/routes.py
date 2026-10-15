from __future__ import annotations
import datetime
import io
import urllib.parse
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

from src.ai_wrapper.bom.parser import BomExcelParser
from src.ai_wrapper.bom.service import BomComparisonService
from src.ai_wrapper.invoice.models import ExtractedTaiwanInvoice
from src.ai_wrapper.invoice.parser import TaiwanPdfInvoiceParser
from src.ai_wrapper.invoice.service import InvoiceIntakeService
from src.ai_wrapper.reporting.excel_generator import AdvancedReportGenerator
from src.shared.database import Database, default_db
import fitz

router = APIRouter(prefix="/ai", tags=["AI & File Automation"])


@router.get("/tools", response_class=HTMLResponse)
async def ai_tools_page(request: Request):
    """Render the AI & File Automation workbench."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="ai_tools.html",
        context={
            "active_page": "ai_tools",
            "page_title": "檔案自動化中心",
        },
    )


# --- 1. BOM Comparison Endpoints ---

@router.get("/bom/sample")
async def download_bom_sample(request: Request):
    """Download a realistic sample BOM Excel file for immediate testing."""
    db: Database = getattr(request.app.state, "db", default_db)
    generator = AdvancedReportGenerator(db=db)
    content = generator.generate_sample_bom_excel()

    filename = "sample_bom_template.xlsx"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/bom/compare", response_class=HTMLResponse)
async def compare_bom_file(request: Request, file: UploadFile = File(...)):
    """Upload BOM Excel file, parse items, compare historical quotes, and render HTMX result."""
    templates = request.app.state.templates
    db: Database = getattr(request.app.state, "db", default_db)

    if not file.filename.endswith((".xlsx", ".xlsm")):
        return HTMLResponse(
            """
            <div class="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm">
              <span class="font-bold">⚠️ 檔案格式錯誤：</span>僅支援 Excel (.xlsx, .xlsm) 格式檔案，請重新選擇。
            </div>
            """
        )

    file_bytes = await file.read()
    parser = BomExcelParser()
    parse_result = parser.parse(file_bytes)

    if parse_result.errors and not parse_result.items:
        err_list = "".join(f"<li>{e}</li>" for e in parse_result.errors)
        return HTMLResponse(
            f"""
            <div class="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm">
              <div class="font-bold mb-1">⚠️ BOM 表解析失敗：</div>
              <ul class="list-disc pl-5 space-y-1">{err_list}</ul>
            </div>
            """
        )

    comparison_service = BomComparisonService(db=db)
    summary = comparison_service.compare_bom(parse_result)

    # Save summary in app state or session if needed for export, or render directly
    return templates.TemplateResponse(
        request=request,
        name="partials/ai_bom_result.html",
        context={
            "summary": summary,
            "filename": file.filename,
            "warnings": parse_result.errors,
        },
    )


# --- 2. Taiwan Electronic Invoice PDF Extraction Endpoints ---

@router.get("/invoice/sample-pdf")
async def download_invoice_sample_pdf():
    """Generate and download a standard Taiwan electronic invoice PDF for testing."""
    doc = fitz.open()
    page = doc.new_page(width=161.57, height=420)  # 5.7cm wide

    page.insert_text(fitz.Point(12, 25), "祥茂電子精密工業股份有限公司", fontsize=8, fontname="china-t")
    page.insert_text(fitz.Point(12, 42), "電子發票證明聯", fontsize=10, fontname="china-t")
    page.insert_text(fitz.Point(12, 56), "(MIG 3.2.1 B2B)", fontsize=8, fontname="helv")

    now = datetime.datetime.now()
    roc_year = now.year - 1911
    period_str = f"{roc_year:03d}年09-10月"
    page.insert_text(fitz.Point(12, 72), period_str, fontsize=9, fontname="china-t")
    page.insert_text(fitz.Point(12, 88), "AB-98765432", fontsize=11, fontname="helv")

    page.draw_line(fitz.Point(10, 96), fitz.Point(150, 96), color=(0, 0, 0), width=0.8)

    page.insert_text(fitz.Point(12, 110), f"開立日期: {now.strftime('%Y-%m-%d')}", fontsize=6.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 122), "隨機碼: 6852", fontsize=7.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 136), "總計: NT$ 14,700", fontsize=7.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 150), "賣方: 88888888", fontsize=7.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 164), "買方: 12345678", fontsize=7.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 178), "未稅金額: NT$ 14,000", fontsize=7, fontname="china-t")
    page.insert_text(fitz.Point(12, 190), "營業稅: NT$ 700", fontsize=7, fontname="china-t")

    page.draw_line(fitz.Point(10, 198), fitz.Point(150, 198), color=(0, 0, 0), width=0.5)
    page.insert_text(fitz.Point(12, 212), "品名: 智慧旗艦終端機零件", fontsize=7, fontname="china-t")
    page.insert_text(fitz.Point(12, 224), "數量: 10    單價: 1,400", fontsize=6.5, fontname="china-t")
    page.insert_text(fitz.Point(12, 236), "小計: NT$ 14,000", fontsize=6.5, fontname="china-t")

    pdf_bytes = doc.write()
    doc.close()

    filename = "sample_taiwan_e_invoice.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/invoice/extract", response_class=HTMLResponse)
async def extract_invoice_pdf(request: Request, file: UploadFile = File(...)):
    """Upload Taiwan e-invoice PDF, extract text layer without OCR, and render preview."""
    templates = request.app.state.templates
    db: Database = getattr(request.app.state, "db", default_db)

    if not file.filename.lower().endswith(".pdf"):
        return HTMLResponse(
            """
            <div class="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-sm">
              <span class="font-bold">⚠️ 檔案格式錯誤：</span>僅支援 PDF 格式發票檔案，請重新上傳。
            </div>
            """
        )

    file_bytes = await file.read()
    parser = TaiwanPdfInvoiceParser()
    extracted = parser.parse(file_bytes)

    intake_service = InvoiceIntakeService(db=db)
    match_result = intake_service.match_invoice(extracted)

    return templates.TemplateResponse(
        request=request,
        name="partials/ai_invoice_result.html",
        context={
            "result": match_result,
            "filename": file.filename,
        },
    )


@router.post("/invoice/confirm-ap", response_class=HTMLResponse)
async def confirm_invoice_ap(
    request: Request,
    invoice_number: str = Form(...),
    seller_name: str = Form(...),
    seller_tax_id: Optional[str] = Form(None),
    total_amount: str = Form(...),
    sales_amount: str = Form(...),
    tax_amount: str = Form(...),
    po_id: Optional[str] = Form(None),
):
    """Confirm extracted invoice and create Accounts Payable (AP) and Journal Entry."""
    db: Database = getattr(request.app.state, "db", default_db)
    tot_dec = Decimal(total_amount.replace(",", ""))
    sales_dec = Decimal(sales_amount.replace(",", "")) if sales_amount else tot_dec
    tax_dec = Decimal(tax_amount.replace(",", "")) if tax_amount else Decimal("0.0")

    extracted = ExtractedTaiwanInvoice(
        invoice_number=invoice_number,
        seller_name=seller_name,
        seller_tax_id=seller_tax_id,
        sales_amount=sales_dec,
        tax_amount=tax_dec,
        total_amount=tot_dec,
    )

    intake_service = InvoiceIntakeService(db=db)
    try:
        ap_id = intake_service.create_ap_from_invoice(
            invoice=extracted,
            po_id=po_id if po_id and po_id.strip() else None,
            supplier_name=seller_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return HTMLResponse(
        f"""
        <div class="p-5 bg-emerald-50 border border-emerald-300 rounded-2xl shadow-sm text-emerald-900">
          <div class="flex items-center gap-3 mb-2">
            <span class="text-2xl">✅</span>
            <div>
              <div class="font-bold text-base">應付帳款與會計分錄建立成功！</div>
              <div class="text-xs text-emerald-700">單據編號: <span class="font-mono font-bold">{ap_id}</span> | 發票號碼: <span class="font-mono">{invoice_number}</span></div>
            </div>
          </div>
          <p class="text-xs text-emerald-800 mt-2 leading-relaxed">
            系統已自動在探吉會計完成借貸分錄認列（借：1201 存貨 ${tot_dec:,.0f} / 貸：2144 應付帳款 ${tot_dec:,.0f}），您可隨時至「探吉 會計記帳」查閱帳齡與執行款項沖銷。
          </p>
          <div class="mt-4 flex gap-3">
            <a href="/accounting" class="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition">
              前往探吉會計查閱 ➔
            </a>
            <button onclick="location.reload()" class="px-3.5 py-1.5 bg-white border border-emerald-300 hover:bg-emerald-100 text-emerald-800 rounded-lg text-xs font-medium transition">
              繼續辨識下一張
            </button>
          </div>
        </div>
        """
    )


# --- 3. Executive Financial Workbook Streaming Export Endpoint ---

@router.get("/reports/executive-financial")
async def download_executive_financial_report(request: Request):
    """Stream multi-sheet executive financial and operations workbook in .xlsx format."""
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
