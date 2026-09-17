# LiLai (哩來) CRM Module
from src.extended_core.crm.models import (
    Contact,
    Deal,
    DealStage,
    Quote,
    QuoteItem,
    QuoteStatus,
)
from src.extended_core.crm.services.crm_service import CrmService

__all__ = [
    "Contact",
    "Deal",
    "DealStage",
    "Quote",
    "QuoteItem",
    "QuoteStatus",
    "CrmService",
]
