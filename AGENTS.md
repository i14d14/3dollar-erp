# Agent Guidelines & Operating Protocols

## 1. Living SSOT & Dual-Verification Protocol (STATUS.md & ROADMAP.md Governance)

All agents working on this project must strictly adhere to the dynamic state tracking and dual-verification protocol:

1. **SSOT Separation of Concerns**:
   - [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md) is the SOLE authoritative source for **Specifications, Architecture Guardrails, and Dual-Track Boundaries (What & How)**. It defines the exact scope of the *Pessimistic MVP Baseline* vs *Optimistic Full Expansion*, architectural ports, and native file access rules.
   - [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) is the SOLE authoritative source for **Operational Execution State (Where & Now)**. It tracks active sprint progress, completion percentages, active blockers, and the verification log. It must NEVER serve as an independent specification.

2. **Mandatory Dual-Check Before Execution (Read Both First)**:
   - Before proposing plans, designing solutions, or executing code for any task:
     a. Inspect [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) to identify the current active sprint, task, and blockers.
     b. Inspect [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md) for that specific task's **Pessimistic MVP Baseline** vs **Optimistic Full Expansion** scope and architectural slots.
     c. Strictly prohibit implementing features solely based on task titles in `STATUS.md` without verifying the boundary definitions in `ROADMAP.md`.

3. **Atomic State Synchronization**:
   - Immediately upon completing and verifying any task or sub-milestone, update [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) in the same turn:
     - Mark the corresponding checkbox as completed (`- [x]`).
     - Re-calculate and update the overall completion percentage.
     - Append a concise entry to the **Verification Log** table with timestamp, milestone, verification summary, and PASS status.

4. **Never Allow Drift**:
   - Working tree changes must never drift ahead of [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md). The file must reflect active operational ground truth at all times.

---

## 2. Architectural Guardrails & 4-Layer Hierarchy

Enforce the 4-layer dependency model defined in [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md):

```
Layer 4: AI Wrapper (Data Intake & Analytics)
   |
Layer 3: Channel & UI (Admin Web Dashboard & LINE Bot Customer Channel)
   |
Layer 2: Extended Core (DanLee CRM & TanJee Accounting)
   |
Layer 1: Core Engine (Dinkoko ERP - Inventory, Orders, Invoicing)
```

### Invariants:
* **Unidirectional Dependency Flow**: Lower layers must NEVER import or depend upon higher layers.
  - Layer 1 (Dinkoko ERP) has zero outgoing dependencies on CRM, Accounting, LINE Bots, or UI.
  - Layer 2 (CRM / Accounting) depends on Layer 1 via domain events or explicit service boundaries.
  - Layer 3 (Admin Web GUI & LINE Bots) interacts with ERP/CRM strictly through public service APIs / View DTOs.
  - Layer 4 (AI Wrappers) acts as non-blocking sidecars or data transformation pipelines.
* **Architecture Fitness Functions**: Run `dependency-cruiser` to continuously enforce layer boundaries and prevent circular dependencies.

---

## 3. Native File Access Protocols

Follow the file access matrix specified in [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md):
* **Excel / CSV**: Use `openpyxl` for reading and manipulating workbooks; use `xlsxwriter` for streaming generation of complex formatted sheets (BOM comparisons, financial statements).
* **PDF**: Use `pymupdf` (`fitz`) for native text-layer extraction (electronic invoices, contracts) and PDF inspection. Do not treat native PDFs as raster images unless image-only OCR is explicitly required.
* **DOCX**: Use `python-docx` for reading Word templates and replacing document variables.

---

## 4. Platform & Tooling Guardrails

* **OS and Shell**: Windows host with Windows PowerShell. Always load [`powershell-docs`](file:///C:/Users/pigmao/.agents/skills/powershell-docs/SKILL.md) before shell operations. Strictly prohibit Linux-specific commands.
* **Encoding**: Explicit UTF-8 across all scripts (`sys.stdout.reconfigure(encoding='utf-8')`). Never redirect via PowerShell 5.1 `>` to prevent UTF-16LE mojibake.
* **Packages and Pip**: Standard library first. Never run `pip install` without explicit user permission.

---

## 5. UI & View Contract Guardrails (Zero-Build SSR & Vertical Slices)

* **Web GUI Is Mandatory**: Dinkoko ERP is an operational ERP requiring visual administration (Web Dashboard, table views, order status progression, mobile RWD). LINE Bot is strictly an external customer touchpoint / value-added channel, NOT a substitute for the internal administrative Web GUI.
* **Contract-First via View DTOs**: Presentation queries and APIs must expose tailored View DTOs (carrying pre-aggregated KPIs, formatted currencies/dates, and visual badge states). Never expose raw database entities directly to views.
* **Zero-Build SSR Architecture**: All Web UI must use Python server-driven rendering (`FastAPI` + `Jinja2` + `HTMX` + `Tailwind CSS` via CDN). Strictly prohibit heavy JavaScript frameworks and build pipelines (`npm`, `webpack`, `vite`, React, Vue) to eliminate environment rot and preserve sprint velocity.
* **Vertical Slice Delivery**: Each domain sprint delivers its business logic and corresponding UI slice in tandem. Strictly prohibit deferring all GUI development to the final sprint.

---

## 6. Web GUI Quick-Launch & Endpoints Operational Reference

Whenever the user asks how to open, view, or launch the ERP Web GUI, immediately provide these exact commands and links:

* **Startup Command** (run from workspace root `d:\3dollar_erp`):
  ```powershell
  python -m uvicorn src.channel_ui.web.app:app --reload --port 8000
  ```
* **Accessible Endpoints**:
  - 營運儀表板 (Executive Dashboard): `http://127.0.0.1:8000/`
  - 訂單與出貨管理 (Orders & Fulfillment): `http://127.0.0.1:8000/orders`
  - 多倉庫存與流水 (Inventory & Stock Ledger): `http://127.0.0.1:8000/inventory`
  - 互動規格文件 (Interactive OpenAPI/Swagger): `http://127.0.0.1:8000/docs`