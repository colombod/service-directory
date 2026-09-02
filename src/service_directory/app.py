"""FastAPI app: GET /, GET /api/services, GET /api/services/local,
GET /api/health, plus Block 2 federation endpoints (instance-info, pairing
handshake) and the federation catalogue additions (GET /api/federation/nodes,
richer per-service metadata, dashboard grouping/search/health-dots).

Also the DYNAMIC SERVICE REGISTRY additions: services now come from the
static, read-only YAML ``services:`` baseline UNION a runtime registry
persisted to ``registry.json`` (agents write via POST/DELETE
/api/services[/{name}], a human manages the same store from the dashboard
form). Every catalogue entry is tagged ``source: "static"|"dynamic"``. Every
mutating registry endpoint requires authorization (write token or, unless
``federation.require_write_token`` is set, the localhost bypass) -- see
``auth.require_write_access``.
"""

from __future__ import annotations

import html as html_escape
import secrets
import socket
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import __version__
from .auth import require_admin, require_read_access, require_write_access
from .config import (
    ConfigError,
    RegistryConfig,
    is_safe_docs_url,
    load_config,
    resolve_state_dir,
)
from .federation import (
    DEFAULT_PEER_TIMEOUT_SECONDS,
    FEDERATION_HOP_HEADER,
    AggregationResult,
    PeerFetcher,
    aggregate_services,
    default_peer_fetcher,
)
from .health import (
    Checker,
    HttpChecker,
    check_service_entries,
    default_checker,
    default_http_checker,
)
from .identity import load_or_create_identity
from .pairing import PairingCodeStore
from .registry import (
    DynamicService,
    deregister_service,
    heartbeat_service,
    load_registry,
    register_service,
)
from .trust_store import PeerRecord, load_peers, upsert_peer
from .urls import resolve_all


def _local_name(config: RegistryConfig) -> str:
    if config.federation.name:
        return config.federation.name
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover - defensive
        return "local"


def _service_card_html(svc: dict) -> str:
    name = html_escape.escape(svc["name"])
    desc = svc.get("description") or ""
    desc_html = ""
    if desc:
        desc_html = f'<p class="description">{html_escape.escape(desc)}</p>'
    category_html = ""
    if svc.get("category"):
        category_html = (
            f'<span class="category">{html_escape.escape(svc["category"])}</span>'
        )
    tags = svc.get("tags") or []
    tags_str = " ".join(tags)
    tags_html = ""
    if tags:
        tags_html = (
            '<div class="tags">'
            + "".join(f'<span class="tag">{html_escape.escape(t)}</span>' for t in tags)
            + "</div>"
        )
    icon_html = ""
    if svc.get("icon"):
        icon_html = f'<span class="icon">{html_escape.escape(svc["icon"])}</span>'
    owner_html = ""
    if svc.get("owner"):
        owner_html = (
            f'<span class="owner">owner: {html_escape.escape(svc["owner"])}</span>'
        )
    # Defense in depth: docs_url can arrive not just from local config
    # (already validated in config.py) but also relayed verbatim from a
    # federated peer's /api/services/local response (see federation.py
    # aggregate_services), which never passes through that parser. Only
    # ever render it as a clickable link if it's an allow-listed http(s)
    # scheme -- otherwise drop the link but keep the rest of the card intact.
    docs_html = ""
    docs_url = svc.get("docs_url")
    if docs_url and is_safe_docs_url(docs_url):
        docs_html = (
            f'<a class="docs" href="{html_escape.escape(docs_url)}">docs &rarr;</a>'
        )
    origin = svc.get("origin") or ""
    # Defense in depth: a resolved link's URL can arrive not just from
    # local, admin-controlled config but also from a caller-supplied
    # dynamic registration ("url"/"port" fields, see _dynamic_service_json)
    # or relayed verbatim from a federated peer. Apply the SAME allow-listed
    # http(s)-scheme check used for docs_url before ever rendering a link as
    # a clickable href -- otherwise a stored `javascript:`-scheme value
    # would execute in the dashboard origin when clicked. Drop the
    # individual unsafe link but keep the rest of the card intact.
    #
    # The FIRST safe link (tailnet-first per host_addresses order) is styled
    # as the primary filled button; every subsequent one is a secondary
    # outline button -- purely visual (class names only), the href/label
    # content and ordering are untouched.
    safe_links = [link for link in svc["links"] if is_safe_docs_url(link["url"])]
    link_buttons = []
    for i, link in enumerate(safe_links):
        variant = "link-btn-primary" if i == 0 else "link-btn-secondary"
        link_buttons.append(
            f'<a class="link-btn {variant}" href="{html_escape.escape(link["url"])}">'
            f"{html_escape.escape(link['label'])}</a>"
        )
    links_html = "".join(link_buttons)
    search_blob = html_escape.escape(
        " ".join([svc["name"], desc, origin, tags_str]).lower()
    )
    # Dynamic (agent/human-registered) entries are removable from the
    # dashboard; static (YAML-declared) entries are read-only and show no
    # control. The raw (un-escaped) name is embedded in a data attribute
    # consumed only by the inline JS DELETE handler -- html.escape() still
    # protects it from breaking out of the attribute (same XSS posture as
    # every other data-* attribute on this card).
    remove_html = ""
    if svc.get("source") == "dynamic":
        remove_html = (
            f'<button type="button" class="remove-service" '
            f'data-remove-name="{name}" title="Remove {name}">&times;</button>'
        )
    meta_html = ""
    if owner_html or docs_html:
        meta_html = f'<div class="meta">{owner_html}{docs_html}</div>'
    return (
        f'<li class="service card" data-name="{name}" data-search="{search_blob}">'
        f"{remove_html}"
        f'<div class="card-top">'
        f"{icon_html}"
        f'<h3 class="service-name">{name}</h3>'
        f"</div>"
        f'<div class="card-badges">'
        f"{category_html}"
        f'<span class="health-pill unknown" data-health-name="{name}">'
        f'<span class="health-dot" data-health-name="{name}">&#9679;</span>'
        f'<span class="health-label">unknown</span>'
        f"</span>"
        f"</div>"
        f"{desc_html}"
        f"{tags_html}"
        f'<div class="links">{links_html}</div>'
        f"{meta_html}"
        f"</li>"
    )


def _render_html(services: list[dict], node_info: list[dict] | None = None) -> str:
    """Render the single self-contained dashboard page.

    Services are grouped BY ORIGIN NODE (a section per node, header = node
    name + description when known, plus a reachable badge -- every group
    rendered here is, by construction, reachable: unreachable peers
    contribute zero entries, see federation.aggregate_services). A plain
    inline-JS search/filter input filters cards by name/description/tag/
    origin. A health pill per service is rendered in a neutral "unknown"
    state and updated client-side from /api/health -- no build step, no
    external/CDN assets. Single self-contained page: all CSS/JS is inline.
    """
    node_info = node_info or []
    node_descriptions = {n["name"]: n.get("description") for n in node_info}
    node_roles = {n["name"]: n.get("role") for n in node_info}

    local_name = node_info[0]["name"] if node_info else ""
    local_description = node_descriptions.get(local_name)
    local_role = node_roles.get(local_name)

    identity_bits = [
        f'<span class="node-chip-name">{html_escape.escape(local_name)}</span>'
    ]
    if local_role:
        identity_bits.append(
            f'<span class="node-chip-role">{html_escape.escape(local_role)}</span>'
        )
    identity_html = "".join(identity_bits)
    subtitle_html = ""
    if local_description:
        subtitle_html = (
            '<p class="node-chip-description">'
            f"{html_escape.escape(local_description)}</p>"
        )

    # Group services by origin, preserving first-seen order of nodes.
    grouped: dict[str, list[dict]] = {}
    for svc in services:
        origin = svc.get("origin") or ""
        grouped.setdefault(origin, []).append(svc)

    sections = []
    for origin, group in grouped.items():
        origin_name = html_escape.escape(origin) if origin else "unknown"
        desc = node_descriptions.get(origin)
        desc_html = ""
        if desc and origin != local_name:
            desc_html = f'<p class="node-description">{html_escape.escape(desc)}</p>'
        cards = "\n".join(_service_card_html(svc) for svc in group)
        # By construction every group present here came either from the
        # local node or from a peer whose fetch already succeeded (see
        # federation.aggregate_services -- unreachable peers contribute no
        # entries at all), so the badge is always "reachable" for any
        # section that actually renders.
        sections.append(
            f'<section class="node-group" data-origin="{origin_name}">'
            '<div class="node-group-header">'
            f"<h2>{origin_name}</h2>"
            '<span class="reachable-badge reachable">reachable</span>'
            "</div>"
            f"{desc_html}"
            f'<ul class="services card-grid">{cards}</ul>'
            f"</section>"
        )
    body = "\n".join(sections)

    empty_state_html = ""
    if not services:
        empty_state_html = (
            '<div class="empty-state">'
            '<p class="empty-state-title">No services registered yet</p>'
            '<p class="empty-state-hint">Add one below, or check back once '
            "a peer node or dynamic registration comes online.</p>"
            "</div>"
        )

    script = """
<script>
(function () {
  var input = document.getElementById('service-filter');
  var cards = document.querySelectorAll('li.service');
  var sections = document.querySelectorAll('section.node-group');

  function applyFilter() {
    var q = (input.value || '').toLowerCase();
    sections.forEach(function (section) {
      var visibleCount = 0;
      section.querySelectorAll('li.service').forEach(function (card) {
        var haystack = card.getAttribute('data-search') || '';
        var origin = section.getAttribute('data-origin') || '';
        var match = q === '' || haystack.indexOf(q) !== -1 ||
          origin.toLowerCase().indexOf(q) !== -1;
        card.style.display = match ? '' : 'none';
        if (match) visibleCount += 1;
      });
      section.style.display = visibleCount > 0 ? '' : 'none';
    });
  }

  if (input) {
    input.addEventListener('input', applyFilter);
  }

  function updateHealth() {
    fetch('/api/health').then(function (resp) {
      return resp.json();
    }).then(function (data) {
      cards.forEach(function (card) {
        var name = card.getAttribute('data-name');
        var dot = card.querySelector('.health-dot');
        var pill = card.querySelector('.health-pill');
        var label = card.querySelector('.health-label');
        var raw = data[name];
        var status = raw === 'up' ? 'up' : (raw === 'down' ? 'down' : 'unknown');
        if (dot) dot.className = 'health-dot ' + status;
        if (pill) pill.className = 'health-pill ' + status;
        if (label) label.textContent = status;
      });
    }).catch(function () {
      // Best-effort only -- health is a progressive enhancement, never
      // blocks rendering of the page itself.
    });
  }

  updateHealth();

  function tokenHeaders() {
    var tokenInput = document.getElementById('write-token-input');
    var token = tokenInput ? (tokenInput.value || '').trim() : '';
    var headers = {'Content-Type': 'application/json'};
    if (token) {
      headers['Authorization'] = 'Bearer ' + token;
    }
    return headers;
  }

  var addForm = document.getElementById('add-service-form');
  var addError = document.getElementById('add-service-error');
  if (addForm) {
    addForm.addEventListener('submit', function (event) {
      event.preventDefault();
      if (addError) addError.textContent = '';
      var formData = new FormData(addForm);
      var body = {
        name: formData.get('name'),
        port: parseInt(formData.get('port'), 10),
        description: formData.get('description') || null,
        category: formData.get('category') || null,
        health_url: formData.get('health_url') || null
      };
      fetch('/api/services', {
        method: 'POST',
        headers: tokenHeaders(),
        body: JSON.stringify(body)
      }).then(function (resp) {
        if (!resp.ok) {
          return resp.json().catch(function () { return {}; }).then(function (data) {
            throw new Error((data && data.detail) || ('request failed: ' + resp.status));
          });
        }
        return resp.json();
      }).then(function () {
        window.location.reload();
      }).catch(function (err) {
        if (addError) addError.textContent = String(err.message || err);
      });
    });
  }

  document.querySelectorAll('.remove-service').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-remove-name');
      if (!name) return;
      fetch('/api/services/' + encodeURIComponent(name), {
        method: 'DELETE',
        headers: tokenHeaders()
      }).then(function (resp) {
        if (!resp.ok) {
          throw new Error('remove failed: ' + resp.status);
        }
        window.location.reload();
      }).catch(function (err) {
        window.alert(String(err.message || err));
      });
    });
  });
})();
</script>
"""

    style = """
<style>
:root {
  color-scheme: light dark;
  --bg: #f3f4f6;
  --surface: #ffffff;
  --surface-2: #f7f8fa;
  --border: #e4e7ec;
  --border-strong: #d0d5dd;
  --text: #131720;
  --text-muted: #475467;
  --text-faint: #667085;
  --accent: #4f46e5;
  --accent-hover: #4338ca;
  --accent-soft: #ecebfe;
  --accent-text: #ffffff;
  --up: #16a34a;   --up-soft: #e6f6ec;
  --down: #dc2626; --down-soft: #fdeaea;
  --unknown: #98a2b3; --unknown-soft: #eef0f2;
  --radius: 12px; --radius-sm: 8px; --radius-pill: 999px;
  --shadow-sm: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.07);
  --shadow-md: 0 6px 16px rgba(16,24,40,.09), 0 2px 6px rgba(16,24,40,.05);
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
  --space-5: 24px; --space-6: 32px; --space-7: 48px;
  --maxw: 1180px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1016; --surface: #161a21; --surface-2: #1c212a;
    --border: #262c37; --border-strong: #343c49;
    --text: #e8ebf0; --text-muted: #a3adbb; --text-faint: #8a94a3;
    --accent: #8079ff; --accent-hover: #948dff; --accent-soft: #22243a;
    --up: #34d399; --up-soft: #10261c; --down: #f87171; --down-soft: #2a1414;
    --unknown: #6b7280; --unknown-soft: #1f232b;
    --shadow-sm: 0 1px 2px rgba(0,0,0,.4);
    --shadow-md: 0 6px 18px rgba(0,0,0,.5);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text); line-height: 1.5;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial,
    "Apple Color Emoji", "Segoe UI Emoji", sans-serif;
  -webkit-font-smoothing: antialiased;
}
a { color: inherit; text-decoration: none; }
::placeholder { color: var(--text-faint); opacity: 1; }
.page { max-width: var(--maxw); margin: 0 auto; padding: 0 var(--space-5) var(--space-7); }

.header-band {
  position: sticky; top: 0; z-index: 20;
  background: color-mix(in srgb, var(--bg) 85%, transparent);
  -webkit-backdrop-filter: saturate(160%) blur(10px);
  backdrop-filter: saturate(160%) blur(10px);
  border-bottom: 1px solid var(--border);
  padding: var(--space-4) var(--space-5);
  margin: 0 calc(-1 * var(--space-5)) var(--space-6);
}
.header-top { display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-4); flex-wrap: wrap; }
.brand { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -.02em;
  display: flex; align-items: center; gap: var(--space-3); }
.brand::before { content: ""; width: 22px; height: 22px; border-radius: 7px;
  background: linear-gradient(135deg, var(--accent), #a855f7);
  box-shadow: 0 2px 8px rgba(79,70,229,.4); }
.node-chip { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-pill);
  padding: 6px 8px 6px 14px; box-shadow: var(--shadow-sm); }
.node-chip-name { font-weight: 600; font-size: 13px; }
.node-chip-role { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--accent); background: var(--accent-soft); padding: 3px 9px; border-radius: var(--radius-pill); }
.node-chip-description { margin: 0; width: 100%; font-size: 12px; color: var(--text-muted); }
.search-bar { margin-top: var(--space-4); position: relative; }
.search-bar::before { content: ""; position: absolute; left: 14px; top: 50%; transform: translateY(-50%);
  width: 16px; height: 16px; pointer-events: none; background: var(--text-faint);
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E") center/contain no-repeat;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E") center/contain no-repeat; }
#service-filter { width: 100%; padding: 11px 14px 11px 42px; font-size: 14px; color: var(--text);
  border: 1px solid var(--border-strong); border-radius: var(--radius-sm);
  background: var(--surface); box-shadow: var(--shadow-sm);
  transition: border-color .15s, box-shadow .15s; }
#service-filter:focus { outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft); }

.node-group { margin-bottom: var(--space-7); }
.node-group-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); }
.node-group-header h2 { margin: 0; font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
.reachable-badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: var(--radius-pill);
  display: inline-flex; align-items: center; gap: 6px; }
.reachable-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.reachable-badge.reachable { color: var(--up); background: var(--up-soft); }
.node-description { margin: 0 0 var(--space-4); color: var(--text-muted); font-size: 13px; }

.card-grid { list-style: none; margin: 0; padding: 0; display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); align-items: start; }

.service.card { position: relative; background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius); padding: var(--space-5); box-shadow: var(--shadow-sm);
  display: flex; flex-direction: column; gap: var(--space-3);
  transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease; }
.service.card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); border-color: var(--border-strong); }
.card-top { display: flex; align-items: center; gap: var(--space-3); padding-right: 26px; }
.icon { font-size: 20px; line-height: 1; width: 42px; height: 42px; flex: none;
  display: grid; place-items: center; border-radius: 11px;
  background: var(--surface-2); border: 1px solid var(--border); }
.service-name { margin: 0; font-size: 16px; font-weight: 650; letter-spacing: -.01em; word-break: break-word; }
.card-badges { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
.category { font-size: 11px; font-weight: 600; color: var(--accent);
  background: var(--accent-soft); border: 1px solid transparent; padding: 3px 10px; border-radius: var(--radius-pill); }
.health-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
  padding: 3px 10px; border-radius: var(--radius-pill); text-transform: capitalize; }
.health-pill .health-dot { font-size: 8px; line-height: 1; }
.health-pill.up { color: var(--up); background: var(--up-soft); }
.health-pill.down { color: var(--down); background: var(--down-soft); }
.health-pill.unknown { color: var(--unknown); background: var(--unknown-soft); }
.description { margin: 0; font-size: 13px; color: var(--text-muted); }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { font-size: 11px; color: var(--text-muted); background: var(--surface-2);
  border: 1px solid var(--border); padding: 2px 9px; border-radius: var(--radius-pill); }
.tag::before { content: "#"; opacity: .45; }
.links { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-top: auto; padding-top: var(--space-2); }
.link-btn { font-size: 13px; font-weight: 600; padding: 8px 14px; border-radius: var(--radius-sm);
  display: inline-flex; align-items: center; gap: 6px; transition: background .15s, border-color .15s, color .15s, transform .1s; }
.link-btn:active { transform: translateY(1px); }
.link-btn-primary { background: var(--accent); color: var(--accent-text); box-shadow: 0 1px 2px rgba(79,70,229,.3); }
.link-btn-primary:hover { background: var(--accent-hover); }
.link-btn-secondary { background: transparent; color: var(--text-muted); border: 1px solid var(--border-strong); }
.link-btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
.meta { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3);
  margin-top: var(--space-1); padding-top: var(--space-3); border-top: 1px solid var(--border);
  font-size: 12px; color: var(--text-faint); }
.docs { color: var(--accent); font-weight: 600; }
.docs:hover { text-decoration: underline; }
.remove-service { position: absolute; top: 12px; right: 12px; width: 26px; height: 26px;
  border: none; border-radius: 8px; background: transparent; color: var(--text-faint);
  font-size: 18px; line-height: 1; cursor: pointer; display: grid; place-items: center;
  transition: background .15s, color .15s; }
.remove-service:hover { background: var(--down-soft); color: var(--down); }

.empty-state { text-align: center; padding: var(--space-7) var(--space-4); color: var(--text-muted);
  border: 1px dashed var(--border-strong); border-radius: var(--radius); background: var(--surface-2); }
.empty-state-title { font-size: 16px; font-weight: 600; color: var(--text); margin: 0 0 var(--space-2); }
.empty-state-hint { margin: 0; font-size: 13px; }

.registration-panel { margin-top: var(--space-6); background: var(--surface-2);
  border: 1px solid var(--border); border-radius: var(--radius); padding: var(--space-5); }
.registration-panel .panel-title { margin: 0 0 var(--space-2); font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
.registration-panel > .panel-title + .write-token-row { margin-top: var(--space-3); }
.add-service-form h2 { display: none; }
.write-token-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: var(--space-4);
  padding-bottom: var(--space-4); border-bottom: 1px dashed var(--border-strong); }
.write-token-row label { font-size: 12px; color: var(--text-muted); }
#write-token-input, .add-service-form input { width: 100%; padding: 11px 14px; font-size: 14px;
  color: var(--text); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); background: var(--surface); }
#write-token-input:focus, .add-service-form input:focus { outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft); }
.add-service-form { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: var(--space-3); }
.add-service-form h2 { grid-column: 1 / -1; }
.add-service-form button { padding: 10px 20px; font-size: 13px; font-weight: 600; border: none;
  border-radius: var(--radius-sm); background: var(--accent); color: var(--accent-text); cursor: pointer; transition: background .15s; }
.add-service-form button:hover { background: var(--accent-hover); }
.add-service-error { grid-column: 1 / -1; color: var(--down); font-size: 12px; min-height: 1em; }

@media (max-width: 640px) {
  .header-band { padding: var(--space-4); margin: 0 calc(-1 * var(--space-5)) var(--space-5); }
  .card-grid { grid-template-columns: 1fr; }
}
.write-token-row .hint { color: var(--text-faint); font-weight: 400; }
</style>
"""

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Service Directory</title>"
        f"{style}"
        "</head>"
        '<body><div class="page">'
        '<header class="header-band">'
        '<div class="header-top">'
        '<h1 class="brand">Service Directory</h1>'
        f'<div class="node-chip">{identity_html}{subtitle_html}</div>'
        "</div>"
        '<div class="search-bar">'
        '<input type="text" id="service-filter" '
        'aria-label="Filter services by name, description, tag, or origin" '
        'placeholder="Filter by name, description, tag, or origin\u2026" />'
        "</div>"
        "</header>"
        '<main class="content">'
        f"{body}"
        f"{empty_state_html}"
        "</main>"
        '<section class="registration-panel">'
        '<h2 class="panel-title">Register a service</h2>'
        '<div class="write-token-row">'
        '<label for="write-token-input">Write token <span class="hint">(required for remote/tailnet writes, or when the node enforces one on localhost)</span></label> '
        '<input type="password" id="write-token-input" '
        'placeholder="Bearer write token (optional on localhost)" />'
        "</div>"
        '<form id="add-service-form" class="add-service-form">'
        "<h2>Add service</h2>"
        '<input type="text" name="name" placeholder="Name" required />'
        '<input type="number" name="port" placeholder="Port" required />'
        '<input type="text" name="description" placeholder="Description" />'
        '<input type="text" name="category" placeholder="Category" />'
        '<input type="text" name="health_url" placeholder="Health URL (optional)" />'
        '<button type="submit">Add service</button>'
        '<span id="add-service-error" class="add-service-error"></span>'
        "</form>"
        "</section>"
        "</div>"
        f"{script}"
        "</body></html>"
    )


def _local_services_json(config: RegistryConfig) -> list[dict]:
    """The STATIC, YAML-declared services only -- always tagged
    ``source: "static"`` so the merged catalogue can distinguish them from
    dynamically-registered entries.
    """
    resolved = resolve_all(config)
    return [
        {
            "name": svc.name,
            "description": svc.description,
            "links": [
                {"label": link.label, "host": link.host, "url": link.url}
                for link in svc.links
            ],
            "category": svc.category,
            "tags": list(svc.tags),
            "icon": svc.icon,
            "owner": svc.owner,
            "docs_url": svc.docs_url,
            "source": "static",
        }
        for svc in resolved
    ]


def _dynamic_service_json(entry: DynamicService, config: RegistryConfig) -> dict:
    """Resolve one dynamic registry entry into the same dict shape as a
    static service (links resolved against every configured host address,
    exactly like ``urls.resolve_service``), tagged ``source: "dynamic"``.
    """
    path = entry.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    links: list[dict] = []
    if entry.port is not None:
        for addr in config.host_addresses:
            links.append(
                {
                    "label": addr.label,
                    "host": addr.host,
                    "url": f"{addr.scheme}://{addr.host}:{entry.port}{path}",
                }
            )
    elif entry.url:
        links.append({"label": "url", "host": "", "url": entry.url})
    return {
        "name": entry.name,
        "description": entry.description,
        "links": links,
        "category": entry.category,
        "tags": list(entry.tags),
        "icon": entry.icon,
        "owner": entry.owner,
        "docs_url": entry.docs_url,
        "health_url": entry.health_url,
        "ttl": entry.ttl,
        "source": "dynamic",
    }


class PairRequest(BaseModel):
    device_id: str
    name: str
    base_url: str
    code: str


class ServiceRegistration(BaseModel):
    name: str
    port: int | None = None
    url: str | None = None
    path: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] = []
    icon: str | None = None
    owner: str | None = None
    docs_url: str | None = None
    health_url: str | None = None
    ttl: float | None = None


def create_app(
    config: RegistryConfig,
    checker: Checker = default_checker,
    peer_fetcher: PeerFetcher = default_peer_fetcher,
    peer_timeout: float = DEFAULT_PEER_TIMEOUT_SECONDS,
    http_checker: HttpChecker = default_http_checker,
    time_fn=time.time,
) -> FastAPI:
    """Build the FastAPI app for a given (already-loaded) config.

    ``checker`` is the injectable connectivity-check seam -- production code
    uses the real ``default_checker``; tests pass a stub so no real network
    I/O ever happens in the suite. ``peer_fetcher`` is the equivalent seam
    for federation pull-aggregation against trusted peers. ``http_checker``
    is the equivalent seam for HTTP ``health_url`` checks on dynamic
    registry entries. ``time_fn`` is the injectable clock seam used for
    dynamic-registry TTL/heartbeat expiry (default ``time.time``).
    """
    app = FastAPI(title="service-directory")
    app.state.config = config
    app.state.checker = checker
    app.state.http_checker = http_checker
    app.state.peer_fetcher = peer_fetcher
    app.state.peer_timeout = peer_timeout
    app.state.state_dir = resolve_state_dir(config)
    app.state.local_name = _local_name(config)
    app.state.pairing_store = PairingCodeStore()
    app.state.time_fn = time_fn

    def _static_names() -> set[str]:
        return {svc.name for svc in config.services}

    def _all_local_services_json() -> list[dict]:
        """Static (YAML) services UNION dynamic (runtime-registered)
        services -- this node's OWN catalogue, before origin-tagging.

        The dynamic registry is read FRESH from disk on every call (never
        cached), pruning any TTL entries that went stale since the last
        read -- see ``registry.load_registry``.
        """
        static = _local_services_json(config)
        dynamic_entries = load_registry(app.state.state_dir, time_fn=app.state.time_fn)
        dynamic = [_dynamic_service_json(e, config) for e in dynamic_entries]
        return static + dynamic

    def _local_only_services() -> list[dict]:
        """This node's OWN services only (static UNION dynamic), tagged
        with the local origin.

        NEVER aggregates peers -- used both for GET /api/services/local and
        (defensively) as the fallback when a request arrives already
        bearing the federation hop header, so a misconfigured peer fetcher
        pointed at the aggregated endpoint still cannot trigger recursion.
        Dynamic services flow through this SAME view, so they federate
        across peers exactly like static ones.
        """
        local = _all_local_services_json()
        return [dict(svc, origin=app.state.local_name) for svc in local]

    def _aggregation_result(request: Request) -> AggregationResult:
        """The SAME best-effort peer aggregation used by /api/services --
        also the single source of truth for peer reachability (consumed by
        /api/federation/nodes). Never probes peers a second time.
        """
        # Defensive hop/visited guard: a request carrying the federation
        # hop header is itself another node's peer-fetch. Even though
        # default_peer_fetcher already targets the local-only endpoint
        # (breaking the recursion at the root), this ensures that ANY
        # aggregated endpoint hit with that header -- e.g. a misconfigured
        # peer fetcher, or a future 3+ node graph -- degrades to a local-
        # only answer instead of fanning out to further peers.
        if request.headers.get(FEDERATION_HOP_HEADER):
            return AggregationResult(
                services=_local_only_services(),
                reachable_peers=[app.state.local_name],
                unreachable_peers=[],
            )
        if not config.federation.enabled:
            # Federation off: still tag origin so the JSON shape is stable,
            # but never attempt any peer I/O.
            return AggregationResult(
                services=_local_only_services(),
                reachable_peers=[app.state.local_name],
                unreachable_peers=[],
            )
        peers = load_peers(app.state.state_dir)
        return aggregate_services(
            local_name=app.state.local_name,
            local_services=_all_local_services_json(),
            peers=peers,
            fetcher=app.state.peer_fetcher,
            timeout=app.state.peer_timeout,
        )

    def _aggregated_services(request: Request) -> list[dict]:
        return _aggregation_result(request).services

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        services = _aggregated_services(request)
        node_info = [
            {
                "name": app.state.local_name,
                "description": config.federation.description,
            }
        ]
        return HTMLResponse(_render_html(services, node_info))

    @app.get("/api/services")
    def api_services(request: Request) -> JSONResponse:
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        services = _aggregated_services(request)
        return JSONResponse(services)

    @app.get("/api/services/local")
    def api_services_local(request: Request) -> JSONResponse:
        """LOCAL-ONLY services view: this node's own services, never peers.

        Same read-access rules as /api/services. This is the endpoint
        peer-fetches target (see ``default_peer_fetcher``), so fetching a
        peer can never itself trigger another round of peer aggregation.
        """
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        return JSONResponse(_local_only_services())

    @app.get("/api/health")
    def api_health(request: Request) -> JSONResponse:
        """Health for the FULL local catalogue (static UNION dynamic).

        Priority per entry: heartbeat-fresh (ttl entries that survived
        pruning on read) -> HTTP GET health_url (2xx = up) -> TCP connect
        fallback against the first resolved link -- see
        ``health.check_service_entries``.
        """
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        entries = _all_local_services_json()
        results = check_service_entries(
            entries,
            checker=app.state.checker,
            http_checker=app.state.http_checker,
            allow_private_health_targets=config.federation.allow_private_health_targets,
        )
        return JSONResponse(results)

    @app.post("/api/services")
    def api_register_service(
        request: Request, body: ServiceRegistration
    ) -> JSONResponse:
        """Register/UPSERT a dynamic service. EVERY mutation requires
        authorization -- see ``auth.require_write_access``. A dynamic name
        colliding with a STATIC (YAML) service name is rejected (409): no
        silent shadowing of the declarative baseline.
        """
        require_write_access(
            request, app.state.state_dir, config.federation.require_write_token
        )
        if not body.name:
            raise HTTPException(status_code=400, detail="name is required")
        if body.port is None and not body.url:
            raise HTTPException(
                status_code=400, detail="either 'port' or 'url' is required"
            )
        if body.name in _static_names():
            raise HTTPException(
                status_code=409,
                detail=f"'{body.name}' is a static service name and cannot be "
                f"shadowed by a dynamic registration",
            )
        entry = DynamicService(
            name=body.name,
            port=body.port,
            url=body.url,
            path=body.path or "/",
            description=body.description,
            category=body.category,
            tags=list(body.tags),
            icon=body.icon,
            owner=body.owner,
            docs_url=body.docs_url,
            health_url=body.health_url,
            ttl=body.ttl,
        )
        stored = register_service(app.state.state_dir, entry, time_fn=app.state.time_fn)
        return JSONResponse(_dynamic_service_json(stored, config))

    @app.delete("/api/services/{name}")
    def api_deregister_service(name: str, request: Request) -> JSONResponse:
        """Deregister a DYNAMIC service. Static entries are read-only --
        deleting/mutating a static name returns 403 (it exists, but is not
        removable this way), an unknown/never-registered dynamic name
        returns 404.
        """
        require_write_access(
            request, app.state.state_dir, config.federation.require_write_token
        )
        if name in _static_names():
            raise HTTPException(status_code=403, detail="static services are read-only")
        removed = deregister_service(
            app.state.state_dir, name, time_fn=app.state.time_fn
        )
        if not removed:
            raise HTTPException(status_code=404, detail=f"no dynamic service '{name}'")
        return JSONResponse({"removed": name})

    @app.post("/api/services/{name}/heartbeat")
    def api_heartbeat_service(name: str, request: Request) -> JSONResponse:
        """Refresh a ttl entry's liveness. Static entries are read-only
        (403). An unknown/expired-and-pruned dynamic name returns 404.
        """
        require_write_access(
            request, app.state.state_dir, config.federation.require_write_token
        )
        if name in _static_names():
            raise HTTPException(status_code=403, detail="static services are read-only")
        updated = heartbeat_service(
            app.state.state_dir, name, time_fn=app.state.time_fn
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"no dynamic service '{name}'")
        return JSONResponse(_dynamic_service_json(updated, config))

    @app.get("/api/instance-info")
    def instance_info() -> JSONResponse:
        """Unauthenticated. Returns ONLY non-secret identity fields -- no
        tokens, no peer list, no config internals.

        ``federation.description``/``federation.role`` are INTENTIONALLY
        public, unauthenticated metadata (same trust tier as ``name``) --
        by design, so any node can self-describe itself to an unauthenticated
        prober during discovery, same as ``name``/``federation_enabled``
        already are. They are included ONLY when explicitly configured
        (never emitted when unset, preserving the exact pre-existing key
        set). Operators MUST NOT put secrets or sensitive internal details
        in these two free-text fields -- treat them like a public hostname,
        not like a peer token or config path.
        """
        identity = load_or_create_identity(app.state.state_dir)
        info = {
            "name": app.state.local_name,
            "device_id": identity.device_id,
            "version": __version__,
            "federation_enabled": config.federation.enabled,
        }
        if config.federation.description:
            info["description"] = config.federation.description
        if config.federation.role:
            info["role"] = config.federation.role
        return JSONResponse(info)

    @app.get("/api/federation/nodes")
    def federation_nodes(request: Request) -> JSONResponse:
        """Nodes as seen from this node: THIS node (from config/identity)
        plus each trusted peer, with reachability reused from the SAME
        best-effort peer aggregation used by /api/services -- never a
        second probe. Same read-access rules as /api/services.
        """
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        identity = load_or_create_identity(app.state.state_dir)
        result = _aggregation_result(request)
        unreachable = set(result.unreachable_peers)

        nodes = [
            {
                "name": app.state.local_name,
                "description": config.federation.description,
                "role": config.federation.role,
                "device_id": identity.device_id,
                "base_url": config.federation.base_url,
                "reachable": True,
            }
        ]
        for peer in load_peers(app.state.state_dir):
            nodes.append(
                {
                    "name": peer.name,
                    "description": None,
                    "role": None,
                    "device_id": peer.device_id,
                    "base_url": peer.base_url,
                    "reachable": peer.name not in unreachable,
                }
            )
        return JSONResponse(nodes)

    @app.post("/api/federation/pairing-code")
    def issue_pairing_code(request: Request) -> JSONResponse:
        """Mint a short-lived, one-time pairing code. Localhost/admin only."""
        require_admin(request, app.state.state_dir)
        code = app.state.pairing_store.issue()
        from .pairing import DEFAULT_PAIRING_TTL_SECONDS

        return JSONResponse({"code": code, "ttl_seconds": DEFAULT_PAIRING_TTL_SECONDS})

    @app.post("/api/federation/pair")
    def pair(body: PairRequest) -> JSONResponse:
        """Redeem a one-time pairing code from a caller node, mint a
        long-lived per-peer token, record the caller in the trust store, and
        return our own identity + that token so both sides trust each other
        using the same per-peer secret.
        """
        if not app.state.pairing_store.redeem(body.code):
            raise HTTPException(
                status_code=400, detail="invalid or expired pairing code"
            )

        token = secrets.token_urlsafe(32)
        upsert_peer(
            app.state.state_dir,
            PeerRecord(
                name=body.name,
                device_id=body.device_id,
                base_url=body.base_url,
                token=token,
            ),
        )
        identity = load_or_create_identity(app.state.state_dir)
        return JSONResponse(
            {
                "name": app.state.local_name,
                "device_id": identity.device_id,
                "base_url": config.federation.base_url,
                "token": token,
            }
        )

    return app


def create_app_from_env(config_path: str | None = None) -> FastAPI:
    """Build the app by loading config from ``SERVICE_REGISTRY_CONFIG`` (or
    an explicit path). Raises :class:`ConfigError` on malformed config --
    callers (the CLI) are responsible for turning that into a clear,
    non-crashing user-facing message.
    """
    config = load_config(config_path)
    return create_app(config)


__all__ = ["ConfigError", "create_app", "create_app_from_env"]
