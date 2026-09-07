# UI kit — App registry, on the Amplifier application rules

**A proposal, not a recreation.** `colombod/service-directory` rebuilt on the
Amplifier visual rules: muxplex's structural pattern (tile overview → pick one →
list on the left, work on the right) in the palette sampled from the Amplifier
mark.

Compare with `ui_kits/service_directory/` — the same product as it ships today
(light-first, blue #3355d1, table rail, no tile view).

## What carried over from the real app

Every behaviour, unchanged: catalogue grouped by origin node, an unreachable
peer contributing no section, health starting at `unknown`, in-app opening as
the **default** action with external links as an explicit new-tab option,
`view_kind` dispatch (`iframe` / `json` / `auto` → probe), the can't-embed
fallback with its verbatim reason, static rows having no remove control, and
Settings owning node identity / peers / pairing behind a write token.

## What changed

| Today | Here | Why |
|---|---|---|
| table rail only | tile overview first, rail on selection | a registry's first question is "what is on this host?" — tiles answer it at a glance |
| light-first, dual mode | Amplifier dark, navy-tinted | one ecosystem ground; the mark sits on its own colour family |
| accent #3355d1 | `--amp-azure` #08B0F8 | one interactive colour across every Amplifier app |
| `unknown` grey pill | violet edge + count when a service **needs you** | attention is the mark's third ring, distinct from "down" (`--amp-err`) |
| Settings as a right sheet | Settings as a modal | it takes over; a panel is for surfaces the page stays live behind |

## Open question for the team

Registry health is a **fleet** status, not an attention state. Here, "needs you"
means an operator action is pending (a dynamic service whose TTL is expiring, a
peer awaiting pairing). If that framing is wrong, the violet channel should go
back to being purely the agent's colour.
