---
paths:
  - "app/templates/**/*.html"
  - "app/static/css/**/*.css"
---
# Frontend, CSS & HTMX Standards

## Semantic CSS Design Tokens
- Never introduce external CSS frameworks (Tailwind, Bootstrap). Stick strictly to hand-crafted, semantic CSS utilizing the custom properties defined in `:root` inside `app/static/css/style.css`.
- Maintain the two-pane workspace grid and scroll isolation (`overflow: hidden` on viewport wrappers, scrolling delegated strictly to `.stream-container` and overview drawers).

## HTMX Partial Conventions
- Ensure dynamic list updates, search filters, and drawer inspections leverage server-rendered HTML fragments (partials) swapped via `hx-get`, `hx-target`, and `hx-swap="innerHTML"`.
- Preserve accessibility indicators such as `:focus-visible` outlines and keyboard navigable `<article class="result-row" tabindex="0">` elements.