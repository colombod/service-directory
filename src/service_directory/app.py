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
    DEFAULT_MAX_HOPS,
    DEFAULT_PEER_TIMEOUT_SECONDS,
    FEDERATION_HOP_HEADER,
    FEDERATION_TTL_HEADER,
    FEDERATION_VISITED_HEADER,
    AggregationResult,
    PeerFetcher,
    aggregate_services,
    dedupe_services,
    default_peer_fetcher,
    make_default_transitive_fetcher,
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


def _service_row_html(svc: dict) -> str:
    name = html_escape.escape(svc["name"])
    desc = svc.get("description") or ""
    desc_html = html_escape.escape(desc)
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
            '<span class="tags">'
            + "".join(f'<span class="tag">{html_escape.escape(t)}</span>' for t in tags)
            + "</span>"
        )
    icon_html = ""
    if svc.get("icon"):
        icon_html = f'<span class="icon">{html_escape.escape(svc["icon"])}</span>'
    owner_html = ""
    if svc.get("owner"):
        owner_html = f'<span class="owner">{html_escape.escape(svc["owner"])}</span>'
    # docs_url / link URLs can be relayed verbatim from a federated peer or a
    # dynamic registration -- only ever render as a clickable href when the
    # scheme is an allow-listed http(s) one (drop the link, keep the row).
    docs_html = ""
    docs_url = svc.get("docs_url")
    if docs_url and is_safe_docs_url(docs_url):
        docs_html = f'<a class="docs" href="{html_escape.escape(docs_url)}">docs</a>'
    meta_html = ""
    if owner_html or docs_html:
        meta_html = f'<span class="meta">{owner_html}{docs_html}</span>'
    origin = svc.get("origin") or ""
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
    remove_html = ""
    if svc.get("source") == "dynamic":
        remove_html = (
            f'<button type="button" class="remove-service" '
            f'data-remove-name="{name}" title="Remove {name}">&times;</button>'
        )
    return (
        f'<tr class="service" data-name="{name}" data-search="{search_blob}">'
        f'<td class="col-name">{icon_html}<span class="service-name">{name}</span>'
        f"{category_html}</td>"
        f'<td class="col-desc">{desc_html}{tags_html}</td>'
        f'<td class="col-status">'
        f'<span class="health-pill unknown" data-health-name="{name}">'
        f'<span class="health-dot" data-health-name="{name}">&#9679;</span>'
        f'<span class="health-label">unknown</span></span></td>'
        f'<td class="col-links">{links_html}</td>'
        f'<td class="col-meta">{meta_html}</td>'
        f'<td class="col-actions">{remove_html}</td>'
        f"</tr>"
    )


# Backwards-compatible alias: the row renderer was previously named
# _service_card_html (cards). Security tests import it by that name to assert
# unsafe links/docs_url are dropped -- behaviour is unchanged by the table redesign.
_service_card_html = _service_row_html


def _render_html(services: list[dict], node_info: list[dict] | None = None) -> str:
    """Render the single self-contained dashboard page.

    Services are grouped BY ORIGIN NODE (a section per node) and presented as
    a precise, uniform table -- no per-item tiles, no motion. A plain inline-JS
    search filters rows by name/description/tag/origin; a health pill per row
    is updated client-side from /api/health. Single self-contained page: all
    CSS/JS inline, no build step, no external/CDN assets.
    """
    node_info = node_info or []
    node_roles = {n["name"]: n.get("role") for n in node_info}
    node_descriptions = {n["name"]: n.get("description") for n in node_info}

    local_name = node_info[0]["name"] if node_info else ""
    local_role = node_roles.get(local_name)

    identity_bits = [
        f'<span class="node-chip-name">{html_escape.escape(local_name)}</span>'
    ]
    if local_role:
        identity_bits.append(
            f'<span class="node-chip-role">{html_escape.escape(local_role)}</span>'
        )
    identity_html = " &middot; ".join(identity_bits)

    grouped: dict[str, list[dict]] = {}
    for svc in services:
        origin = svc.get("origin") or ""
        grouped.setdefault(origin, []).append(svc)

    sections = []
    for origin, group in grouped.items():
        origin_name = html_escape.escape(origin) if origin else "unknown"
        desc = node_descriptions.get(origin)
        desc_html = ""
        if desc:
            desc_html = (
                f'<span class="node-description">{html_escape.escape(desc)}</span>'
            )
        rows = "\n".join(_service_row_html(svc) for svc in group)
        # Every group present here is reachable by construction (unreachable
        # peers contribute no entries -- see federation.aggregate_services).
        sections.append(
            f'<section class="node-group" data-origin="{origin_name}">'
            '<div class="node-group-header">'
            f"<h2>{origin_name}</h2>"
            '<span class="reachable-badge reachable">reachable</span>'
            f"{desc_html}"
            "</div>"
            '<table class="svc-table"><thead><tr>'
            "<th>Service</th><th>Description</th><th>Status</th>"
            "<th>Address</th><th>Info</th><th></th>"
            f"</tr></thead><tbody>{rows}</tbody></table>"
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
  var cards = document.querySelectorAll('.service');
  var sections = document.querySelectorAll('section.node-group');

  function applyFilter() {
    var q = (input.value || '').toLowerCase();
    sections.forEach(function (section) {
      var visibleCount = 0;
      section.querySelectorAll('.service').forEach(function (card) {
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
    }).catch(function () {});
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
  --bg: #ffffff; --panel: #ffffff; --alt: #f6f7f9;
  --border: #e4e7ec; --border-strong: #cdd2da;
  --text: #1b232f; --text-muted: #56606e; --text-faint: #838d9b;
  --accent: #3355d1; --accent-weak: #eef1fb;
  --up: #1f9d55; --up-bg: #e8f6ee; --down: #d23b3b; --down-bg: #fbeaea;
  --unknown: #8a94a3; --unknown-bg: #eef0f3;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1319; --panel: #141a22; --alt: #1a212b;
    --border: #232b36; --border-strong: #323b48;
    --text: #e6eaf0; --text-muted: #9aa4b2; --text-faint: #707a88;
    --accent: #7f9cff; --accent-weak: #1b2333;
    --up: #35c07a; --up-bg: #10251a; --down: #f06666; --down-bg: #2a1414;
    --unknown: #6b7581; --unknown-bg: #1c232c;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-font-smoothing: antialiased; }
a { color: var(--accent); text-decoration: none; }
::placeholder { color: var(--text-faint); opacity: 1; }
.page { max-width: 1200px; margin: 0 auto; padding: 0 28px 56px; }

.header-band { display: flex; align-items: baseline; justify-content: space-between; gap: 16px;
  padding: 22px 0 16px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }
.header-top { display: contents; }
.brand { margin: 0; font-size: 17px; font-weight: 650; letter-spacing: -.01em; }
.node-chip { font-size: 12.5px; color: var(--text-muted); }
.node-chip-name { font-weight: 600; color: var(--text); }
.node-chip-role { color: var(--accent); font-weight: 600; }
.node-chip-description { display: none; }
.search-bar { position: relative; margin-bottom: 26px; }
.search-bar::before { content: ""; position: absolute; left: 12px; top: 50%; transform: translateY(-50%);
  width: 15px; height: 15px; background: var(--text-faint);
  -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E") center/contain no-repeat;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E") center/contain no-repeat; }
#service-filter { width: 100%; padding: 9px 12px 9px 34px; font-size: 13.5px; color: var(--text);
  background: var(--panel); border: 1px solid var(--border-strong); border-radius: 7px; }
#service-filter:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-weak); }

.node-group { margin-bottom: 28px; }
.node-group-header { display: flex; align-items: center; gap: 9px; margin-bottom: 9px; }
.node-group-header h2 { margin: 0; font-size: 11.5px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--text-muted); }
.reachable-badge { font-size: 11px; font-weight: 600; color: var(--up);
  display: inline-flex; align-items: center; gap: 5px; }
.reachable-badge::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.node-description { font-size: 12px; color: var(--text-faint); }
.node-description::before { content: "\2014 "; }

.svc-table { width: 100%; border-collapse: collapse; background: var(--panel);
  border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.svc-table thead th { text-align: left; font-size: 10.5px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .05em; color: var(--text-faint); padding: 10px 16px; background: var(--alt);
  border-bottom: 1px solid var(--border); }
.svc-table td { padding: 13px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
.svc-table tbody tr:last-child td { border-bottom: none; }
.col-name { white-space: nowrap; }
.icon { margin-right: 8px; }
.service-name { font-weight: 600; }
.category { margin-left: 9px; font-size: 11px; font-weight: 600; color: var(--accent);
  background: var(--accent-weak); padding: 2px 8px; border-radius: 5px; }
.col-desc { color: var(--text-muted); font-size: 13px; max-width: 380px; }
.tags { margin-left: 8px; }
.tag { font-size: 11.5px; color: var(--text-faint); margin-right: 6px; }
.tag::before { content: "#"; opacity: .6; }
.col-status { white-space: nowrap; }
.health-pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600;
  padding: 3px 9px; border-radius: 5px; text-transform: capitalize; }
.health-pill .health-dot { font-size: 7px; line-height: 1; }
.health-pill.up { color: var(--up); background: var(--up-bg); }
.health-pill.down { color: var(--down); background: var(--down-bg); }
.health-pill.unknown { color: var(--unknown); background: var(--unknown-bg); }
.col-links { white-space: nowrap; }
.link-btn { font-family: var(--mono); font-size: 12px; font-weight: 600; padding: 5px 11px;
  border-radius: 6px; margin-right: 6px; display: inline-block; }
.link-btn-primary { color: #fff; background: var(--accent); }
.link-btn-secondary { color: var(--text-muted); border: 1px solid var(--border-strong); }
.col-meta { white-space: nowrap; }
.meta { font-size: 12px; color: var(--text-faint); }
.owner { margin-right: 10px; }
.docs { color: var(--accent); font-weight: 600; }
.col-actions { text-align: right; width: 40px; }
.remove-service { border: none; background: none; color: var(--text-faint); font-size: 18px;
  cursor: pointer; padding: 0 4px; line-height: 1; }
.remove-service:hover { color: var(--down); }

.empty-state { border: 1px dashed var(--border-strong); border-radius: 10px; padding: 44px;
  text-align: center; color: var(--text-muted); background: var(--alt); }
.empty-state-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0 0 6px; }
.empty-state-hint { margin: 0; font-size: 13px; }

.registration-panel { margin-top: 28px; padding: 20px; background: var(--alt);
  border: 1px solid var(--border); border-radius: 10px; }
.panel-title { margin: 0 0 14px; font-size: 12px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--text-muted); }
.write-token-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px;
  padding-bottom: 16px; border-bottom: 1px solid var(--border); }
.write-token-row label { font-size: 12px; color: var(--text-muted); }
.write-token-row .hint { color: var(--text-faint); font-weight: 400; }
#write-token-input, .add-service-form input { width: 100%; padding: 9px 12px; font-size: 13.5px;
  color: var(--text); background: var(--panel); border: 1px solid var(--border-strong); border-radius: 7px; }
#write-token-input:focus, .add-service-form input:focus { outline: none; border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-weak); }
.add-service-form { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.add-service-form h2 { display: none; }
.add-service-form button { padding: 9px 18px; font-size: 13px; font-weight: 600; color: #fff;
  background: var(--accent); border: none; border-radius: 7px; cursor: pointer; }
.add-service-error { grid-column: 1 / -1; color: var(--down); font-size: 12px; min-height: 1em; }

@media (max-width: 720px) {
  .svc-table thead { display: none; }
  .svc-table, .svc-table tbody, .svc-table tr, .svc-table td { display: block; width: 100%; }
  .svc-table td { border-bottom: none; padding: 3px 16px; }
  .svc-table tbody tr { border-bottom: 1px solid var(--border); padding: 12px 0; }
}
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
        f'<div class="node-chip">{identity_html}</div>'
        "</div>"
        "</header>"
        '<div class="search-bar">'
        '<input type="text" id="service-filter" '
        'aria-label="Filter services by name, description, tag, or origin" '
        'placeholder="Filter by name, description, tag, or origin\u2026" />'
        "</div>"
        '<main class="content">'
        f"{body}"
        f"{empty_state_html}"
        "</main>"
        '<section class="registration-panel">'
        '<h2 class="panel-title">Register a service</h2>'
        '<div class="write-token-row">'
        '<label for="write-token-input">Write token '
        '<span class="hint">(required for remote/tailnet writes, or when the '
        'node enforces one on localhost)</span></label> '
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
    peer_fetcher_factory=None,
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
    app.state.peer_fetcher_factory = peer_fetcher_factory
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

    def _local_only_result() -> AggregationResult:
        return AggregationResult(
            services=_local_only_services(),
            reachable_peers=[app.state.local_name],
            unreachable_peers=[],
        )

    def _aggregation_result(request: Request) -> AggregationResult:
        """Best-effort peer aggregation for /api/services -- also the single
        source of truth for peer reachability (consumed by
        /api/federation/nodes).

        TRANSITIVE + LOOP-SAFE. A top-level (user-facing) request carries no
        federation headers: it starts with an empty visited-set and the full
        DEFAULT_MAX_HOPS budget. A request that arrives bearing the hop header
        is another node's peer-fetch: it carries the visited-set of nodes
        already traversed and the remaining hop budget. This node:

          * answers LOCAL-ONLY (stopping the walk) if it is itself already in
            ``visited`` -- a cycle -- or the budget is exhausted (ttl <= 0);
          * otherwise fetches every trusted peer NOT already in ``visited``,
            passing ``visited | {self}`` and ``ttl - 1``, and merges.

        The visited-set makes a cycle impossible; the budget bounds depth. So
        a CONNECTED graph aggregates fully (pair any new node to any one
        member -- no full mesh needed) while a mutual/looping graph terminates.
        Duplicates reachable via multiple paths are collapsed by (origin, name).
        """
        if not config.federation.enabled:
            # Federation off: still tag origin so the JSON shape is stable,
            # but never attempt any peer I/O.
            return _local_only_result()

        is_hop = request.headers.get(FEDERATION_HOP_HEADER) is not None
        raw_visited = request.headers.get(FEDERATION_VISITED_HEADER, "")
        visited = frozenset(n for n in raw_visited.split(",") if n)
        raw_ttl = request.headers.get(FEDERATION_TTL_HEADER)
        if raw_ttl is not None:
            try:
                ttl = int(raw_ttl)
            except ValueError:
                ttl = 0
        elif is_hop:
            # A hop with no explicit budget (e.g. an older/misconfigured peer
            # fetcher) is treated as fully exhausted -- answer local-only,
            # never fan out. Belt-and-suspenders against recursion.
            ttl = 0
        else:
            ttl = DEFAULT_MAX_HOPS

        me = app.state.local_name
        if me in visited or ttl <= 0:
            return _local_only_result()

        new_visited = visited | {me}
        peers = [p for p in load_peers(app.state.state_dir) if p.name not in new_visited]

        # Select the fetcher. An injected raw fetcher (existing hermetic tests)
        # is used as-is -- one level, visited/ttl not threaded -- preserving
        # its behaviour exactly. A factory (transitive tests) or the production
        # default builds a visited/ttl-aware fetcher that hits each peer's
        # AGGREGATED endpoint so the walk continues, bounded, on the far side.
        if app.state.peer_fetcher_factory is not None:
            fetcher = app.state.peer_fetcher_factory(new_visited, ttl - 1)
        elif app.state.peer_fetcher is default_peer_fetcher:
            fetcher = make_default_transitive_fetcher(new_visited, ttl - 1)
        else:
            fetcher = app.state.peer_fetcher

        result = aggregate_services(
            local_name=me,
            local_services=_all_local_services_json(),
            peers=peers,
            fetcher=fetcher,
            timeout=app.state.peer_timeout,
        )
        return AggregationResult(
            services=dedupe_services(result.services),
            reachable_peers=result.reachable_peers,
            unreachable_peers=result.unreachable_peers,
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
