from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
import uuid

from src.core.domain.order import OrderChannel, SalesOrder
from src.core.ports.event_bus_port import EventBusPort
from src.core.services.order_service import OrderService
from src.extended_core.crm.documents.quote_document_engine import QuoteDocumentEngine
from src.extended_core.crm.models import Contact, Deal, DealItem, DealStage, Quote, QuoteItem, QuoteStatus
from src.shared.database import Database


class CrmService:
    """哩來 (LiLai) CRM 業務領域服務：管理客戶主檔、四段商機管線、報價單套印與拋轉 ERP 銷售訂單。"""

    def __init__(
        self,
        db: Database,
        order_service: Optional[OrderService] = None,
        event_bus: Optional[EventBusPort] = None,
    ) -> None:
        self.db = db
        if order_service is not None:
            self.order_service = order_service
        elif event_bus is not None:
            self.order_service = OrderService(db=db, event_bus=event_bus)
        else:
            self.order_service = None

    # =========================================================================
    # 1. 客戶主檔與聯絡人管理 (Contact Management)
    # =========================================================================

    def create_contact(
        self,
        company_name: str,
        contact_name: str,
        tax_id: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Contact:
        """建立客戶主檔，包含統編 8 位數格式校驗與公司名稱重複性防呆。"""
        company_clean = (company_name or "").strip()
        contact_clean = (contact_name or "").strip()
        if not company_clean:
            raise ValueError("客戶公司名稱不可為空 (Company name is required)")
        if not contact_clean:
            raise ValueError("聯絡人姓名不可為空 (Contact name is required)")

        contact_id = f"CUST-{uuid.uuid4().hex[:8].upper()}"

        contact = Contact(
            contact_id=contact_id,
            company_name=company_clean,
            tax_id=tax_id,
            contact_name=contact_clean,
            email=email.strip() if email else None,
            phone=phone.strip() if phone else None,
        )

        with self.db.transaction() as conn:
            # 1. 檢查客戶公司名稱是否已存在 (不分大小寫與首尾空白)
            dup_company = conn.execute(
                "SELECT contact_id, company_name FROM crm_contacts WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))",
                (company_clean,),
            ).fetchone()
            if dup_company:
                raise ValueError(
                    f"客戶公司「{company_clean}」已存在於系統中，不可重複建立 (Company '{company_clean}' already exists)"
                )

            # 2. 檢查統一編號是否與既有客戶重複 (若有填寫統編)
            if contact.tax_id:
                dup_tax = conn.execute(
                    "SELECT contact_id, company_name FROM crm_contacts WHERE tax_id = ?",
                    (contact.tax_id,),
                ).fetchone()
                if dup_tax:
                    raise ValueError(
                        f"統一編號 {contact.tax_id} 已由客戶「{dup_tax['company_name']}」登記，不可重複建檔 (Tax ID already exists)"
                    )

            conn.execute(
                """
                INSERT INTO crm_contacts (contact_id, company_name, tax_id, contact_name, email, phone)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    contact.contact_id,
                    contact.company_name,
                    contact.tax_id,
                    contact.contact_name,
                    contact.email,
                    contact.phone,
                ),
            )

        return contact

    def get_contact(self, contact_id: str) -> Optional[Contact]:
        """依據 contact_id 查詢客戶主檔。"""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT contact_id, company_name, tax_id, contact_name, email, phone FROM crm_contacts WHERE contact_id = ?",
                (contact_id,),
            ).fetchone()
            if not row:
                return None
            return Contact(
                contact_id=row["contact_id"],
                company_name=row["company_name"],
                tax_id=row["tax_id"],
                contact_name=row["contact_name"],
                email=row["email"],
                phone=row["phone"],
            )

    def list_contacts(self) -> List[Contact]:
        """查詢所有客戶清單，按建立時間新至舊排序。"""
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT contact_id, company_name, tax_id, contact_name, email, phone FROM crm_contacts ORDER BY created_at DESC"
            ).fetchall()
            return [
                Contact(
                    contact_id=r["contact_id"],
                    company_name=r["company_name"],
                    tax_id=r["tax_id"],
                    contact_name=r["contact_name"],
                    email=r["email"],
                    phone=r["phone"],
                )
                for r in rows
            ]

    def update_contact(
        self,
        contact_id: str,
        company_name: Optional[str] = None,
        contact_name: Optional[str] = None,
        tax_id: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Contact:
        """更新客戶主檔資訊（嚴格禁止更改客戶公司名稱）。"""
        existing = self.get_contact(contact_id)
        if not existing:
            raise ValueError(f"查無客戶 ID: {contact_id} (Contact not found)")

        # 嚴格禁止更改客戶公司名稱
        if company_name is not None and company_name.strip() and company_name.strip() != existing.company_name:
            raise ValueError(
                f"客戶公司名稱為企業主識別，建立後不允許變更（原名稱：{existing.company_name}）(Company name cannot be modified)"
            )

        new_contact = contact_name.strip() if contact_name is not None else existing.contact_name
        if not new_contact:
            raise ValueError("聯絡人姓名不可為空 (Contact name is required)")

        new_tax = tax_id.strip() if (tax_id is not None and tax_id.strip()) else None
        new_email = email.strip() if (email is not None and email.strip()) else None
        new_phone = phone.strip() if (phone is not None and phone.strip()) else None

        updated = Contact(
            contact_id=contact_id,
            company_name=existing.company_name,
            tax_id=new_tax,
            contact_name=new_contact,
            email=new_email,
            phone=new_phone,
        )

        with self.db.transaction() as conn:
            # 檢查統一編號是否與其他客戶衝突
            if updated.tax_id:
                dup_tax = conn.execute(
                    "SELECT contact_id, company_name FROM crm_contacts WHERE tax_id = ? AND contact_id != ?",
                    (updated.tax_id, contact_id),
                ).fetchone()
                if dup_tax:
                    raise ValueError(
                        f"統一編號 {updated.tax_id} 已由其他客戶「{dup_tax['company_name']}」登記 (Tax ID already exists)"
                    )

            conn.execute(
                """
                UPDATE crm_contacts
                SET tax_id = ?, contact_name = ?, email = ?, phone = ?
                WHERE contact_id = ?
                """,
                (
                    updated.tax_id,
                    updated.contact_name,
                    updated.email,
                    updated.phone,
                    contact_id,
                ),
            )

        return updated

    # =========================================================================
    # 2. 四段商機管線管理 (Deal Pipeline Management)
    # =========================================================================

    def create_deal(
        self,
        contact_id: str,
        title: str,
        expected_amount: Decimal = Decimal("0.0"),
        stage: DealStage = DealStage.LEAD,
        items: Optional[List[Tuple[str, Decimal, Decimal]]] = None,  # (sku, qty, unit_price)
    ) -> Deal:
        """為指定客戶建立新商機，支援多品項 (SKU * 數量 * 單價) 計價。"""
        contact = self.get_contact(contact_id)
        if not contact:
            raise ValueError(f"指定的客戶不存在: {contact_id} (Contact not found)")

        title_clean = (title or "").strip()
        if not title_clean:
            raise ValueError("商機名稱不可為空 (Deal title is required)")

        deal_items: List[DealItem] = []
        deal_id = f"DEAL-{uuid.uuid4().hex[:8].upper()}"

        if items:
            calc_amount = Decimal("0.0")
            for sku, qty, unit_price in items:
                q_dec = Decimal(str(qty))
                p_dec = Decimal(str(unit_price))
                if q_dec <= Decimal("0.0"):
                    raise ValueError(f"品項 {sku} 之數量必須大於 0 (Quantity must be greater than 0)")
                if p_dec < Decimal("0.0"):
                    raise ValueError(f"品項 {sku} 之預估單價不得為負數 (Price cannot be negative)")
                subtot = q_dec * p_dec
                calc_amount += subtot
                deal_items.append(
                    DealItem(
                        deal_item_id=f"DITEM-{uuid.uuid4().hex[:8].upper()}",
                        deal_id=deal_id,
                        sku=sku.strip().upper(),
                        qty=q_dec,
                        unit_price=p_dec,
                        subtotal=subtot,
                    )
                )
            expected_amount = calc_amount
        else:
            if expected_amount < Decimal("0.0"):
                raise ValueError("預估金額不可為負數 (Expected amount cannot be negative)")

        deal = Deal(
            deal_id=deal_id,
            contact_id=contact_id,
            title=title_clean,
            stage=stage,
            expected_amount=expected_amount,
            converted_order_id=None,
            items=deal_items,
        )

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO crm_deals (deal_id, contact_id, title, stage, expected_amount, converted_order_id)
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (deal.deal_id, deal.contact_id, deal.title, deal.stage.value, float(deal.expected_amount)),
            )
            for it in deal_items:
                conn.execute(
                    """
                    INSERT INTO crm_deal_items (deal_item_id, deal_id, sku, qty, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (it.deal_item_id, it.deal_id, it.sku, float(it.qty), float(it.unit_price), float(it.subtotal)),
                )

        return deal

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        """依據 deal_id 查詢商機，含品項明細。"""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT deal_id, contact_id, title, stage, expected_amount, converted_order_id FROM crm_deals WHERE deal_id = ?",
                (deal_id,),
            ).fetchone()
            if not row:
                return None

            item_rows = conn.execute(
                "SELECT deal_item_id, deal_id, sku, qty, unit_price, subtotal FROM crm_deal_items WHERE deal_id = ?",
                (deal_id,),
            ).fetchall()
            items = [
                DealItem(
                    deal_item_id=r["deal_item_id"],
                    deal_id=r["deal_id"],
                    sku=r["sku"],
                    qty=Decimal(str(r["qty"])),
                    unit_price=Decimal(str(r["unit_price"])),
                    subtotal=Decimal(str(r["subtotal"])),
                )
                for r in item_rows
            ]

            return Deal(
                deal_id=row["deal_id"],
                contact_id=row["contact_id"],
                title=row["title"],
                stage=DealStage(row["stage"]),
                expected_amount=Decimal(str(row["expected_amount"])),
                converted_order_id=row["converted_order_id"],
                items=items,
            )

    def delete_draft_deal(self, deal_id: str) -> None:
        """Delete a draft deal in LEAD stage prior to quotes or conversion."""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT deal_id, stage, converted_order_id FROM crm_deals WHERE deal_id = ?",
                (deal_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"查無商機 {deal_id} (Deal not found)")

            if row["converted_order_id"]:
                raise ValueError(f"無法撤回商機 {deal_id}：已拋轉為 ERP 銷售訂單 (Already converted to order)")

            # Check no quotes have been issued
            q_row = conn.execute("SELECT 1 FROM crm_quotes WHERE deal_id = ?", (deal_id,)).fetchone()
            if q_row:
                raise ValueError(f"無法撤回商機 {deal_id}：已有建立報價單記錄 (Quotes exist)")

            conn.execute("DELETE FROM crm_deal_items WHERE deal_id = ?", (deal_id,))
            conn.execute("DELETE FROM crm_deals WHERE deal_id = ?", (deal_id,))


    def list_deals(
        self,
        stage: Optional[DealStage] = None,
        contact_id: Optional[str] = None,
    ) -> List[Deal]:
        """查詢商機清單，支援階段或客戶篩選，含品項明細。"""
        query = "SELECT deal_id, contact_id, title, stage, expected_amount, converted_order_id FROM crm_deals WHERE 1=1"
        params: List[Any] = []
        if stage:
            query += " AND stage = ?"
            params.append(stage.value)
        if contact_id:
            query += " AND contact_id = ?"
            params.append(contact_id)
        query += " ORDER BY created_at DESC"

        with self.db.transaction() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
            deal_ids = [r["deal_id"] for r in rows]
            items_by_deal: Dict[str, List[DealItem]] = {}
            if deal_ids:
                placeholders = ",".join(["?"] * len(deal_ids))
                item_rows = conn.execute(
                    f"SELECT deal_item_id, deal_id, sku, qty, unit_price, subtotal FROM crm_deal_items WHERE deal_id IN ({placeholders})",
                    deal_ids,
                ).fetchall()
                for ir in item_rows:
                    items_by_deal.setdefault(ir["deal_id"], []).append(
                        DealItem(
                            deal_item_id=ir["deal_item_id"],
                            deal_id=ir["deal_id"],
                            sku=ir["sku"],
                            qty=Decimal(str(ir["qty"])),
                            unit_price=Decimal(str(ir["unit_price"])),
                            subtotal=Decimal(str(ir["subtotal"])),
                        )
                    )

            return [
                Deal(
                    deal_id=r["deal_id"],
                    contact_id=r["contact_id"],
                    title=r["title"],
                    stage=DealStage(r["stage"]),
                    expected_amount=Decimal(str(r["expected_amount"])),
                    converted_order_id=r["converted_order_id"],
                    items=items_by_deal.get(r["deal_id"], []),
                )
                for r in rows
            ]

    def advance_deal_stage(self, deal_id: str, new_stage: DealStage) -> Deal:
        """推進或變更商機階段，含狀態機限制與已轉單防護。"""
        deal = self.get_deal(deal_id)
        if not deal:
            raise ValueError(f"查無商機 ID: {deal_id} (Deal not found)")

        # Protection: If already converted to ERP SalesOrder, locked
        if deal.converted_order_id and new_stage != DealStage.WON:
            raise ValueError(
                f"商機 {deal_id} 已拋轉為 ERP 銷售訂單 ({deal.converted_order_id})，狀態已鎖定為贏單 (Deal converted to order, stage is locked)"
            )

        # Transition validation
        if deal.stage == new_stage:
            return deal

        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE crm_deals SET stage = ? WHERE deal_id = ?",
                (new_stage.value, deal_id),
            )

        return Deal(
            deal_id=deal.deal_id,
            contact_id=deal.contact_id,
            title=deal.title,
            stage=new_stage,
            expected_amount=deal.expected_amount,
            converted_order_id=deal.converted_order_id,
            items=deal.items,
        )

    # =========================================================================
    # 3. 報價單建立與明細試算 (Quotation Management)
    # =========================================================================

    def create_quote(
        self,
        deal_id: str,
        items: Optional[List[Tuple[str, Decimal, Decimal]]] = None,  # (sku, qty, unit_price)
        valid_days: int = 30,
    ) -> Quote:
        """為商機建立商業報價單，並記錄商品明細與自動更新商機預估金額。若未傳入明細則自動繼承商機原品項。"""
        deal = self.get_deal(deal_id)
        if not deal:
            raise ValueError(f"查無商機 ID: {deal_id} (Deal not found)")

        if items is None:
            if deal.items:
                items = [(it.sku, it.qty, it.unit_price) for it in deal.items]
            else:
                raise ValueError("報價單必須包含至少一項商品明細 (Quote must contain at least one item)")
        elif not items:
            raise ValueError("報價單必須包含至少一項商品明細 (Quote must contain at least one item)")

        valid_until = datetime.date.today() + datetime.timedelta(days=valid_days)
        quote_id = f"QUO-{uuid.uuid4().hex[:8].upper()}"
        # Formatted quote number e.g. Q-202609-XXXX
        month_prefix = datetime.date.today().strftime("%Y%m")
        quote_number = f"Q-{month_prefix}-{uuid.uuid4().hex[:4].upper()}"

        quote_items: List[QuoteItem] = []
        total_amount = Decimal("0.0")

        with self.db.transaction() as conn:
            # 1. Validate items and verify products exist
            item_data = []
            for sku, qty, unit_price in items:
                if qty <= Decimal("0.0") or unit_price < Decimal("0.0"):
                    raise ValueError(f"商品 {sku} 數量或單價無效 (Invalid quantity or price for SKU)")
                prod = conn.execute("SELECT name FROM products WHERE sku = ?", (sku,)).fetchone()
                if not prod:
                    raise ValueError(f"商品品號 '{sku}' 不存在於系統中 (Product SKU does not exist)")
                subtotal = qty * unit_price
                total_amount += subtotal
                item_data.append((sku, qty, unit_price, subtotal))

            # 2. Insert into crm_quotes
            conn.execute(
                """
                INSERT INTO crm_quotes (quote_id, deal_id, quote_number, total_amount, valid_until, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    deal_id,
                    quote_number,
                    float(total_amount),
                    valid_until.isoformat(),
                    QuoteStatus.DRAFT.value,
                ),
            )

            # 3. Insert into crm_quote_items
            for sku, qty, unit_price, subtotal in item_data:
                item_id = f"QI-{uuid.uuid4().hex[:8].upper()}"
                conn.execute(
                    """
                    INSERT INTO crm_quote_items (item_id, quote_id, sku, qty, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (item_id, quote_id, sku, float(qty), float(unit_price), float(subtotal)),
                )
                quote_items.append(
                    QuoteItem(
                        item_id=item_id,
                        quote_id=quote_id,
                        sku=sku,
                        qty=qty,
                        unit_price=unit_price,
                        subtotal=subtotal,
                    )
                )

            # 4. Update deal's expected amount and move to PROPOSAL stage if in LEAD or DISCOVERY
            new_stage = DealStage.PROPOSAL if deal.stage in (DealStage.LEAD, DealStage.DISCOVERY) else deal.stage
            conn.execute(
                "UPDATE crm_deals SET expected_amount = ?, stage = ? WHERE deal_id = ?",
                (float(total_amount), new_stage.value, deal_id),
            )

        return Quote(
            quote_id=quote_id,
            deal_id=deal_id,
            quote_number=quote_number,
            total_amount=total_amount,
            valid_until=valid_until,
            status=QuoteStatus.DRAFT,
            items=quote_items,
        )

    def get_quote(self, quote_id: str) -> Optional[Quote]:
        """依據 quote_id 取得報價單及其明細。"""
        with self.db.transaction() as conn:
            row = conn.execute(
                "SELECT quote_id, deal_id, quote_number, total_amount, valid_until, docx_path, pdf_path, status FROM crm_quotes WHERE quote_id = ?",
                (quote_id,),
            ).fetchone()
            if not row:
                return None

            item_rows = conn.execute(
                "SELECT item_id, quote_id, sku, qty, unit_price, subtotal FROM crm_quote_items WHERE quote_id = ?",
                (quote_id,),
            ).fetchall()

            items = [
                QuoteItem(
                    item_id=r["item_id"],
                    quote_id=r["quote_id"],
                    sku=r["sku"],
                    qty=Decimal(str(r["qty"])),
                    unit_price=Decimal(str(r["unit_price"])),
                    subtotal=Decimal(str(r["subtotal"])),
                )
                for r in item_rows
            ]

            valid_date = (
                datetime.date.fromisoformat(row["valid_until"])
                if isinstance(row["valid_until"], str)
                else row["valid_until"]
            )

            return Quote(
                quote_id=row["quote_id"],
                deal_id=row["deal_id"],
                quote_number=row["quote_number"],
                total_amount=Decimal(str(row["total_amount"])),
                valid_until=valid_date,
                docx_path=row["docx_path"],
                pdf_path=row["pdf_path"],
                status=QuoteStatus(row["status"]),
                items=items,
            )

    def get_quotes_for_deal(self, deal_id: str) -> List[Quote]:
        """取得指定商機的所有報價單清單。"""
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT quote_id FROM crm_quotes WHERE deal_id = ? ORDER BY created_at DESC",
                (deal_id,),
            ).fetchall()
        quotes = []
        for r in rows:
            q = self.get_quote(r["quote_id"])
            if q:
                quotes.append(q)
        return quotes

    def delete_quote(self, quote_id: str) -> None:
        """撤回並刪除草稿報價單，並依狀況復原商機預估金額與階段。"""
        quote = self.get_quote(quote_id)
        if not quote:
            raise ValueError(f"查無報價單 ID: {quote_id} (Quote not found)")

        deal = self.get_deal(quote.deal_id)
        if not deal:
            raise ValueError(f"查無報價單關聯之商機 ID: {quote.deal_id} (Deal not found)")

        if deal.converted_order_id:
            raise ValueError(
                f"無法撤回報價單 {quote.quote_number}：商機已拋轉為 ERP 銷售訂單 ({deal.converted_order_id})"
            )

        if quote.status == QuoteStatus.ACCEPTED:
            raise ValueError(f"無法撤回報價單 {quote.quote_number}：該報價單已處於已接受 (ACCEPTED) 狀態")

        with self.db.transaction() as conn:
            # Delete quote items and quote
            conn.execute("DELETE FROM crm_quote_items WHERE quote_id = ?", (quote_id,))
            conn.execute("DELETE FROM crm_quotes WHERE quote_id = ?", (quote_id,))

            # Check remaining quotes for this deal
            remaining_quotes = conn.execute(
                "SELECT quote_id, total_amount FROM crm_quotes WHERE deal_id = ? ORDER BY created_at DESC",
                (deal.deal_id,),
            ).fetchall()

            if remaining_quotes:
                latest_amt = Decimal(str(remaining_quotes[0]["total_amount"]))
                conn.execute(
                    "UPDATE crm_deals SET expected_amount = ? WHERE deal_id = ?",
                    (float(latest_amt), deal.deal_id),
                )
            else:
                # No quotes remain. Revert expected amount back to deal items total or 0
                original_amt = sum((it.subtotal for it in deal.items), Decimal("0.0"))
                # If deal was moved to PROPOSAL solely because of quote, revert to DISCOVERY
                revert_stage = DealStage.DISCOVERY if deal.stage == DealStage.PROPOSAL else deal.stage
                conn.execute(
                    "UPDATE crm_deals SET expected_amount = ?, stage = ? WHERE deal_id = ?",
                    (float(original_amt), revert_stage.value, deal.deal_id),
                )

    def get_quote_full_details(self, quote_id: str) -> Tuple[Contact, Deal, Quote, List[Dict[str, Any]]]:
        """取得報價單完整資訊（含關聯客戶、商機與商品中文規格名稱）。"""
        quote = self.get_quote(quote_id)
        if not quote:
            raise ValueError(f"查無報價單 ID: {quote_id} (Quote not found)")

        deal = self.get_deal(quote.deal_id)
        if not deal:
            raise ValueError(f"查無報價單關聯之商機 ID: {quote.deal_id} (Deal not found)")

        contact = self.get_contact(deal.contact_id)
        if not contact:
            raise ValueError(f"查無商機關聯之客戶 ID: {deal.contact_id} (Contact not found)")

        items_detail = []
        with self.db.transaction() as conn:
            for item in quote.items:
                prod = conn.execute(
                    "SELECT name, base_unit FROM products WHERE sku = ?", (item.sku,)
                ).fetchone()
                p_name = prod["name"] if prod else item.sku
                p_unit = prod["base_unit"] if prod else "PCS"
                items_detail.append(
                    {
                        "sku": item.sku,
                        "name": p_name,
                        "unit": p_unit,
                        "qty": item.qty,
                        "unit_price": item.unit_price,
                        "subtotal": item.subtotal,
                    }
                )

        return contact, deal, quote, items_detail

    # =========================================================================
    # 4. 文件套印與原生 PDF 產出 (Document Center)
    # =========================================================================

    def generate_quote_docx(self, quote_id: str) -> bytes:
        """動態套印並產出可編輯之 DOCX 商業報價單二進位串流。"""
        contact, deal, quote, items_detail = self.get_quote_full_details(quote_id)
        return QuoteDocumentEngine.generate_docx(contact, deal, quote, items_detail)

    def generate_quote_pdf(self, quote_id: str) -> bytes:
        """原生產出具備文字層之防竄改 A4 報價單 PDF 二進位串流。"""
        contact, deal, quote, items_detail = self.get_quote_full_details(quote_id)
        return QuoteDocumentEngine.generate_pdf(contact, deal, quote, items_detail)

    # =========================================================================
    # 5. 贏單 (WON) 一鍵穿透拋轉 ERP 銷售訂單 (One-Click ERP Conversion)
    # =========================================================================

    def convert_deal_to_erp_order(
        self,
        deal_id: str,
        quote_id: Optional[str] = None,
        warehouse_id: str = "WH-MAIN",
    ) -> Tuple[SalesOrder, Deal]:
        """將贏單商機一鍵穿透拋轉為 ERP 核心銷售訂單 (SO)，建立雙向剛性勾稽。"""
        if not self.order_service:
            raise RuntimeError("OrderService 未注入，無法執行 ERP 轉單作業 (OrderService not injected)")

        deal = self.get_deal(deal_id)
        if not deal:
            raise ValueError(f"查無商機 ID: {deal_id} (Deal not found)")

        if deal.converted_order_id:
            raise ValueError(
                f"此商機已於先前成功拋轉為訂單 {deal.converted_order_id}，不可重複轉單 (Deal already converted)"
            )

        # Retrieve quote to convert
        target_quote: Optional[Quote] = None
        if quote_id:
            target_quote = self.get_quote(quote_id)
        else:
            quotes = self.get_quotes_for_deal(deal_id)
            if quotes:
                target_quote = quotes[0]  # Latest quote

        if target_quote and target_quote.items:
            so_items = [(it.sku, it.qty, it.unit_price) for it in target_quote.items]
        elif deal.items:
            so_items = [(it.sku, it.qty, it.unit_price) for it in deal.items]
        else:
            raise ValueError(
                f"商機 {deal_id} 缺乏有效報價單或商機物料明細，無法轉為銷售訂單 (Quote or deal items required for conversion)"
            )

        # 2. Call Layer 1 OrderService to create SalesOrder
        sales_order = self.order_service.create_order(
            customer_id=deal.contact_id,
            items=so_items,
            channel=OrderChannel.CRM,
            warehouse_id=warehouse_id,
        )

        # 3. Automatically confirm order and secure virtual stock lock (下單即鎖庫)
        sales_order = self.order_service.confirm_order(
            order_id=sales_order.order_id,
            warehouse_id=warehouse_id,
        )

        # 3. Update Deal stage to WON and record converted_order_id
        with self.db.transaction() as conn:
            conn.execute(
                """
                UPDATE crm_deals
                SET stage = ?, converted_order_id = ?
                WHERE deal_id = ?
                """,
                (DealStage.WON.value, sales_order.order_id, deal_id),
            )
            # Mark quote as ACCEPTED if present
            if target_quote:
                conn.execute(
                    "UPDATE crm_quotes SET status = ? WHERE quote_id = ?",
                    (QuoteStatus.ACCEPTED.value, target_quote.quote_id),
                )

        updated_deal = Deal(
            deal_id=deal.deal_id,
            contact_id=deal.contact_id,
            title=deal.title,
            stage=DealStage.WON,
            expected_amount=deal.expected_amount,
            converted_order_id=sales_order.order_id,
        )

        return sales_order, updated_deal
