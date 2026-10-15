from __future__ import annotations
import io
import json
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from src.channel_ui.web.dependencies import (
    get_procurement_service,
    get_templates,
    get_view_service,
)
from src.channel_ui.web.toast_helper import render_toast_oob
from src.channel_ui.web.view_service import WebViewService
from src.core.services.bom_parser import BomExcelParser
from src.core.services.bom_service import BomComparisonService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.accounting.services.excel_report_generator import AdvancedReportGenerator
from src.shared.database import Database, default_db

router = APIRouter(prefix="/procurement")


@router.get("", response_class=HTMLResponse)
async def procurement_page(
    request: Request,
    sku: Optional[str] = None,
    warehouse_id: Optional[str] = None,
    qty: Optional[int] = None,
    supplier_name: Optional[str] = None,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """採購管理主頁面：展示開單卡片、物料選項、倉庫清單與即時採購單流水。"""
    pos = view_service.list_purchase_orders()
    products = view_service.list_active_products_for_po()
    warehouses = view_service.list_warehouses_for_select()

    prefill_unit_cost = ""
    if sku:
        matched = next((p for p in products if p.get("sku") == sku), None)
        if matched and matched.get("cost_price") is not None:
            prefill_unit_cost = f"{Decimal(str(matched['cost_price'])):.2f}"

    return templates.TemplateResponse(
        request=request,
        name="procurement.html",
        context={
            "active_page": "procurement",
            "pos": pos,
            "products": products,
            "warehouses": warehouses,
            "prefill_sku": sku or "",
            "prefill_warehouse_id": warehouse_id or "WH-MAIN",
            "prefill_qty": qty or 20,
            "prefill_supplier_name": supplier_name or "",
            "prefill_unit_cost": prefill_unit_cost,
        },
    )


# --- BOM Comparison & One-Click Split POs Endpoints ---

@router.get("/bom/sample")
async def download_bom_sample_endpoint(request: Request):
    """下載採購用 BOM 比價範本 Excel 檔。"""
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
async def compare_bom_endpoint(request: Request, file: UploadFile = File(...)):
    """上傳 BOM Excel 檔，解析物料、比對供應商歷史採購單價，並呈現比價明細與一鍵下單按鈕。"""
    templates: Jinja2Templates = request.app.state.templates
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

    # Prepare items payload for one-click split PO generation
    split_items_json = []
    for item in summary.items:
        supp = item.effective_supplier or ""
        cost = float(item.effective_cost) if item.effective_cost is not None else 0.0
        split_items_json.append({
            "sku": item.sku,
            "name": item.name,
            "qty": float(item.qty),
            "unit_cost": cost,
            "supplier_name": supp,
            "is_orderable": item.is_orderable,
        })

    return templates.TemplateResponse(
        request=request,
        name="partials/procurement_bom_result.html",
        context={
            "summary": summary,
            "filename": file.filename,
            "warnings": parse_result.errors,
            "split_items_json_str": json.dumps(split_items_json, ensure_ascii=False),
        },
    )


@router.post("/bom/create-pos", response_class=HTMLResponse)
async def create_pos_from_bom_endpoint(
    request: Request,
    items_json: str = Form(...),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """一鍵依供應商公司分割生成多張採購訂單 (Group by Supplier -> Multi POs)。"""
    try:
        items_raw = json.loads(items_json)
    except Exception:
        raise HTTPException(status_code=400, detail="BOM 資料格式錯誤")

    if not items_raw:
        raise HTTPException(status_code=400, detail="BOM 查無可建立採購單之物料")

    # Rigid filter: must have a non-empty, valid supplier and positive cost & quantity
    valid_items = []
    skipped_items = []
    for it in items_raw:
        supp = str(it.get("supplier_name", "")).strip()
        s = str(it.get("sku", "")).strip().upper()
        n = str(it.get("name", "")).strip() or s
        try:
            q = Decimal(str(it.get("qty", "1")))
            c = Decimal(str(it.get("unit_cost", "0")))
        except Exception:
            q = Decimal("0")
            c = Decimal("0")

        if supp and supp != "未指定供應商" and c > Decimal("0") and q > Decimal("0"):
            valid_items.append({"sku": s, "name": n, "qty": q, "unit_cost": c, "supplier_name": supp})
        else:
            skipped_items.append(it)

    if not valid_items:
        raise HTTPException(
            status_code=400,
            detail="BOM 查無有效物料可建立採購單（所有品項均未指定供應商或單價為 0，請先補齊廠商與價格資料）",
        )

    db: Database = getattr(request.app.state, "db", default_db)
    # Ensure any new SKUs with valid cost from BOM exist in products catalog so PO creation succeeds
    with db.transaction() as conn:
        for it in valid_items:
            s_val = it["sku"]
            n_val = it["name"]
            c_val = it["unit_cost"]
            row = conn.execute("SELECT 1 FROM products WHERE sku = ?", (s_val,)).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO products (sku, name, base_unit, cost_price, selling_price, safety_stock, is_active)
                    VALUES (?, ?, 'PCS', ?, ?, 0, 1)
                    """,
                    (s_val, n_val, float(c_val), float(c_val * Decimal("1.5"))),
                )

    # Group by supplier
    by_supplier: Dict[str, List[Tuple[str, Decimal, Decimal]]] = {}
    for it in valid_items:
        by_supplier.setdefault(it["supplier_name"], []).append((it["sku"], it["qty"], it["unit_cost"]))

    created_pos = []
    for supp, it_list in by_supplier.items():
        try:
            po = procurement_service.create_purchase_order(supplier_name=supp, items=it_list)
            created_pos.append(po)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"為供應商【{supp}】建立採購單失敗: {e}")

    po_ids_str = ", ".join(p.po_id for p in created_pos)
    if skipped_items:
        summary_text = (
            f"成功為 {len(created_pos)} 家供應商自動分割建立採購單（單號：{po_ids_str}）！"
            f"另有 {len(skipped_items)} 筆物料因未指定供應商或單價為 0 已自動排除，未產生無效採購單。"
        )
    else:
        summary_text = f"成功為 {len(created_pos)} 家供應商自動分割建立採購單！單號：{po_ids_str}"

    pos = view_service.list_purchase_orders()
    products = view_service.list_active_products_for_po()
    warehouses = view_service.list_warehouses_for_select()

    page_html = templates.get_template("procurement.html").render({
        "request": request,
        "active_page": "procurement",
        "pos": pos,
        "products": products,
        "warehouses": warehouses,
        "prefill_sku": "",
    })
    po_ids_undo_str = ",".join(p.po_id for p in created_pos)
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=summary_text,
        type="success",
        undo_url="/procurement/bom/create-pos/undo" if created_pos else None,
        undo_vals={"po_ids": po_ids_undo_str} if created_pos else None,
        undo_label="撤回建立",
        undo_target="#procurement-container",
        undo_select="#procurement-container",
        undo_swap="outerHTML",
        ttl_seconds=8,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")


@router.post("/bom/create-pos/undo", response_class=HTMLResponse)
async def undo_create_pos_from_bom_endpoint(
    request: Request,
    po_ids: str = Form(""),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """撤回 BOM 批次自動分割建立之採購單。"""
    canceled_ids: List[str] = []
    if po_ids:
        for raw_id in po_ids.split(","):
            pid = raw_id.strip()
            if pid:
                try:
                    procurement_service.cancel_purchase_order(pid)
                    canceled_ids.append(pid)
                except Exception:
                    pass

    pos = view_service.list_purchase_orders()
    products = view_service.list_active_products_for_po()
    warehouses = view_service.list_warehouses_for_select()

    page_html = templates.get_template("procurement.html").render({
        "request": request,
        "active_page": "procurement",
        "pos": pos,
        "products": products,
        "warehouses": warehouses,
        "prefill_sku": "",
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回 BOM 自動分割建立之 {len(canceled_ids)} 張採購單！單號：{', '.join(canceled_ids)}",
        type="info",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")


@router.post("/create", response_class=HTMLResponse)
async def create_purchase_order_endpoint(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """建立新採購單 (DRAFT)，支援單項與多品項明細。"""
    form_data = await request.form()
    supplier_name = str(form_data.get("supplier_name", "")).strip()
    if not supplier_name:
        raise HTTPException(status_code=400, detail="請輸入供應商名稱")

    # Collect items from form lists or indexed fields
    skus = form_data.getlist("sku")
    qtys = form_data.getlist("qty")
    unit_costs = form_data.getlist("unit_cost")

    items: List[Tuple[str, Decimal, Decimal]] = []
    if skus and qtys and unit_costs:
        for s, q, c in zip(skus, qtys, unit_costs):
            s_val = str(s).strip().upper()
            if not s_val:
                continue
            try:
                q_val = Decimal(str(q))
                c_val = Decimal(str(c))
            except Exception:
                raise HTTPException(status_code=400, detail=f"品號 {s_val} 之數量或單價格式錯誤")
            if q_val <= Decimal("0.0"):
                raise HTTPException(status_code=400, detail=f"品號 {s_val} 之採購數量必須大於 0")
            if c_val < Decimal("0.0"):
                raise HTTPException(status_code=400, detail=f"品號 {s_val} 之進貨單價不得為負數")
            items.append((s_val, q_val, c_val))

    if not items:
        raise HTTPException(status_code=400, detail="採購單必須包含至少一項有效物料")

    target_warehouse = str(form_data.get("target_warehouse") or form_data.get("warehouse_id") or "WH-MAIN").strip()

    try:
        po = procurement_service.create_purchase_order(
            supplier_name=supplier_name,
            items=items,
            warehouse_id=target_warehouse,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if request.headers.get("HX-Request") == "true":
        pos = view_service.list_purchase_orders()
        products = view_service.list_active_products_for_po()
        warehouses = view_service.list_warehouses_for_select()
        page_html = templates.get_template("procurement.html").render({
            "request": request,
            "active_page": "procurement",
            "pos": pos,
            "products": products,
            "warehouses": warehouses,
            "prefill_sku": "",
        })
        toast_html = render_toast_oob(
            templates=templates,
            request=request,
            message=f"成功建立採購單 {po.po_id}（供應商：{po.supplier_name}，金額：NT$ {po.total_amount:,.2f}）",
            type="success",
            undo_url=f"/procurement/{po.po_id}/cancel",
            undo_label="撤回建立",
            undo_target="#procurement-container",
            undo_select="#procurement-container",
            undo_swap="outerHTML",
            ttl_seconds=6,
        )
        return HTMLResponse(content=f"{page_html}\n{toast_html}")

    return RedirectResponse(url="/procurement", status_code=303)


@router.post("/{po_id}/cancel", response_class=HTMLResponse)
async def cancel_purchase_order_endpoint(
    po_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """撤回/取消建立採購單。"""
    try:
        procurement_service.cancel_purchase_order(po_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    pos = view_service.list_purchase_orders()
    products = view_service.list_active_products_for_po()
    warehouses = view_service.list_warehouses_for_select()
    page_html = templates.get_template("procurement.html").render({
        "request": request,
        "active_page": "procurement",
        "pos": pos,
        "products": products,
        "warehouses": warehouses,
        "prefill_sku": "",
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"已成功撤回採購單建立 ({po_id})，狀態已標記為取消。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{page_html}\n{toast_html}")


@router.post("/{po_id}/submit", response_class=HTMLResponse)
async def submit_purchase_order_endpoint(
    po_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """送出採購單，推進狀態至 SUBMITTED。"""
    try:
        procurement_service.submit_purchase_order(po_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_purchase_order_row(po_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"查無採購單 {po_id}")

    row_html = templates.get_template("partials/po_row.html").render({
        "request": request,
        "po": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"採購單 {po_id} 已確認送出，等待供應商到貨！",
        type="success",
        undo_url=f"/procurement/{po_id}/submit/undo",
        undo_label="撤回下訂",
        undo_target=f"#po-row-{po_id}",
        undo_swap="outerHTML",
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")


@router.post("/{po_id}/submit/undo", response_class=HTMLResponse)
async def undo_submit_purchase_order_endpoint(
    po_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """撤回採購單下訂送出，復原至 DRAFT 狀態。"""
    try:
        procurement_service.revert_submit_purchase_order(po_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_purchase_order_row(po_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"查無採購單 {po_id}")

    row_html = templates.get_template("partials/po_row.html").render({
        "request": request,
        "po": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"採購單 {po_id} 已成功撤回下訂，已恢復為草稿 (DRAFT)。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")


@router.get("/{po_id}/receive-modal", response_class=HTMLResponse)
async def get_receive_po_modal_endpoint(
    po_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
):
    """渲染驗收入庫目的倉庫確認彈窗。"""
    dto = view_service.get_purchase_order_row(po_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"查無採購單 {po_id}")

    warehouses = view_service.list_warehouses_for_select()
    return templates.TemplateResponse(
        request=request,
        name="partials/receive_po_modal.html",
        context={
            "po": dto,
            "warehouses": warehouses,
        },
    )


@router.post("/{po_id}/receive", response_class=HTMLResponse)
async def receive_purchase_order_endpoint(
    po_id: str,
    request: Request,
    warehouse_id: Optional[str] = Form(None),
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """驗收入庫：生成入庫單 GRN、寫入庫存流水、重算移動平均成本、自動立帳會計 AP。"""
    form_data = await request.form()
    safety_stocks: Dict[str, int] = {}
    for key, value in form_data.items():
        if key.startswith("safety_stock_"):
            sku = key[len("safety_stock_"):]
            try:
                safety_stocks[sku] = int(str(value))
            except (ValueError, TypeError):
                pass

    try:
        grn = procurement_service.receive_goods(
            po_id=po_id,
            warehouse_id=warehouse_id,
            safety_stocks=safety_stocks if safety_stocks else None,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_purchase_order_row(po_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"查無採購單 {po_id}")

    row_html = templates.get_template("partials/po_row.html").render({
        "request": request,
        "po": dto,
    })
    modal_close_html = '<div id="modal-container" hx-swap-oob="innerHTML:#modal-container"></div>'
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"採購單 {po_id} 已成功驗收入庫！入庫單號：{grn.grn_id}（入庫倉庫：{grn.warehouse_id}），移動平均成本已重算並完成應付立帳！",
        type="success",
        undo_url=f"/procurement/{po_id}/receive/undo",
        undo_label="撤回入庫",
        undo_target=f"#po-row-{po_id}",
        undo_swap="outerHTML",
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{modal_close_html}\n{toast_html}")


@router.post("/{po_id}/receive/undo", response_class=HTMLResponse)
async def undo_receive_purchase_order_endpoint(
    po_id: str,
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    view_service: WebViewService = Depends(get_view_service),
    procurement_service: ProcurementService = Depends(get_procurement_service),
):
    """撤回採購單驗收入庫（紅字退庫沖銷、復原採購單至 SUBMITTED、沖銷 AP 與傳票）。"""
    try:
        procurement_service.revert_goods_receipt(po_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    dto = view_service.get_purchase_order_row(po_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"查無採購單 {po_id}")

    row_html = templates.get_template("partials/po_row.html").render({
        "request": request,
        "po": dto,
    })
    toast_html = render_toast_oob(
        templates=templates,
        request=request,
        message=f"採購單 {po_id} 已成功撤回驗收入庫（已紅字沖銷庫存與會計分錄），採購單恢復為待到貨 (SUBMITTED) 狀態。",
        type="success",
        undo_url=None,
        ttl_seconds=6,
    )
    return HTMLResponse(content=f"{row_html}\n{toast_html}")


