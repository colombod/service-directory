# UI kit — Amplifier application shell

**The starting point for a new Amplifier app.** Not a recreation of an existing
product: the structural pattern borrowed from muxplex (tile overview → pick one
→ list on the left, work on the right), repainted in the palette sampled from
the Amplifier mark.

## The pattern

| State | Layout |
|---|---|
| **Overview** | full-width grid of equal-weight tiles, one per item; filter + sort in the header; nothing selected |
| **Focused** | the same list condensed into a 240px left rail, the selected item's work filling the rest |
| **Agent** | violet-edged right panel over the page, page stays live behind it |

Selection is carried by the tile/row's **left edge bar** turning azure — the bar
is always present, so selecting changes its colour, never the geometry.
Attention ("this item needs you") turns it violet and adds a glow + count.

## What to change when you adopt it

- `data.js` — your items. Each needs `name`, `status`, a one-line `meta`, and a
  `preview` (the item's own content: log tail, diff, output, summary).
- The word "Run" — whatever your app's unit is called.
- Nothing else. The header, rail, tile, detail, agent panel and toast are the
  pattern; keep them.

## Rules this kit demonstrates

- One accent (azure) = interactive. Violet = agent + attention. Green/amber/red
  = status only.
- Flat: nothing in the layout is shadowed. Only the agent panel and the toast are.
- 13px base, 4px radius, 6/8/12/16px spacing, 44px header, 48px touch floor.
- The Amplifier mark at 16px next to the app name in plain type — apps do not
  get their own wordmark unless they earn one.
