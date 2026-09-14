# Project Manual & How-to-Use SSOT

## Authoritative Location
- [`README.md`](file:///d:/3dollar_erp/README.md) is the project's authoritative **User Manual and Quick Start Guide** (How to Run & Use).
- When any agent or user needs to know:
  1. How to run the local ERP server (`python -m uvicorn src.channel_ui.web.app:app --reload --port 8000`)
  2. The Web GUI URLs (`/`, `/orders`, `/inventory`, `/docs`)
  3. How to perform business workflows (confirm orders, ship with DO, issue MIG 3.2.1 invoices, download label/invoice PDFs, transfer stock)
  4. How to execute tests (`python -m unittest discover -s tests`)
  Direct them to [`README.md`](file:///d:/3dollar_erp/README.md).

## SSOT Division of Responsibilities
- [`README.md`](file:///d:/3dollar_erp/README.md): How to Run & Use (User Manual)
- [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md): What & How to Build (Specs & Boundaries)
- [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md): Where & Now (Execution Progress & Verification Log)
- [`AGENTS.md`](file:///d:/3dollar_erp/AGENTS.md): Agent Operating Rules & Guardrails
