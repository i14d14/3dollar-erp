# Re-export from Core Services (Layer 1) for backward compatibility
from src.core.services.bom_parser import BomExcelParser

__all__ = ["BomExcelParser"]
