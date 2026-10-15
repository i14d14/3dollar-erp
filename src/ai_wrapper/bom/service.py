# Re-export from Core Services (Layer 1) for backward compatibility
from src.core.services.bom_service import BomComparisonService

__all__ = ["BomComparisonService"]
