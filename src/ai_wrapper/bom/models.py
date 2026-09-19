from __future__ import annotations
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class BomItem(BaseModel):
    """Single item line extracted from an uploaded BOM Excel file."""
    sku: str = Field(..., description="料號 / SKU 代碼")
    name: str = Field(..., description="品名 / 物料名稱")
    spec: Optional[str] = Field(None, description="規格描述")
    qty: Decimal = Field(..., description="需求數量")
    unit: str = Field("PCS", description="單位")
    level: int = Field(1, description="BOM 階層")


class BomParseResult(BaseModel):
    """Result of parsing an uploaded BOM Excel file."""
    items: List[BomItem] = Field(default_factory=list)
    total_rows: int = 0
    errors: List[str] = Field(default_factory=list)


class SupplierPriceQuote(BaseModel):
    """Historical procurement quote from a supplier for a specific SKU."""
    supplier_name: str
    unit_cost: Decimal
    po_id: Optional[str] = None
    order_date: Optional[str] = None


class BomComparisonItem(BaseModel):
    """Detailed price comparison and recommendation for a single BOM item."""
    sku: str
    name: str
    spec: Optional[str] = None
    qty: Decimal
    unit: str = "PCS"
    standard_cost: Decimal = Decimal("0.0")
    quotes: List[SupplierPriceQuote] = Field(default_factory=list)
    lowest_quote: Optional[SupplierPriceQuote] = None
    highest_quote: Optional[SupplierPriceQuote] = None
    estimated_subtotal_lowest: Decimal = Decimal("0.0")
    estimated_subtotal_highest: Decimal = Decimal("0.0")
    potential_savings: Decimal = Decimal("0.0")
    has_history: bool = False


class BomComparisonSummary(BaseModel):
    """Aggregated summary of the entire BOM price comparison."""
    total_skus: int = 0
    total_qty: Decimal = Decimal("0.0")
    total_cost_lowest: Decimal = Decimal("0.0")
    total_cost_highest: Decimal = Decimal("0.0")
    total_cost_standard: Decimal = Decimal("0.0")
    total_potential_savings: Decimal = Decimal("0.0")
    items: List[BomComparisonItem] = Field(default_factory=list)
    unquoted_skus: List[str] = Field(default_factory=list)
