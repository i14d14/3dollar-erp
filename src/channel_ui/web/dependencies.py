import os
from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates

from src.channel_ui.line_bot.adapters import MockLineMessagingAdapter, RealLineMessagingAdapter
from src.channel_ui.line_bot.ports import LineMessagingPort
from src.channel_ui.line_bot.service import LineBotService
from src.channel_ui.web.view_service import WebViewService
from src.core.ports.event_bus_port import EventBusPort
from src.core.services.inventory_service import InventoryService
from src.core.services.invoice_service import InvoiceService
from src.core.services.order_service import OrderService
from src.core.services.procurement_service import ProcurementService
from src.extended_core.accounting.services.accounting_service import AccountingService
from src.extended_core.crm.services.crm_service import CrmService
from src.shared.database import Database



def get_db(request: Request) -> Database:
    """Retrieve the application's active Database instance from app.state."""
    return request.app.state.db


def get_event_bus(request: Request) -> EventBusPort:
    """Retrieve the application's active EventBus instance from app.state."""
    return request.app.state.event_bus


def get_templates(request: Request) -> Jinja2Templates:
    """Retrieve Jinja2 templates instance from app.state."""
    return request.app.state.templates


def get_view_service(request: Request) -> WebViewService:
    """Retrieve WebViewService instance from app.state."""
    return request.app.state.view_service


def get_order_service(
    db: Database = Depends(get_db),
    event_bus: EventBusPort = Depends(get_event_bus),
) -> OrderService:
    """Dependency provider for OrderService wired to the active app db and event bus."""
    return OrderService(db=db, event_bus=event_bus)


def get_invoice_service(
    db: Database = Depends(get_db),
    event_bus: EventBusPort = Depends(get_event_bus),
) -> InvoiceService:
    """Dependency provider for InvoiceService wired to the active app db and event bus."""
    return InvoiceService(db=db, event_bus=event_bus)


def get_procurement_service(
    db: Database = Depends(get_db),
    event_bus: EventBusPort = Depends(get_event_bus),
) -> ProcurementService:
    """Dependency provider for ProcurementService wired to the active app db and event bus."""
    return ProcurementService(db=db, event_bus=event_bus)


def get_inventory_service(
    db: Database = Depends(get_db),
) -> InventoryService:
    """Dependency provider for InventoryService wired to the active app db."""
    return InventoryService(db=db)


def get_accounting_service(
    db: Database = Depends(get_db),
) -> AccountingService:
    """Dependency provider for AccountingService wired to the active app db."""
    return AccountingService(db=db)


def get_crm_service(
    db: Database = Depends(get_db),
    order_service: OrderService = Depends(get_order_service),
) -> CrmService:
    """Dependency provider for CrmService wired to the active app db and order service."""
    return CrmService(db=db, order_service=order_service)


def get_line_channel_secret(request: Request) -> str:
    """Retrieve the LINE channel secret from app.state or environment."""
    return getattr(
        request.app.state,
        "line_channel_secret",
        os.environ.get("LINE_CHANNEL_SECRET", "mock_channel_secret"),
    )


def get_line_messaging_port(request: Request) -> LineMessagingPort:
    """Retrieve the active LineMessagingPort from app.state, default to MockLineMessagingAdapter."""
    port = getattr(request.app.state, "line_messaging_port", None)
    if port is None:
        access_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
        channel_id = os.environ.get("LINE_CHANNEL_ID")
        channel_secret = getattr(
            request.app.state,
            "line_channel_secret",
            os.environ.get("LINE_CHANNEL_SECRET"),
        )
        # If user provided access token OR (channel_id + secret), use Real adapter with v3 Stateless Token
        if access_token or (channel_id and channel_secret and channel_secret != "mock_channel_secret"):
            port = RealLineMessagingAdapter(
                channel_access_token=access_token,
                channel_id=channel_id,
                channel_secret=channel_secret,
            )
        else:
            port = MockLineMessagingAdapter()
        request.app.state.line_messaging_port = port
    return port


def get_line_bot_service(
    db: Database = Depends(get_db),
    order_service: OrderService = Depends(get_order_service),
    inventory_service: InventoryService = Depends(get_inventory_service),
    messaging_port: LineMessagingPort = Depends(get_line_messaging_port),
) -> LineBotService:
    """Dependency provider for LineBotService wired to the active app db and services."""
    return LineBotService(
        db=db,
        order_service=order_service,
        inventory_service=inventory_service,
        messaging_port=messaging_port,
    )

