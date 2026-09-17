# User-Facing Error Messages & I18n Protocol (Strict Traditional Chinese for UI/Toasts)

## Rule & Governance
1. **Mandatory Traditional Chinese (繁體中文) for UI**:
   - Every error message presented to human operators via HTMX (`#toast-container`, OOB swap banners, form feedback, and `HTTPException.detail` passed to the view) MUST be authored in professional Traditional Chinese (繁體中文).
   - Strictly prohibit raw internal English exception traces and uncaught English domain errors from leaking directly to the UI.

2. **Two-Tier Defense Architecture**:
   - **Tier 1 (Domain Services)**:
     - Service exceptions intended for client display should formulate their human-readable message in Traditional Chinese (retaining technical IDs like SKU, Order ID, Warehouse ID).
   - **Tier 2 (Web Layer / Exception Handler in `app.py`)**:
     - The web exception handler (`app.py`) serves as an automated safety net, normalizing and translating any domain/system exception before injecting it into the toast banner.
