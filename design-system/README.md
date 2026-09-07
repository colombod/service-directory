# Amplifier Design System

The shared visual language for Amplifier ecosystem applications. Two CSS files,
no build step, no dependencies, no framework assumptions.

## Install

```html
<html lang="en" data-brand="amplifier">
  <link rel="stylesheet" href="/amplifier-design-system/amplifier.css">
```

`data-brand="amplifier"` is the opt-in. Without it the tokens are defined but
nothing is remapped, so the file is safe to load next to existing styles
(including muxplex's own, which keeps its cyan accent).

- `amplifier.tokens.css` — every value: colour, space, radius, type, control
  metrics, motion, elevation, z-index ladder, layout constants.
- `amplifier.components.css` — the shell primitives as `.amp-*` classes.
- `amplifier.css` — imports both. Use this one.
- `example/` — one design page per part of the product, static, no framework.
  These are the reference implementations; copy markup out of them.

  | Page | Part it designs |
  |---|---|
  | `example/index.html` | Catalogue / work surface: tile overview, focused rail + detail, agent panel |
  | `example/federation-setup.html` | Federation (multi-device): enable, issue code, redeem, verify, trusted peers |
  | `example/agent-integration.html` | Amplifier agent integration: bundle install, the three config values, TLS trust, verification |
- `AGENTS.md` — the rules, written for a coding agent. Read it before writing UI.

## Where the colours come from

Sampled from the pixels of the Amplifier mark — deep navy `#002880`, mid blue
`#0060E0`, azure `#08B0F8`, violet `#5018D0`. No fourth hue was invented.

| Role | Token | Rule |
|---|---|---|
| Interactive | `--amp-azure` | The one accent. Links, selection, focus. |
| Pressed / held | `--amp-blue` | The active state of azure, nothing else. |
| Agent + attention | `--amp-violet` | Agent presence, and "this item needs you". |
| Surfaces | `--amp-page/raised/hover` | Navy-tinted so the mark sits on its own family. |
| Status | `--amp-ok/warn/err` | Green/amber/red. Status only, never decoration. |

## Two shapes, not one

**Work surfaces** use the overview → focused → agent pattern below.
**Setup and management surfaces** (federation, agent integration, node identity,
lifecycle) live in Settings behind a lateral tab rail, and are built from
`.amp-steps` / `.amp-field` / `.amp-code` / `.amp-note` / `.amp-checks`. A new
management capability becomes a section in that rail — never a new top-level page.

Every setup page ends in **verification the user can read**: a checklist of
claims about observable state, not a green "success" banner for a handshake that
proves less than it appears to.

## The layout pattern

Overview (tile grid) → focused (240px rail + detail) → agent (violet-edged
right panel over a live page). Selection is carried by a 3px left edge bar that
is always present: state changes its colour, never the geometry.

## Versioning

`v1.0.0`. Values are generated from the upstream design-system project; edit
them there and re-export rather than patching this copy.
