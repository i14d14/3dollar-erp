# How to Run the 3Dollar ERP Web GUI

## Startup Command
Run from workspace root (`d:\3dollar_erp`):
```powershell
python -m uvicorn src.channel_ui.web.app:app --reload --port 8000
```
Or execute the helper script:
```powershell
.\tools\run_web.ps1
```

## Key URLs
- Executive Dashboard: `http://127.0.0.1:8000/`
- Orders & Fulfillment: `http://127.0.0.1:8000/orders`
- Multi-Warehouse Inventory: `http://127.0.0.1:8000/inventory`
- Interactive OpenAPI Specs: `http://127.0.0.1:8000/docs`

## Stack
- Zero-Build SSR: FastAPI + Jinja2 + HTMX (1.9 CDN) + Tailwind CSS (CDN).
- View DTOs: `src.channel_ui.web.dtos` and `src.channel_ui.web.view_service`.
