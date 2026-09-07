# Conventions for this repo

Rules that govern every change here — for humans and for agents (including
Resolve-driven work). Read this before designing a feature, not after.

## 1. API first — always

**Every capability lands as a documented JSON endpoint before, or alongside, any
UI that uses it.** The UI is a client of the API, never the only way to do
something.

Concretely, a feature is not complete if:

- the UI can do something the API cannot,
- an agent or script would have to scrape HTML or drive a browser to accomplish
  it, or
- the endpoint exists but is undocumented in the README.

This repo has two first-class consumers and they are equal citizens:

| Consumer | Reaches the system via |
|---|---|
| A person | the single server-rendered page |
| An agent / script / another node | the JSON API + the CLI |

Federation is the proof case: peers talk to each other over the API. Anything
the UI can do that the API cannot is invisible to the rest of the fleet.

**Checklist for any new capability**

- [ ] JSON endpoint exists, with success *and* failure shapes
- [ ] Reads follow existing read-access rules
- [ ] **Every mutation requires the existing write token** and returns the
      existing error shape on failure — no new unauthenticated mutation path
- [ ] Documented in the README with a real, runnable example
- [ ] Hermetic test covers the success path and the auth-failure path

## 2. Decide where it lives in the UI — deliberately

Having an API is necessary, not sufficient. For every feature, decide and record
*where a person encounters it*. The answer is one of:

1. **The catalogue / viewer** — it is about seeing or using a *service*.
2. **Settings / management** — it is about configuring *this node*, its
   federation, its peers, or its lifecycle (status, version, upgrade).
3. **Deliberately API-only** — say so explicitly, with the reason.

"I'll add the UI later" is not one of the options. If a capability is reachable
only by CLI, that is a usability defect, and it gets filed as one.

The precedent: node identity, federation, pairing and peer management were
CLI-only for their whole first life. Pairing two nodes by hand took three CLI
invocations across two machines, an environment variable, and a non-default
port — while the web UI showed no hint any of it existed. That is exactly the
failure this rule prevents.

**Settings is the home for node/fleet management.** It uses a *lateral* (left,
vertical) tab rail — macOS System Settings shaped — with the selected section
rendered beside it. New management surfaces become a section there rather than a
new top-level page.

## 3. Constraints that apply to all UI work

- **Single self-contained page.** All CSS/JS inline. No build step, no CDN, no
  npm, no external assets. Plain inline JS.
- **Match the existing design system** — same tokens, spacing, and type scale as
  `_render_html`. The values and the component rules are written down in
  `design-system/` (start with `design-system/AGENTS.md`); the reference pages
  in `design-system/example/` are the shape to copy. It must read as one
  product.
- **Preserve existing DOM hooks** that JS and tests depend on: `service-filter`,
  `section.node-group[data-origin]`, `tr.service[data-name]`/`[data-search]`,
  `[data-view-url]`/`[data-view-kind]`, `svc-table`, `health-pill`/`health-dot`,
  `add-service-form`, `write-token-input`, `remove-service`,
  `.service-name.service-open`.
- **Opening a service in-app is the default action**; opening externally is an
  explicit option (`target="_blank"`), never the only affordance.

## 4. URLs: tailnet-DNS-first, and HTTPS must match the page

Every URL rendered as clickable or embedded prefers the **Tailscale DNS name**,
so any device on the tailnet can open it.

**If the dashboard is served over HTTPS, every `view_url` and link must be HTTPS
too.** An `http://` URL inside an HTTPS page is mixed content: the browser
blocks it, the iframe silently renders nothing, and it looks like a layout bug
rather than a blocked resource. This has been introduced twice — once for local
services and again for federated ones — because the rule lived in reviewers'
heads instead of in validation. Prefer failing loudly at config-load over
shipping a blank pane.

## 5. Tests

- Hermetic: no real network, no real peer, no real clock. Stub them.
- `filterwarnings=error::DeprecationWarning` — the suite stays warning-clean.
- New work is **additive**: every existing test passes UNCHANGED.
- A test asserting a bug is fixed must **fail against the pre-fix code**.

## 6. Don't leave the machine dirty

Any preview server, port, tailscale serve, or temp config created while
verifying is torn down before the work is called done.
