# Amplifier ecosystem design system

> **This folder is the complete design system**, exported from the design-system
> project. Layout is preserved, so every relative link in the guideline cards
> and UI kits works when opened directly in a browser — no build step, no
> server, no dependencies.

## What is where

| Path | What it is |
|---|---|
| `SKILL.md` | Skill front-matter. Drop this folder into `~/.claude/skills/` and it is invocable by name. |
| `AGENTS.md` | **Read first for UI work.** The rules, the class map, and the shape every setup page follows. |
| `styles.css` | Source entry point — `@import`s every token file. What the guideline cards load. |
| `tokens/*.css` | The values: colour, space, radius, type, elevation, layers, control metrics, motion, layout, and `amplifier-app.css` (the new-app palette). |
| `products/service-directory.css` | Service Directory's own scoped palette. Deliberately not merged. |
| `dist/amplifier.css` | Flattened single-file build (tokens + `.amp-*` components) for dropping into an app. Generated — edit `tokens/` and re-export. |
| `guidelines/*.card.html` | 22 reference cards: brand usage, colour families, type, shape, layers, motion, control metrics, and the Amplifier app palette/shell/surfaces/states. |
| `components/` | Component primitives as real files — `.jsx` + `.d.ts` + `.prompt.md` each, grouped by product surface. |
| `ui_kits/` | Four interactive kits: muxplex, Service Directory, the generic Amplifier app shell, and the registry restyled on Amplifier rules. |
| `example/` | One static design page per part: catalogue/viewer, federation (multi-device) setup, Amplifier agent integration. |
| `assets/` | Brand assets — wordmark, lockups, icons, favicons, OG, and the Amplifier mark. |

## Using it in a coding session

```
Read AGENTS.md before writing any UI. Values come from tokens/ (or dist/amplifier.css
if you want one file). Look up anything visual in guidelines/ before inventing it.
The pages in example/ are the shape to copy.
```

## Opt-in for a new app

```html
<html lang="en" data-brand="amplifier">
  <link rel="stylesheet" href="/design-system/dist/amplifier.css">
```

Without `data-brand="amplifier"` the tokens are defined but nothing is remapped,
so the file is safe to load beside existing styles — muxplex keeps its cyan.

---

The shared design language for apps built in the **Amplifier** ecosystem — a
system that uses AI to build other systems. This project is compiled from the
two real Amplifier apps the team has shipped, and is meant to be the place a
designer or agent looks up a value *before* inventing one.

## Sources

| Source | What was taken from it |
|---|---|
| `github.com/bkrabach/muxplex` (`main`) | **The canonical brand and UI system.** `muxplex/frontend/tokens.css` (every token value), `muxplex/frontend/style.css` (component rules), `docs/DESIGN_LANGUAGE.md` (principles, component vocabulary), `assets/branding/` (all brand assets) |
| `github.com/colombod/service-directory` (`main`) | The second product surface: `src/service_directory/app.py` (`_render_html()`'s inline CSS + markup), `docs/UI.md`, `AGENTS.md`, `config.sample.yaml` |
| `github.com/microsoft/amplifier-app-resolve` | **Not accessible** to the import tools or by fetch. Nothing here is derived from it. Referenced by name only (Resolve appears as a registered service). |

Nothing in this system was recreated from a screenshot; every value comes from
source code.

## The two products

**muxplex** — a dense monitoring tool for tmux sessions across devices, with a
web PWA, a federation layer, an embedded terminal, and an Amplifier Agent panel.
Dark-only, cyan accent, flat, extremely dense. This is the brand.

**Service Directory** — a tiny config-driven service registry for one host: a
single server-rendered page listing the other services on the machine, with an
in-app viewer and node federation. Light-first with a dual-mode palette, blue
accent, no build step, no external assets. Its palette is deliberately kept
scoped (`products/service-directory.css`) rather than merged.

They are **different products sharing an ecosystem**, not one product. Do not
reconcile their palettes; do reconcile their principles.

---

## Content fundamentals

How the Amplifier apps write, taken from their own UI strings and docs.

- **Plain, declarative, lower-case-leaning.** Labels are nouns: `Filter`,
  `Sort`, `Write Token`, `Trusted Peers`, `Pairing`. Buttons are verbs:
  `Open here`, `Add service`, `Issue pairing code`, `Pair with peer`.
- **Sentence case in prose, Title Case for section headings**, UPPERCASE only
  as a *style* on small section labels (never typed in caps).
- **Second person, sparingly.** "Pick a service to open it here — without
  leaving the directory." Never "Let's get started", never "Oops".
- **State the mechanism.** Errors and empty states say what actually happened:
  "This service cannot be embedded (X-Frame-Options or CSP frame-ancestors)."
  "Service is unreachable." "Expires in 600s (one-time use)." A reason is
  quoted verbatim, not softened into "Something went wrong".
- **Never claim an unobserved state.** A peer that could not be reached is
  `unknown`, never `down`; health starts at `unknown` and is filled in after
  the fetch.
- **Hints are parenthetical and technical**: "(required for remote/tailnet
  writes, or when the node enforces one on localhost)".
- **No emoji in chrome.** The one emoji in either product is a per-service
  `icon` field a *user* sets in their own YAML (`icon: "🎬"`). Do not add emoji
  to UI copy.
- **No marketing voice, no exclamation marks, no "powerful"/"seamless".** The
  strongest claim either app makes about itself is "dense monitoring tool".
- **Units and identifiers are exact**: `3w · 2m`, `0.1.0`, `updated 14s ago`,
  `100.111.191.22:8080`. Monospace carries anything a user might copy.

---

## Visual foundations

### Colour
One accent, three text tiers, four signal colours — and that is the entire
palette. `--accent` (#00D9F5) means "this is interactive" and nothing else.
`--ok` / `--warn` / `--err` / `--bell` mean status and never decorate a
surface. A filled coloured surface is a *claim that the thing inside it has a
state*; if you cannot say in one clause what a fill means, remove it.
Surfaces are a three-step luminance ladder (#0D1117 → #10131C → #1A1F2B).

### Type
No webfont is loaded by either app. `system-ui` for chrome, `SF Mono` for
terminal content and anything copyable. Urbanist 700 exists **only inside the
brand wordmark SVGs** — never as UI type. The real base size is 13px, and
13/12/11px account for two-thirds of all declarations. Half-pixel sizes in
Service Directory (10.5 / 12.5 / 13.5px) are intentional; do not round them.

### Spacing and density
Density is the product, not a compromise. 6px between related items, 8px
between components (and as the grid gap), 12px inside a panel, 16px at the
page margin, 24px only between unrelated regions. Not a strict 4px grid — 6px
is the app's real unit and the scale keeps it honest.

### Backgrounds and imagery
Flat colour only. No gradients, no photography, no illustration, no texture,
no pattern. The one image asset in the running UI is the Amplifier mark at
16px. Where "content" appears it is someone else's monospace output on pure
black (#000000) — the interface is chrome around a terminal.

### Elevation, borders, radii
Nine box-shadows in 4,077 lines of CSS, every one on something that overlaps
other content. **Elevation is earned by overlap, never by grouping.** Anything
that sits *in* the layout is flat and separated by a 1px `--border`. Radii:
4px for essentially everything, 8px for menus and dialogs, 12px for mobile
sheets, 999px for pills. Cards are a 1px border and a 4px radius — no shadow,
no accent left-border decoration (the 3px left edge bar on a tile is a *state*
channel, not ornament).

### Hover, focus, press
Hover changes a **border colour** (`--border` → `--accent`) or an **ink colour**
(`--text-muted` → `--text`, `--accent` → `--accent-hover`); it does not move,
scale, or shadow anything. Focus-visible gets `2px solid --accent` at 2px
offset — and the same colour change as hover, so tabbing looks like hovering.
Press is not a separate treatment. Service Directory's primary button hovers
at `opacity: .9`; its inputs focus with a 3px `--accent-weak` ring.

### Motion
150ms for hover/focus/colour, 200ms to appear or disappear, 250ms for a tile
expanding or a sheet rising. Two keyframe animations ship in total:
`bell-pulse` (1.4s, infinite — the only looping motion) and `sheet-up`.
Motion confirms a state change; it never performs.

### Transparency and blur
Almost none, deliberately. `--bg-overlay` (85% black) for a scrim, and
`--accent-dim` / `--bell-glow` as low-alpha state fills. **No backdrop-filter
anywhere**: the device tag over a live terminal is fully opaque *by
construction*, because a translucent chip's contrast becomes a function of
whatever pixels are underneath it.

### Layout
Fixed 44px header. 200px session rail (muxplex) / 340px catalogue rail
(Service Directory), both collapsible to 0. Grid of
`minmax(360px, 1fr)` tiles at 300px tall. Stacking follows a measured z-index
ladder (1 / 10 / 50 / 100 / 200 / 299 / 300 / 310 / 500) — never a fresh
integer. 48×48 CSS px is the touch-target floor and is not negotiable.

---

## Amplifier application rules

The two shipped apps are what they are. **This section is what a NEW Amplifier
app should be** — muxplex's structure, the Amplifier mark's colour.

### 1. The palette comes from the mark
`tokens/amplifier-app.css`, sampled by pixel count from
`assets/amplifier/amplifier-icon-48.png`: deep navy `#002880`, mid blue
`#0060E0`, bright azure `#08B0F8`, violet `#5018D0`. Surfaces are a
navy-tinted three-step ladder (`#0A0E18` → `#101728` → `#18213A`) so the mark
sits on its own colour family instead of on neutral grey. An app opts in with
`data-brand="amplifier"` on its root element.

### 2. Three colour channels, and only three
- **Azure = interactive.** One accent. Links, selection edges, the single
  primary button on a surface. Hover → `--amp-azure-hover`; held →
  `--amp-azure-dim` fill with an azure border.
- **Violet = the agent, and "this needs you".** It is the mark's third ring, so
  attention stays inside the brand instead of borrowing muxplex's amber — and it
  stays distinct from `--amp-err` ("this is broken") and `--amp-warn`.
- **Green / amber / red = status only**, shared verbatim with muxplex so a
  status reads identically across the ecosystem.

If you cannot say in one clause what a colour *means* on a surface, remove it.

### 3. The shell: overview → focus
Every Amplifier app is a list of things you supervise, so every Amplifier app
has the same two states:

1. **Overview** — a full-width grid of equal-weight tiles,
   `repeat(auto-fill, minmax(320px, 1fr))`, one tile per item, grouped by
   whatever the app's natural grouping is (host, device, owner, node). Density
   is the feature: the first question is "what is here, and does any of it need
   me?", and the tile answers it without a click.
2. **Focused** — selecting a tile collapses the list into a 240–260px left rail
   (same items, same order, same edge colours) and gives the rest of the width
   to the selected item's work.

The rail is never a second navigation model: it is the overview, condensed.
"← All items" in the header is the only way back, and it is a link, not a button.

### 4. Selection and attention live in the left edge bar
Every tile and every rail row carries a **3px left border at all times**.
`--amp-line` at rest, `--amp-azure` when hovered or selected, `--amp-violet`
plus a glow and a count badge when the item needs a human. Selection therefore
changes a colour, never a geometry — nothing shifts, resizes, or lifts.

### 5. Structure inherited from muxplex, unchanged
44px header · 4px radius on everything (8px on menus and dialogs, 12px on
mobile sheets) · 6/8/12/16/24px spacing · 13px base type · flat by default,
with a shadow only on things that overlap live content · the measured z-index
ladder · 150/200/250ms motion · 48×48 touch floor. Read
"Visual foundations" above; none of it changes for an Amplifier app.

### 6. Identity: the mark plus the app's name in plain type
The Amplifier mark at 16×16, then the app name at 13px/600. **An app does not
get its own wordmark** unless it has earned one the way muxplex did. The agent
affordance is the same mark plus the word "Agent", and the agent panel is a
violet-edged panel over a page that stays live behind it — never a modal, never
a chat-app header inside your app.

### 7. Chrome is words
View, sort and filter controls are azure text, not glyph buttons. The only
bordered controls are the agent button and the one primary action on a surface.
A glyph appears only where a word cannot fit (`×`, `←`, `▾`, `●`, `↗`).

---

## Iconography

- **Almost no icons.** Both apps are text-first: chrome is words
  (`View ▾`, `Sort ▾`, `+ New session`, `Open here`), not glyphs.
- **No icon font, no sprite sheet, no icon library** in either codebase.
  There is nothing to import, and adding a set would be an invention.
- **Where a glyph is needed, it is a Unicode character in the UI font**:
  `☰` menu, `×` (U+00D7) close/remove, `«` `»` collapse/expand, `▾` disclosure,
  `●` status dot, `↗` external link, `⚙` settings, `+` / `−` (U+2212) panel
  toggle, `—` (U+2014) description separator, `#` tag prefix.
- **Two inline SVGs exist, both as CSS masks, not elements**: the search
  magnifier in the filter field and the panel-layout glyph in the viewer's
  welcome state. Both are stroke-only, `stroke-width: 2` / `1.8`, round caps,
  painted with `background` so they inherit a token colour.
- **The Amplifier mark is the one real image asset** — see below.
- **Emoji**: never in chrome. Only as a user-supplied per-service `icon` value.
- If you need an icon that does not exist here, **ask** rather than importing a
  library; the correct answer is usually a word.

### The Amplifier mark
`assets/amplifier/amplifier-icon-32.png` (and `-48`) is the ecosystem's shared
identity asset: interlocking blue/cyan rings. It appears at **16×16** in front
of the word "Agent" in the header and in the "Powered by Amplifier Agent"
byline. There is **one** logo asset, not a second one — never redraw it,
recolour it, or generate a variant. Any Amplifier app that wants to signal it
is Amplifier-powered uses this exact file.

### muxplex brand assets
Wordmark, icon and lockup ship as SVG sources with rendered PNGs
(`assets/branding/`). The wordmark sets **Urbanist 700** with "mux" in
#F0F6FF and "plex" in #00D9F5. Light-surface variants exist for each.
**Service Directory has no logo or mark of any kind** — it renders the words
"Service Directory" at 17px/650. Do not invent one for it.

---

## Index

| Path | What it is |
|---|---|
| `styles.css` | the entry point — `@import`s only |
| `tokens/` | `color`, `space`, `radius`, `type`, `elevation`, `layer`, `control`, `motion`, `layout` |
| `products/service-directory.css` | the second product's scoped palette |
| `guidelines/` | 18 foundation specimen cards (colour, type, space, shape, brand) |
| `components/muxplex_core/` | QuickLink, HeaderButton, FilterInput, Field, Surface, Badge |
| `components/muxplex_session/` | SessionTile, SidebarItem, DeviceHeader, SessionPill, FilterPill |
| `components/muxplex_overlay/` | Toast, Menu, Modal, BottomSheet |
| `components/directory_core/` | Button, TextInput, Disclosure, EmptyState (Service Directory) |
| `components/catalogue/` | NodeGroup, ServiceTable, ServiceRow, HealthPill, CategoryChip, TagList, ReachableBadge, AddressLink |
| `components/viewer/` | ViewerWelcome, ViewerHeader, ViewerFallback, ServiceDetail, JsonTree |
| `components/settings/` | SettingsPanel, SettingsSection, KeyValueList, PeerItem, PairingCode |
| `tokens/amplifier-app.css` | **the palette for new Amplifier apps**, sampled from the mark |
| `ui_kits/amplifier_app/` | **the Amplifier app shell** — start new apps here |
| `ui_kits/registry_amplifier/` | the app registry restyled on the Amplifier rules (proposal) |
| `ui_kits/muxplex/` | interactive recreation: grid, rail, session view, settings, agent panel |
| `ui_kits/service_directory/` | interactive recreation: catalogue, detail, iframe/JSON viewer, settings |
| `assets/branding/` | muxplex wordmark, icon, lockup (SVG + PNG), favicons, OG |
| `assets/amplifier/` | the Amplifier mark |
| `github.md` | source repo association and screen map |
| `SKILL.md` | Agent Skills entry point |

### Intentional additions

Both codebases are CSS-only — they define no React components — so every
component here is a faithful port of an existing CSS rule + markup shape, named
after `DESIGN_LANGUAGE.md`'s own seven-component vocabulary (Surface, Quick
link, Menu, Field, Badge, Panel, Modal). Two wrappers have no single rule
behind them and are called out as additions:

- **`Surface`** — the vocabulary names it; the CSS expresses it inline on
  tiles, rails and panels.
- **`Field`** — likewise: label + control + helper, with the documented
  spacing, rather than a class in `style.css`.

Nothing else was invented: there is no Avatar, Tabs, Tooltip, Accordion or
DatePicker here, because neither product has one.

### Known gaps

- `muxplex/frontend/deck/` (the "soft deck" surface, its own responsive spec
  and 56px header) is not covered here.
- Login (`login.html`) and setup pages are not recreated.
- `--warning` / `--danger` are read by `style.css` but defined nowhere
  upstream; two different reds ship under one name. Use `--warn` / `--err`.
