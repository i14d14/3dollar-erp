from __future__ import annotations
import json
from typing import Any, Dict, Optional, Union
from fastapi.templating import Jinja2Templates
from starlette.requests import Request


def render_toast_oob(
    templates: Jinja2Templates,
    request: Request,
    message: str,
    type: str = "success",
    undo_url: Optional[str] = None,
    undo_label: str = "撤回",
    undo_target: Optional[str] = None,
    undo_select: Optional[str] = None,
    undo_swap: str = "outerHTML",
    undo_vals: Optional[Union[Dict[str, Any], str]] = None,
    ttl_seconds: int = 6,
) -> str:
    """Render a standardized toast notification card wrapped in an HTMX OOB container.

    Args:
        templates: Active Jinja2Templates instance.
        request: Current HTTP Request.
        message: Traditional Chinese notification text.
        type: "success" | "error" | "info".
        undo_url: Optional URL endpoint to trigger when the Undo button is clicked.
        undo_label: Display text for undo button (default "撤回").
        undo_target: Target DOM selector to receive undo response.
        undo_swap: HTMX swap strategy for undo response (default "outerHTML").
        undo_vals: Optional dict or JSON string payload for hx-vals.
        ttl_seconds: Time-To-Live in seconds for the countdown progress bar (default 6).

    Returns:
        HTML string wrapped in <div id="toast-container" hx-swap-oob="innerHTML:#toast-container">...</div>.
    """
    if isinstance(undo_vals, dict):
        undo_vals_str = json.dumps(undo_vals, ensure_ascii=False)
    else:
        undo_vals_str = undo_vals

    toast_html = templates.get_template("partials/toast_notification.html").render({
        "request": request,
        "type": type,
        "message": message,
        "undo_url": undo_url,
        "undo_label": undo_label,
        "undo_target": undo_target,
        "undo_select": undo_select,
        "undo_swap": undo_swap,
        "undo_vals": undo_vals_str,
        "ttl_seconds": ttl_seconds,
    })

    return f'<div id="toast-container" hx-swap-oob="innerHTML:#toast-container">{toast_html.strip()}</div>'
