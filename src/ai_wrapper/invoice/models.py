from __future__ import annotations
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class ExtractedInvoiceItem(BaseModel):
    """Line item extracted from a Taiwan electronic invoice PDF."""
    description: str = Field(..., description="品名 / 項目說明")
    qty: Decimal = Field(Decimal("1.0"), description="數量")
    unit_price: Decimal = Field(Decimal("0.0"), description="單價")
    amount: Decimal = Field(Decimal("0.0"), description="金額 / 小計")


class ExtractedTaiwanInvoice(BaseModel):
    """Structured data extracted from a native Taiwan electronic invoice PDF."""
    invoice_number: str = Field(..., description="發票字軌號碼 (2碼英文+8碼數字)")
    seller_tax_id: Optional[str] = Field(None, description="賣方統一編號 (8碼)")
    seller_name: Optional[str] = Field(None, description="賣方營業人名稱")
    buyer_tax_id: Optional[str] = Field(None, description="買方統一編號 (8碼)")
    buyer_name: Optional[str] = Field(None, description="買方營業人名稱")
    invoice_date: Optional[str] = Field(None, description="開立日期 (YYYY-MM-DD)")
    sales_amount: Decimal = Field(Decimal("0.0"), description="銷售額 / 未稅金額")
    tax_amount: Decimal = Field(Decimal("0.0"), description="營業稅額")
    total_amount: Decimal = Field(Decimal("0.0"), description="總計金額 (含稅)")
    random_code: Optional[str] = Field(None, description="4 碼隨機碼")
    items: List[ExtractedInvoiceItem] = Field(default_factory=list, description="發票品項明細")
    is_math_valid: bool = Field(True, description="總金額是否等於未稅金額加稅額")
    validation_warnings: List[str] = Field(default_factory=list, description="檢驗提示或警告訊息")


class InvoiceMatchResult(BaseModel):
    """Result of matching an extracted invoice against ERP procurement and supplier master data."""
    extracted: ExtractedTaiwanInvoice
    matched_po_id: Optional[str] = None
    matched_supplier: Optional[str] = None
    existing_ap_id: Optional[str] = None
    status: str = "NEW"  # "NEW", "MATCHED_PO", "ALREADY_RECORDED", "MATH_ERROR"
