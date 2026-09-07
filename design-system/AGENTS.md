# AGENTS.md — Amplifier Design System

Rules for writing UI in this repo. Read before generating markup or CSS.

Where to look things up:

| Question | Look in |
|---|---|
| What is this value / why | `guidelines/*.card.html` (22 cards) |
| The raw values | `tokens/*.css` |
| A component's props + intent | `components/<surface>/<Name>.prompt.md` + `.d.ts` |
| What a whole screen looks like | `example/`, then `ui_kits/` |
| Principles, copywriting, content rules | `README.md` |

## Non-negotiable

1. **Load `dist/amplifier.css` (or `styles.css` + your own component CSS) and set
   `data-brand="amplifier"` on the root element.** Never copy token values into a
   component; reference the variable.
2. **No new numbers.** If a size, colour, radius, duration or z-index is not in
   `tokens/`, it does not exist. Compose from what is there. When you are unsure
   what a value is *for*, open the matching card in `guidelines/` — every token
   family has one.
3. **No new colours.** Azure is interactive, violet is agent/attention,
   green/amber/red are status. That's the whole palette. Never use amber for
   "needs attention" and never use violet for an error.
4. **Flat.** Nothing in the layout carries a shadow. Elevation is earned by
   overlapping other content: only the agent panel, dialogs, menus and the
   toast get `--shadow-*`.
5. **Selection changes colour, not geometry.** The 3px left edge bar on tiles
   and rail rows is always rendered; it goes azure when selected, violet with a
   `--glow-bell` when the item needs attention.
6. **Never signal with colour alone.** Attention is colour + border + inner
   glow + a count. Status text is a word, not just a dot.
7. **48px minimum hit area** (`--touch-min`) for anything clickable, even where
   the visual control is smaller. Header is 44px visual height, not a target.
8. **13px base** (`--text-md`). Never below 11px (`--text-xs`) for text a user
   must read; 10px (`--text-2xs`) is monospace preview only.
9. **Chrome is words, not glyphs.** Toolbar actions use `.amp-link` (azure
   text). `.amp-btn` is for actions that must read as a target; `--primary` is
   at most one per view.
10. **The mark, never a wordmark.** 16px Amplifier icon next to the app name in
    plain type. An app does not get its own logotype.

## Class map

| Need | Class |
|---|---|
| App frame | `.amp-app` > `.amp-header` + `.amp-body` |
| Toolbar action | `.amp-link` |
| Target action | `.amp-btn`, `.amp-btn--primary`, `.amp-btn--agent` |
| Search / filter | `.amp-filter` > `.amp-filter__input` (+ `--wide` in a rail) |
| Overview | `.amp-overview` > `.amp-grid` > `.amp-tile` |
| Focused list | `.amp-rail` > `.amp-rail__head` + `.amp-rail__list` > `.amp-row` |
| Work area | `.amp-detail` > `.amp-detail__head` + `.amp-detail__body` |
| Logs / output / code | `.amp-well` |
| Metadata | `.amp-kv` |
| Grouping box | `.amp-panel` |
| Agent | `.amp-agent` (+ `__head`/`__body`/`__foot`, `.amp-msg--agent`/`--user`) |
| Status word | `.amp-status--ok/warn/err/active/attention` |
| Attention count | `.amp-badge` |
| Confirmation | `.amp-toast` |
| Modal | `.amp-scrim` + `.amp-dialog` |
| Empty state | `.amp-empty` |
| Settings frame | `.amp-settings` > `.amp-tabrail` > `.amp-tab` + `.amp-section` |
| Ordered setup | `.amp-steps` > `.amp-step` (`data-state="done"|"active"`) |
| Form field | `.amp-field` > `.amp-field__label` + `.amp-input` + `.amp-field__hint` |
| Command / config | `.amp-code` (+ `.amp-code__copy`) |
| One-time code | `.amp-token` |
| Caveat that will bite | `.amp-note`, `--warn`, `--err`, `--agent` |
| Verification | `.amp-checks` > `.amp-check` (`data-state="pass"|"fail"`) |
| Peer / log entry | `.amp-peer` (+ `data-self`, `data-unreachable`) |
| Status pill | `.amp-pill`, `--ok`, `--err`, `--agent` |

State is expressed with attributes, not extra classes:
`aria-selected="true"` on a tile or row, `data-attention` on either,
`aria-pressed="true"` on `.amp-btn--agent`.

## Structure to follow

```html
<div class="amp-app">
  <header class="amp-header">
    <img class="amp-header__mark" src="…/amplifier-icon-32.png" alt="Amplifier">
    <span class="amp-header__name">App name</span>
    <button class="amp-link">Sort ▾</button>
    <div class="amp-filter"><input class="amp-filter__input" placeholder="Filter"></div>
    <div class="amp-header__spacer"></div>
    <button class="amp-btn amp-btn--agent" aria-pressed="false">Agent</button>
  </header>
  <div class="amp-body">
    <!-- overview:  <div class="amp-overview"><div class="amp-grid">…tiles…</div></div> -->
    <!-- focused:   <nav class="amp-rail">…rows…</nav><section class="amp-detail">…</section> -->
  </div>
</div>
```

Three states, one app: overview → focused → agent. Do not invent a fourth
navigation level; nest inside `.amp-detail__body` instead.

## Setup and management pages

Federation, agent integration, node identity and lifecycle are **sections of
Settings**, reached from the lateral `.amp-tabrail` — never new top-level pages,
never on the landing page. Both shipped setup pages follow the same four-part
shape and yours should too:

1. **A subhead that says what the feature is for**, and one `.amp-note` naming
   the thing that will bite (write token required; this node has no dependency
   on Amplifier).
2. **`.amp-steps`** in the order a person actually works: config → issue →
   redeem → verify. Mark completed steps `data-state="done"`, the current one
   `data-state="active"`.
3. **Copyable truth.** Config and commands go in `.amp-code` with a copy
   control; resolved values (URL, token, cert state) go in an `.amp-kv` the
   user copies from rather than retypes.
4. **`.amp-checks` — verification of observable state.** A handshake returning
   200 is not success. Each check is a claim the user can confirm, and a failed
   check says what is actually wrong, not "error".

Absent optional data renders as an em dash with a `.amp-note` explaining that
the dash is correct. Never show a spinner for something that will never arrive.

## Content rules

- Status is one lowercase word (`running`, `idle`, `failed`) — not a sentence.
- A tile shows: name, status, one-line summary, the item's own content
  (log tail / diff / output) in the well, and one footer chip.
- Empty states say what would be there and why it isn't. No illustrations.
- No emoji. No icon fonts. `▾` `←` `×` as text glyphs are fine.

## Accessibility floor

Text ≥ 4.5:1 against its background. `--amp-ink` (16.8:1) and
`--amp-ink-muted` (6.4:1) both pass on `--amp-page`; `--amp-ink-dim` does not
and is decorative only — never the sole carrier of meaning. Keep
`:focus-visible` visible; `--focus-ring` is defined for you.
`prefers-reduced-motion` is already honoured in the components file — do not
re-implement it.
