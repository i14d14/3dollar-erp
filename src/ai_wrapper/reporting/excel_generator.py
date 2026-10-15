# Re-export from Extended Core (Layer 2: TanGii Accounting) for backward compatibility
from src.extended_core.accounting.services.excel_report_generator import AdvancedReportGenerator

__all__ = ["AdvancedReportGenerator"]
