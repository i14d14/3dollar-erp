# Re-export from Core Engine (Layer 1) for backward compatibility
from src.core.domain.bom import (
    BomComparisonItem,
    BomComparisonSummary,
    BomItem,
    BomParseResult,
    SupplierPriceQuote,
)

__all__ = [
    "BomItem",
    "BomParseResult",
    "SupplierPriceQuote",
    "BomComparisonItem",
    "BomComparisonSummary",
]
