# CLAUDE.md

`AGENTS.md` is the source of truth for how work is done in this repo — API
first, where a feature lives in the UI, the constraints on UI work, URL rules,
tests, and leaving the machine clean. Read it before designing a feature, not
after. Everything in it applies here; this file only adds the pointers a coding
session needs up front.

## Before writing any UI

Read `design-system/AGENTS.md`. Values come from `design-system/tokens/` (the
flattened build is `design-system/dist/amplifier.css`); look anything visual up
in `design-system/guidelines/` before inventing it. The pages in
`design-system/example/` are the shape to copy, and `design-system/ui_kits/` has
working kits for each product surface.

Read **role tokens**, never brand constants — `--amp-interactive-*` and
`--amp-attention-*` rather than `--amp-azure` and `--amp-violet`. The role names
are what flip between the dark and light themes; a component that reaches for a
brand constant is correct in one theme and wrong in the other.

The folder carries its own `SKILL.md`, so it is also invocable as a skill by
name (`amplifier-design`) outside this repo.

`design-system/` is documentation and reference markup, not a runtime
dependency. The dashboard stays a single self-contained page and keeps inlining
its own CSS in `_render_html()` (AGENTS.md §3) — the design system is where the
values and component rules are written down, so they stop being re-derived per
feature.

## Docs worth reading before changing behaviour

- `docs/UI.md` — what the page actually does, section by section
- `docs/API.md` — the endpoints the UI is a client of
- `docs/FEDERATION.md` — peers, pairing, and what crosses node boundaries
