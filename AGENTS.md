# Agent Guidelines & Operating Protocols

## 1. Living SSOT & Dual-Verification Protocol (STATUS.md & ROADMAP.md Governance)

All agents working on this project must strictly adhere to the dynamic state tracking and dual-verification protocol:

1. **SSOT Separation of Concerns**:
   - [`README.md`](file:///d:/3dollar_erp/README.md) is the SOLE authoritative source for **Project Onboarding, Quick Start, and Operational User Manual (How to Run & Use)**. It contains service startup commands, URL routes, manual workflow instructions, and verification procedures.
   - [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md) is the SOLE authoritative source for **Specifications, Architecture Guardrails, and Dual-Track Boundaries (What & How)**. It defines the exact scope of the *Youth Edition MVP Baseline (青春版)* vs *Optimistic Full Expansion*, architectural ports, and native file access rules.
   - [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) is the SOLE authoritative source for **Operational Execution State (Where & Now)**. It tracks active sprint progress, completion percentages, active blockers, and the verification log. It must NEVER serve as an independent specification.

2. **Mandatory Dual-Check Before Execution (Read Both First)**:
   - Before proposing plans, designing solutions, or executing code for any task:
     a. Inspect [`STATUS.md`](file:///d:/3dollar_erp/STATUS.md) to identify the current active sprint, task, and blockers.
     b. Inspect [`ROADMAP.md`](file:///d:/3dollar_erp/ROADMAP.md) for that specific task's **Youth Edition MVP Baseline (青春版)** vs **Optimistic Full Expansion** scope and architectural slots.
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
Layer 2: Extended Core (LiLai CRM & TanGii Accounting)
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
* **User-Facing Error Messages & I18n Protocol (Strict Traditional Chinese for UI/Toasts)**:
  - Every error message presented to human operators via HTMX (`#toast-container`, OOB swap banners, form feedback, and `HTTPException.detail` passed to the view) MUST be authored in professional Traditional Chinese (繁體中文).
  - Strictly prohibit raw internal English exception traces and uncaught English domain errors from leaking directly to the UI.
  - Implement a Two-Tier Defense:
    1. *Tier 1 (Domain Services)*: Service exceptions intended for client display should formulate their human-readable message in Traditional Chinese (retaining technical IDs like SKU, Order ID, Warehouse ID).
    2. *Tier 2 (Web Layer / Exception Handler)*: The web exception handler (`app.py`) serves as an automated safety net, normalizing and translating any domain/system exception before injecting it into the toast banner.
* **Browser Autofill Heuristics Acceptance**: Browser autofill behavior (e.g., Chromium/Edge contact suggestions for name, email, phone) is explicitly accepted as standard browser behavior. Do NOT implement complex workarounds (such as `readonly` toggles, fake inputs, or listeners) unless the user explicitly requests to revisit autofill. If browser autofill triggers inappropriately, ignore it until explicitly instructed otherwise.

---

## 6. Interactive Verification & User Testing Protocol (Action -> Expected Outcome)

Whenever reporting newly added features for manual verification or guiding the user through step-by-step testing:
* **Mandatory Action $\rightarrow$ Expected Structure**: Every test scenario or feature item must strictly follow the paired format:
  - **Action (動作)**: Concrete operational step to perform (target page/tab, button clicked, form inputs, sample payload).
  - **Expected Outcome (預期)**: Concrete visual, data, or system reaction (UI badge update, toast/banner, PDF/Excel stream download, database reflection).
* Strictly prohibit listing feature names or summaries without the explicit paired Action $\rightarrow$ Expected Outcome breakdown.