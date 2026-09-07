# User Interface Guide

The dashboard is one server-rendered page (`_render_html()` in
`src/service_directory/app.py`) — no build step, no client-side framework.
This guide covers what a user sees and can do, purely from the rendered
markup and inline JS already shipped.

## 1. Layout: catalogue + viewer

The page is a two-pane workspace:

- **Left (sidebar)**: the catalogue, grouped into one
  `<section class="node-group" data-origin="...">` per origin node. Each
  section has its own `<table class="svc-table">` listing that node's
  services (columns: Service, Description, Status, Address, Info). A node
  only ever appears if it is currently reachable — an unreachable peer
  contributes no section at all (see `docs/ARCHITECTURE.md` §4).
- **Right (viewer)**: empty/catalogue-summary by default; shows a selected
  service's detail view, then (on "Open here") the embedded content.

A collapse button (`#sidebar-collapse-btn`) toggles the sidebar's
`data-collapsed` attribute for a wider viewer pane.

## 2. Filtering

The `#service-filter` text input filters rows client-side: it matches
against each row's `data-search` attribute (name + description + origin +
tags, lowercased) OR the section's `data-origin`. A node-group section
hides itself entirely if none of its rows match. There is no server round
trip — filtering is instant and purely in the already-rendered DOM.

## 3. Opening a service

Every service row's name is a real `<button class="service-name
service-open">`, not inert text — clicking it (or clicking anywhere else on
the row that isn't itself a link/button) opens that service's **detail
view** in the right-hand pane: description, category, tags, current health
label, a documentation link (if `docs_url` is set), links to open the
service **externally** (`target="_blank"`, one per configured host address),
and an **"Open here"** button.

**Opening a service in-app is the default action.** External links
(`class="link-btn"` in the row, and the "Open externally" links in the
detail view) are always `target="_blank"` — an explicit, secondary option a
user chooses, never the only way to reach a service.

Clicking "Open here" calls `openServiceInViewer(name, url, kind,
refreshSecs)`, which dispatches on the service's `view_kind` (see §4).

If a service has no resolvable `view_url` and no primary link at all, the
detail view shows "No in-app view configured for this service" instead of
an "Open here" button.

## 4. Viewer modes (`view_kind`)

Configured per service in YAML (`view_kind: "auto"|"iframe"|"json"`,
defaults to `"auto"` when omitted). This is the single field that controls
what happens when a user clicks "Open here".

### `iframe` — embed directly, no probe

Renders the service directly inside an `<iframe>` in the viewer pane, with
a Reload button and an "open in new tab" link. **No probe is performed** —
the URL is embedded unconditionally.

**Choose `iframe` when**: the service is a real HTML app AND either (a) it
does not send `X-Frame-Options`/blocking CSP, or (b) it's fine to try
embedding it regardless. **This is the only mode that works reliably for a
service that requires a login** — see the `auto` caveat below.

### `json` — fetch and render as a JSON tree

Fetches the URL through `GET /api/view-proxy` (server-side, avoiding CORS)
and renders the parsed body as a collapsible JSON tree (plain inline JS, no
libraries). Provides a manual "Refresh" button, an "Auto-refresh: on/off"
toggle, and an "updated Ns ago" indicator.

`view_refresh_seconds` (a positive integer in config) sets the auto-refresh
interval and starts it automatically the first time the JSON view opens for
that service; the toggle button lets the user turn it off/back on for the
current session. Only meaningful for `json`-kind (and `auto`-kind services
that resolve to JSON) — the field is silently ignored otherwise.

**Choose `json` when**: the service exposes a JSON status/health endpoint
rather than an HTML UI (e.g. a `/status` endpoint), and set `view_url` to
that specific endpoint if it differs from the service's primary link.

### `auto` — probe first, then decide

Calls `GET /api/embed-probe?url=<view_url>` first:

- If the probe reports `reachable: false` → shows the fallback pane
  ("Service is unreachable.").
- Else if `content_type` contains `application/json` → fetches via
  `/api/view-proxy` and renders as JSON (same as `json`-kind).
- Else if `embeddable: false` (an `X-Frame-Options` header or a
  `frame-ancestors` CSP directive was present) → shows the fallback pane
  ("This service cannot be embedded (X-Frame-Options or CSP
  frame-ancestors).").
- Else → embeds as an iframe (same as `iframe`-kind).

**`auto` is strictly less capable than `iframe` for anything behind a
login.** The probe is an unauthenticated `HEAD` request; an app that
redirects an unauthenticated caller to a login page (a `3xx` response) is
reported by `/api/embed-probe` as **`reachable: false`** (see
`docs/API.md`'s known limitation for `/api/embed-probe`) — so `auto` will
ALWAYS show the "unreachable" fallback for such a service, even though a
logged-in human could embed it fine. **Pin `view_kind: "iframe"` explicitly
for any service that sits behind auth** — leaving it on `auto` (or omitting
`view_kind`) means it can never be opened in-app.

## 5. Services that cannot be embedded

When the viewer decides a service cannot be shown in-page — either because
`auto`'s probe reported `embeddable: false`/`reachable: false`, or because a
`json`/`auto` fetch through `/api/view-proxy` failed — it shows a fallback
card: a short reason (e.g. "This service cannot be embedded
(X-Frame-Options or CSP frame-ancestors)." or "Service is unreachable.") and
an **"Open <name> in a new tab ↗"** link (`target="_blank"`). The user is
never left with a dead end — opening externally is always offered as the
explicit fallback action, consistent with external links being an option
everywhere else in the UI.

## 6. Health status

Each row shows a health pill (`.health-pill` / `.health-dot`, states
`unknown`/`up`/`down`) that starts as `unknown` and is filled in
client-side by a `fetch('/api/health')` call on page load (no per-row
polling; one batched request for the whole catalogue).

## 7. Removing dynamic services from the dashboard

A dynamic row gets a × remove button (`.remove-service`,
`data-remove-name="<name>"`) that calls `DELETE
/api/services/{name}`. The request attaches the `write-token-input` field's
value (see §8) as `Authorization: Bearer <token>` when non-empty (see §8) — a static
service never gets a remove button, matching the API's read-only rule for
static entries. Removing a service refreshes the sidebar catalogue in
place — no page reload.

Registering a NEW service is an administrative action and lives in
**Settings** (§8's "Register Service" section), not on the landing page.


## 8. Settings

Opened via the `#settings-btn` button, which shows the `#settings-overlay`
panel. Reads live from the API on open (`loadSettings()`):

- **Write Token** (`#write-token-input`): a password-type input the user
  pastes the shared write token into. It is stored only in the DOM/session
  — every mutating fetch in the page (add/remove service, remove peer,
  issue pairing code, pair with peer) reads this field and adds
  `Authorization: Bearer <value>` when non-empty. **Every mutation in the
  Settings panel (and the catalogue's add/remove-service actions) requires
  this token** unless the browser happens to be running on the node itself
  (`127.0.0.1`), in which case the server's localhost bypass applies
  regardless of what's typed here.
- **Register Service** (`#add-service-form`): posts `name`, `port`,
  `description`, `category`, `health_url` to `POST /api/services`. This is
  an administrative action (AGENTS.md §2), so it lives here rather than on
  the landing page. On success the sidebar catalogue refreshes in place —
  no page reload — and the new service is immediately visible/openable
  from the catalogue. Errors (missing/invalid write token, validation
  failures) render into `#add-service-error` beside the form.
- **Node Identity** (`#settings-identity-section`): renders `GET
  /api/settings` — name, an "enabled"/"disabled" federation badge,
  description, role, base URL, and host addresses, whichever are present.
- **Trusted Peers** (`#settings-peers-section`): renders `GET
  /api/federation/peers` — each peer's name, base URL, and a
  reachable/unknown badge, with a `×` button (`.settings-remove-peer-btn`)
  that calls `DELETE /api/federation/peers/{name}` (write-token gated).
- **Pairing** (`#settings-pairing-section`): only shown when
  `federation_enabled` is true (hidden via inline `style.display` from
  `renderIdentity()`). Two independent actions:
  - **"Issue pairing code"** button → `POST
    /api/federation/ui-pairing-code` (write-token gated) → shows the code
    and its expiry ("Expires in 600s (one-time use)").
  - **"Pair with peer"** form (peer base URL + code) → `POST
    /api/federation/pair-with-peer` (write-token gated) → on success shows
    "Paired with `<name>` (`<base_url>`)" and reloads the peers list.

Settings is read-only until a write token is supplied for anything that
mutates state — this matches AGENTS.md's rule that Settings is the home for
node/fleet management, and that every mutation needs the existing write
token.

Settings sections are designed against `design-system/example/` — federation
setup and Amplifier agent integration each have a reference page there, both
following the same shape: steps in working order, copyable config, and a
verification checklist of observable state rather than a success banner.
