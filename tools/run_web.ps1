# 3Dollar ERP Web GUI Launcher
Write-Host "Launching 3Dollar ERP Web Admin..." -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host "Orders:    http://127.0.0.1:8000/orders" -ForegroundColor Green
Write-Host "Inventory: http://127.0.0.1:8000/inventory" -ForegroundColor Green
Write-Host "OpenAPI:   http://127.0.0.1:8000/docs" -ForegroundColor Green
python -m uvicorn src.channel_ui.web.app:app --reload --port 8000
