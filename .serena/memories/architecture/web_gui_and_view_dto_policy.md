# Web GUI & View DTO Architecture Decision Record (ADR)

## Context & Product Reality
- Dinkoko ERP is an operational ERP for inventory, orders, and finance. It is NOT a headless-only or CLI-only tool; it must provide a modern Web GUI (Dashboard, single-document workflow, RWD mobile interface) for administrative/warehouse staff.
- LINE Bot is strictly a lightweight customer-facing channel / value-added service, NOT the entire or primary GUI.

## Guardrails & Best Practices
1. **Contract-First via View DTOs**:
   - APIs and query services designed for presentation must return explicit `View DTO` models (carrying pre-aggregated metrics, formatted strings, and status badge metadata), never raw database entities.
2. **Zero-Build SSR Stack**:
   - Web GUI adopts `FastAPI` + `Jinja2` + `HTMX` + `Tailwind CSS` (via CDN).
   - Strictly prohibit heavy JS build chains (Node.js, npm, Webpack, Vite, React/Vue SPA complexity) to preserve sprint velocity and maintain simplicity.
3. **Vertical Slice Delivery**:
   - Deliver UI presentation slices in tandem with domain milestones rather than deferring all GUI work to the final sprint.
