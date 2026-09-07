# UI kit — muxplex (web app)

A recreation of the muxplex dashboard: dense session grid, 200px session rail,
header quick controls, settings modal, and the Amplifier Agent panel.

Source of truth: `bkrabach/muxplex@main` —
`muxplex/frontend/index.html`, `muxplex/frontend/style.css`,
`muxplex/frontend/tokens.css`, `docs/DESIGN_LANGUAGE.md`.

## Screens / states

| State | What it shows |
|---|---|
| Grid (default) | session tiles, bell tile, device tags, filter + sort + view controls |
| Session open | one session expanded to the full view, floating return pill, rail highlight |
| Settings | modal over the page (backdrop 299 / dialog 300) |
| Agent panel | right-side panel at `--z-panel`, text on the page (no chat bubbles) |
| Rail collapsed | sidebar width 0, grid reflows |

## Fidelity notes

- Tiles are 300px tall with a 3px left edge bar that is always present.
- Bell state = amber border + inner glow + pulsing count badge, never colour alone.
- Nothing in the layout is shadowed. Only the pill, menu, modal and panel are.
- The screens inline the same values the primitives in `components/muxplex_*` use;
  the kit is a browser-runnable recreation, not a bundler consumer.
