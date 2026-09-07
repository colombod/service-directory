# CLAUDE.md

`AGENTS.md` is the source of truth for how work is done in this repo — API
first, where a feature lives in the UI, the constraints on UI work, URL rules,
tests, and leaving the machine clean. Read it before designing a feature, not
after. Everything in it applies here; this file only adds the pointers a coding
session needs up front.

## Before writing any UI

Read `design-system/AGENTS.md`. Use the `.amp-*` classes and the tokens; don't
invent colours or sizes. The pages in `design-system/example/` are the shape to
copy.

`design-system/` is documentation and reference markup, not a runtime
dependency. The dashboard stays a single self-contained page and keeps inlining
its own CSS in `_render_html()` (AGENTS.md §3) — the design system is where the
values and component rules are written down, so they stop being re-derived per
feature.

## Docs worth reading before changing behaviour

- `docs/UI.md` — what the page actually does, section by section
- `docs/API.md` — the endpoints the UI is a client of
- `docs/FEDERATION.md` — peers, pairing, and what crosses node boundaries
