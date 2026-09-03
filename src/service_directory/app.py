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
import urllib.parse
import urllib.request

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from . import __version__
from .auth import require_admin, require_read_access, require_write_access
from .config import (
    ConfigError,
    RegistryConfig,
    is_safe_docs_url,
    is_safe_health_target,
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
    # Task 5: embed view_url / view_kind as data-attributes for the JS viewer.
    # Fall back to the primary link URL when view_url is not configured.
    primary_url = safe_links[0]["url"] if safe_links else ""
    raw_view_url = svc.get("view_url") or primary_url
    view_url_attr = html_escape.escape(raw_view_url) if raw_view_url else ""
    view_kind_attr = html_escape.escape(svc.get("view_kind") or "auto")
    return (
        f'<tr class="service" data-name="{name}" data-search="{search_blob}"'
        f' data-view-url="{view_url_attr}" data-view-kind="{view_kind_attr}">'
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

    Two-pane workspace: a collapsible left sidebar listing services grouped by
    origin node, and a right viewer pane that opens a selected service's UI
    in-page (iframe for HTML, formatted JSON tree for JSON endpoints, graceful
    fallback card for services that refuse framing).

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

    script = (
        "\n<script>\n"
        "(function () {\n"
        "  var input = document.getElementById('service-filter');\n"
        "  var cards = document.querySelectorAll('.service');\n"
        "  var sections = document.querySelectorAll('section.node-group');\n"
        "\n"
        "  function applyFilter() {\n"
        "    var q = (input.value || '').toLowerCase();\n"
        "    sections.forEach(function (section) {\n"
        "      var visibleCount = 0;\n"
        "      section.querySelectorAll('.service').forEach(function (card) {\n"
        "        var haystack = card.getAttribute('data-search') || '';\n"
        "        var origin = section.getAttribute('data-origin') || '';\n"
        "        var match = q === '' || haystack.indexOf(q) !== -1 ||\n"
        "          origin.toLowerCase().indexOf(q) !== -1;\n"
        "        card.style.display = match ? '' : 'none';\n"
        "        if (match) visibleCount += 1;\n"
        "      });\n"
        "      section.style.display = visibleCount > 0 ? '' : 'none';\n"
        "    });\n"
        "  }\n"
        "\n"
        "  if (input) {\n"
        "    input.addEventListener('input', applyFilter);\n"
        "  }\n"
        "\n"
        "  function updateHealth() {\n"
        "    fetch('/api/health').then(function (resp) {\n"
        "      return resp.json();\n"
        "    }).then(function (data) {\n"
        "      cards.forEach(function (card) {\n"
        "        var name = card.getAttribute('data-name');\n"
        "        var dot = card.querySelector('.health-dot');\n"
        "        var pill = card.querySelector('.health-pill');\n"
        "        var label = card.querySelector('.health-label');\n"
        "        var raw = data[name];\n"
        "        var status = raw === 'up' ? 'up' : (raw === 'down' ? 'down' : 'unknown');\n"
        "        if (dot) dot.className = 'health-dot ' + status;\n"
        "        if (pill) pill.className = 'health-pill ' + status;\n"
        "        if (label) label.textContent = status;\n"
        "      });\n"
        "    }).catch(function () {});\n"
        "  }\n"
        "\n"
        "  updateHealth();\n"
        "\n"
        "  function tokenHeaders() {\n"
        "    var tokenInput = document.getElementById('write-token-input');\n"
        "    var token = tokenInput ? (tokenInput.value || '').trim() : '';\n"
        "    var headers = {'Content-Type': 'application/json'};\n"
        "    if (token) {\n"
        "      headers['Authorization'] = 'Bearer ' + token;\n"
        "    }\n"
        "    return headers;\n"
        "  }\n"
        "\n"
        "  var addForm = document.getElementById('add-service-form');\n"
        "  var addError = document.getElementById('add-service-error');\n"
        "  if (addForm) {\n"
        "    addForm.addEventListener('submit', function (event) {\n"
        "      event.preventDefault();\n"
        "      if (addError) addError.textContent = '';\n"
        "      var formData = new FormData(addForm);\n"
        "      var body = {\n"
        "        name: formData.get('name'),\n"
        "        port: parseInt(formData.get('port'), 10),\n"
        "        description: formData.get('description') || null,\n"
        "        category: formData.get('category') || null,\n"
        "        health_url: formData.get('health_url') || null\n"
        "      };\n"
        "      fetch('/api/services', {\n"
        "        method: 'POST',\n"
        "        headers: tokenHeaders(),\n"
        "        body: JSON.stringify(body)\n"
        "      }).then(function (resp) {\n"
        "        if (!resp.ok) {\n"
        "          return resp.json().catch(function () { return {}; }).then(function (data) {\n"
        "            throw new Error((data && data.detail) || ('request failed: ' + resp.status));\n"
        "          });\n"
        "        }\n"
        "        return resp.json();\n"
        "      }).then(function () {\n"
        "        window.location.reload();\n"
        "      }).catch(function (err) {\n"
        "        if (addError) addError.textContent = String(err.message || err);\n"
        "      });\n"
        "    });\n"
        "  }\n"
        "\n"
        "  document.querySelectorAll('.remove-service').forEach(function (btn) {\n"
        "    btn.addEventListener('click', function () {\n"
        "      var name = btn.getAttribute('data-remove-name');\n"
        "      if (!name) return;\n"
        "      fetch('/api/services/' + encodeURIComponent(name), {\n"
        "        method: 'DELETE',\n"
        "        headers: tokenHeaders()\n"
        "      }).then(function (resp) {\n"
        "        if (!resp.ok) {\n"
        "          throw new Error('remove failed: ' + resp.status);\n"
        "        }\n"
        "        window.location.reload();\n"
        "      }).catch(function (err) {\n"
        "        window.alert(String(err.message || err));\n"
        "      });\n"
        "    });\n"
        "  });\n"
        "\n"
        "  // ---- Two-pane sidebar/viewer logic (Tasks 1-4) ----\n"
        "\n"
        "  var sidebar = document.getElementById('sidebar');\n"
        "  var viewer = document.getElementById('viewer');\n"
        "  var collapseBtn = document.getElementById('sidebar-collapse-btn');\n"
        "\n"
        "  if (collapseBtn && sidebar) {\n"
        "    collapseBtn.addEventListener('click', function () {\n"
        "      var collapsed = sidebar.getAttribute('data-collapsed') === 'true';\n"
        "      sidebar.setAttribute('data-collapsed', collapsed ? 'false' : 'true');\n"
        "      collapseBtn.setAttribute('aria-expanded', collapsed ? 'true' : 'false');\n"
        "      collapseBtn.title = collapsed ? 'Collapse sidebar' : 'Expand sidebar';\n"
        "    });\n"
        "  }\n"
        "\n"
        "  // JSON tree renderer (Task 4) -- plain inline JS, no libraries.\n"
        "  function renderJsonTree(obj, depth) {\n"
        "    depth = depth || 0;\n"
        "    if (obj === null) return '<span class=\"json-null\">null</span>';\n"
        "    if (typeof obj === 'boolean') return '<span class=\"json-bool\">' + obj + '</span>';\n"
        "    if (typeof obj === 'number') return '<span class=\"json-num\">' + obj + '</span>';\n"
        "    if (typeof obj === 'string') return '<span class=\"json-str\">\"' + obj.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\"/g,'&quot;') + '\"</span>';\n"
        "    if (Array.isArray(obj)) {\n"
        "      if (obj.length === 0) return '<span class=\"json-bracket\">[]</span>';\n"
        "      var items = obj.map(function(v) { return '<li>' + renderJsonTree(v, depth+1) + '</li>'; }).join('');\n"
        "      return '<details open><summary class=\"json-bracket\">[' + obj.length + ']</summary><ul class=\"json-list\">' + items + '</ul></details>';\n"
        "    }\n"
        "    if (typeof obj === 'object') {\n"
        "      var keys = Object.keys(obj);\n"
        "      if (keys.length === 0) return '<span class=\"json-bracket\">{}</span>';\n"
        "      var entries = keys.map(function(k) {\n"
        "        return '<li><span class=\"json-key\">' + k.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</span>: ' + renderJsonTree(obj[k], depth+1) + '</li>';\n"
        "      }).join('');\n"
        "      return '<details open><summary class=\"json-bracket\">{' + keys.length + '}</summary><ul class=\"json-list\">' + entries + '</ul></details>';\n"
        "    }\n"
        "    return String(obj);\n"
        "  }\n"
        "\n"
        "  function showViewerDefault() {\n"
        "    if (!viewer) return;\n"
        "    viewer.innerHTML = '<div class=\"viewer-default\"><div id=\"viewer-catalogue\"></div></div>';\n"
        "  }\n"
        "\n"
        "  function showViewerLoading(name) {\n"
        "    if (!viewer) return;\n"
        "    viewer.innerHTML = '<div class=\"viewer-loading\">Loading ' + name.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '\u2026</div>';\n"
        "  }\n"
        "\n"
        "  function showViewerIframe(name, url) {\n"
        "    if (!viewer) return;\n"
        "    var safeUrl = url.replace(/&/g,'&amp;').replace(/\"/g,'&quot;');\n"
        "    var safeName = name.replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        "    viewer.innerHTML =\n"
        "      '<div class=\"viewer-header\">' +\n"
        "      '<span class=\"viewer-svc-name\">' + safeName + '</span>' +\n"
        "      '<a class=\"viewer-open-tab\" href=\"' + safeUrl + '\" target=\"_blank\" rel=\"noopener\">open in new tab &#8599;</a>' +\n"
        "      '<button class=\"viewer-close-btn\" id=\"viewer-close-btn\" title=\"Back to catalogue\">&larr; back</button>' +\n"
        "      '</div>' +\n"
        "      '<iframe class=\"viewer-iframe\" id=\"viewer-iframe\" src=\"' + safeUrl + '\" title=\"' + safeName + '\"></iframe>';\n"
        "    document.getElementById('viewer-close-btn').addEventListener('click', showViewerDefault);\n"
        "  }\n"
        "\n"
        "  function showViewerJson(name, url, jsonData) {\n"
        "    if (!viewer) return;\n"
        "    var safeUrl = url.replace(/&/g,'&amp;').replace(/\"/g,'&quot;');\n"
        "    var safeName = name.replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        "    viewer.innerHTML =\n"
        "      '<div class=\"viewer-header\">' +\n"
        "      '<span class=\"viewer-svc-name\">' + safeName + '</span>' +\n"
        "      '<a class=\"viewer-open-tab\" href=\"' + safeUrl + '\" target=\"_blank\" rel=\"noopener\">open in new tab &#8599;</a>' +\n"
        "      '<button class=\"viewer-close-btn\" id=\"viewer-close-btn\" title=\"Back to catalogue\">&larr; back</button>' +\n"
        "      '</div>' +\n"
        "      '<div class=\"viewer-json\" id=\"viewer-json-tree\"></div>';\n"
        "    document.getElementById('viewer-json-tree').innerHTML = renderJsonTree(jsonData);\n"
        "    document.getElementById('viewer-close-btn').addEventListener('click', showViewerDefault);\n"
        "  }\n"
        "\n"
        "  function showViewerFallback(name, url, reason) {\n"
        "    if (!viewer) return;\n"
        "    var safeUrl = url.replace(/&/g,'&amp;').replace(/\"/g,'&quot;');\n"
        "    var safeName = name.replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        "    var safeReason = (reason || '').replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        "    viewer.innerHTML =\n"
        "      '<div class=\"viewer-header\">' +\n"
        "      '<span class=\"viewer-svc-name\">' + safeName + '</span>' +\n"
        "      '<a class=\"viewer-open-tab\" href=\"' + safeUrl + '\" target=\"_blank\" rel=\"noopener\">open in new tab &#8599;</a>' +\n"
        "      '<button class=\"viewer-close-btn\" id=\"viewer-close-btn\" title=\"Back to catalogue\">&larr; back</button>' +\n"
        "      '</div>' +\n"
        "      '<div class=\"viewer-fallback\" id=\"viewer-fallback-card\">' +\n"
        "      '<p class=\"viewer-fallback-title\">Cannot be embedded</p>' +\n"
        "      '<p class=\"viewer-fallback-reason\">' + (safeReason || 'This service cannot be displayed in-page.') + '</p>' +\n"
        "      '<a class=\"viewer-fallback-link\" href=\"' + safeUrl + '\" target=\"_blank\" rel=\"noopener\">Open ' + safeName + ' in a new tab &#8599;</a>' +\n"
        "      '</div>';\n"
        "    document.getElementById('viewer-close-btn').addEventListener('click', showViewerDefault);\n"
        "  }\n"
        "\n"
        "  function openServiceInViewer(name, url, kind) {\n"
        "    if (!url) { showViewerDefault(); return; }\n"
        "    if (kind === 'iframe') {\n"
        "      showViewerIframe(name, url);\n"
        "      return;\n"
        "    }\n"
        "    if (kind === 'json') {\n"
        "      showViewerLoading(name);\n"
        "      fetch('/api/view-proxy?url=' + encodeURIComponent(url))\n"
        "        .then(function(r) {\n"
        "          if (!r.ok) throw new Error('proxy error ' + r.status);\n"
        "          return r.json();\n"
        "        })\n"
        "        .then(function(data) { showViewerJson(name, url, data); })\n"
        "        .catch(function(e) { showViewerFallback(name, url, String(e.message || e)); });\n"
        "      return;\n"
        "    }\n"
        "    // kind === 'auto': probe first.\n"
        "    showViewerLoading(name);\n"
        "    fetch('/api/embed-probe?url=' + encodeURIComponent(url))\n"
        "      .then(function(r) { return r.json(); })\n"
        "      .then(function(probe) {\n"
        "        if (!probe.reachable) {\n"
        "          showViewerFallback(name, url, 'Service is unreachable.');\n"
        "        } else if (probe.content_type && probe.content_type.indexOf('application/json') !== -1) {\n"
        "          // JSON content-type: use proxy renderer.\n"
        "          return fetch('/api/view-proxy?url=' + encodeURIComponent(url))\n"
        "            .then(function(r) {\n"
        "              if (!r.ok) throw new Error('proxy error ' + r.status);\n"
        "              return r.json();\n"
        "            })\n"
        "            .then(function(data) { showViewerJson(name, url, data); })\n"
        "            .catch(function(e) { showViewerFallback(name, url, String(e.message || e)); });\n"
        "        } else if (!probe.embeddable) {\n"
        "          showViewerFallback(name, url, 'This service cannot be embedded (X-Frame-Options or CSP frame-ancestors).');\n"
        "        } else {\n"
        "          showViewerIframe(name, url);\n"
        "        }\n"
        "      })\n"
        "      .catch(function(e) { showViewerFallback(name, url, String(e.message || e)); });\n"
        "  }\n"
        "\n"
        "  // Wire up sidebar service rows as clickable.\n"
        "  document.querySelectorAll('.service').forEach(function (row) {\n"
        "    row.style.cursor = 'pointer';\n"
        "    row.addEventListener('click', function (e) {\n"
        "      // Don't intercept clicks on links/buttons inside the row.\n"
        "      if (e.target.closest('a, button')) return;\n"
        "      var name = row.getAttribute('data-name') || '';\n"
        "      var url = row.getAttribute('data-view-url') || '';\n"
        "      var kind = row.getAttribute('data-view-kind') || 'auto';\n"
        "      openServiceInViewer(name, url, kind);\n"
        "    });\n"
        "  });\n"
        "\n"
        "})();\n"
        "</script>\n"
    )

    style = (
        "\n<style>\n"
        ":root {\n"
        "  color-scheme: light dark;\n"
        "  --bg: #ffffff; --panel: #ffffff; --alt: #f6f7f9;\n"
        "  --border: #e4e7ec; --border-strong: #cdd2da;\n"
        "  --text: #1b232f; --text-muted: #56606e; --text-faint: #838d9b;\n"
        "  --accent: #3355d1; --accent-weak: #eef1fb;\n"
        "  --up: #1f9d55; --up-bg: #e8f6ee; --down: #d23b3b; --down-bg: #fbeaea;\n"
        "  --unknown: #8a94a3; --unknown-bg: #eef0f3;\n"
        "  --mono: ui-monospace, SFMono-Regular, \"SF Mono\", Menlo, Consolas, monospace;\n"
        "}\n"
        "@media (prefers-color-scheme: dark) {\n"
        "  :root {\n"
        "    --bg: #0f1319; --panel: #141a22; --alt: #1a212b;\n"
        "    --border: #232b36; --border-strong: #323b48;\n"
        "    --text: #e6eaf0; --text-muted: #9aa4b2; --text-faint: #707a88;\n"
        "    --accent: #7f9cff; --accent-weak: #1b2333;\n"
        "    --up: #35c07a; --up-bg: #10251a; --down: #f06666; --down-bg: #2a1414;\n"
        "    --unknown: #6b7581; --unknown-bg: #1c232c;\n"
        "  }\n"
        "}\n"
        "* { box-sizing: border-box; }\n"
        "body { margin: 0; background: var(--bg); color: var(--text);\n"
        "  font: 14px/1.5 -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif;\n"
        "  -webkit-font-smoothing: antialiased; }\n"
        "a { color: var(--accent); text-decoration: none; }\n"
        "::placeholder { color: var(--text-faint); opacity: 1; }\n"
        ".page { max-width: 1400px; margin: 0 auto; padding: 0; }\n"
        "\n"
        ".header-band { display: flex; align-items: baseline; justify-content: space-between; gap: 16px;\n"
        "  padding: 22px 28px 16px; border-bottom: 1px solid var(--border); margin-bottom: 0; }\n"
        ".header-top { display: contents; }\n"
        ".brand { margin: 0; font-size: 17px; font-weight: 650; letter-spacing: -.01em; }\n"
        ".node-chip { font-size: 12.5px; color: var(--text-muted); }\n"
        ".node-chip-name { font-weight: 600; color: var(--text); }\n"
        ".node-chip-role { color: var(--accent); font-weight: 600; }\n"
        ".node-chip-description { display: none; }\n"
        "\n"
        "/* Two-pane workspace layout */\n"
        ".workspace { display: flex; height: calc(100vh - 64px); overflow: hidden; }\n"
        "\n"
        "/* Sidebar */\n"
        "#sidebar { width: 340px; min-width: 220px; max-width: 480px; flex-shrink: 0;\n"
        "  border-right: 1px solid var(--border); display: flex; flex-direction: column;\n"
        "  overflow: hidden; background: var(--panel); }\n"
        "#sidebar[data-collapsed=\"true\"] { width: 0; min-width: 0; border-right: none; overflow: hidden; }\n"
        ".sidebar-top { padding: 14px 14px 8px; border-bottom: 1px solid var(--border); flex-shrink: 0; }\n"
        ".sidebar-filter-row { display: flex; align-items: center; gap: 8px; }\n"
        ".search-bar { position: relative; flex: 1; margin-bottom: 0; }\n"
        ".search-bar::before { content: \"\"; position: absolute; left: 10px; top: 50%; transform: translateY(-50%);\n"
        "  width: 13px; height: 13px; background: var(--text-faint);\n"
        "  -webkit-mask: url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E\") center/contain no-repeat;\n"
        "  mask: url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E\") center/contain no-repeat; }\n"
        "#service-filter { width: 100%; padding: 7px 10px 7px 28px; font-size: 13px; color: var(--text);\n"
        "  background: var(--alt); border: 1px solid var(--border-strong); border-radius: 6px; }\n"
        "#service-filter:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-weak); }\n"
        "#sidebar-collapse-btn { flex-shrink: 0; border: 1px solid var(--border-strong); background: var(--alt);\n"
        "  color: var(--text-muted); border-radius: 6px; padding: 5px 9px; font-size: 13px; cursor: pointer;\n"
        "  line-height: 1; }\n"
        "#sidebar-collapse-btn:hover { color: var(--text); }\n"
        ".sidebar-catalogue { flex: 1; overflow-y: auto; padding: 10px 0; }\n"
        "\n"
        "/* Viewer pane */\n"
        "#viewer { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; }\n"
        ".viewer-default { flex: 1; overflow-y: auto; padding: 24px 28px 56px; }\n"
        ".viewer-loading { flex: 1; display: flex; align-items: center; justify-content: center;\n"
        "  color: var(--text-muted); font-size: 14px; }\n"
        ".viewer-header { display: flex; align-items: center; gap: 12px; padding: 10px 18px;\n"
        "  border-bottom: 1px solid var(--border); background: var(--alt); flex-shrink: 0; }\n"
        ".viewer-svc-name { font-weight: 600; font-size: 14px; flex: 1; }\n"
        ".viewer-open-tab { font-size: 12px; color: var(--accent); }\n"
        ".viewer-close-btn { border: 1px solid var(--border-strong); background: var(--panel);\n"
        "  color: var(--text-muted); border-radius: 5px; padding: 4px 10px; font-size: 12px; cursor: pointer; }\n"
        ".viewer-close-btn:hover { color: var(--text); }\n"
        ".viewer-iframe { flex: 1; border: none; width: 100%; height: 100%; }\n"
        ".viewer-json { flex: 1; overflow: auto; padding: 18px 24px; font-family: var(--mono); font-size: 13px; }\n"
        ".viewer-fallback { flex: 1; display: flex; flex-direction: column; align-items: center;\n"
        "  justify-content: center; padding: 40px; text-align: center; }\n"
        ".viewer-fallback-title { font-size: 16px; font-weight: 600; color: var(--text); margin: 0 0 8px; }\n"
        ".viewer-fallback-reason { color: var(--text-muted); font-size: 13px; margin: 0 0 20px; }\n"
        ".viewer-fallback-link { font-size: 14px; font-weight: 600; color: var(--accent);\n"
        "  border: 1px solid var(--accent); padding: 8px 18px; border-radius: 7px; }\n"
        "\n"
        "/* JSON tree */\n"
        ".json-key { color: var(--accent); font-weight: 600; }\n"
        ".json-str { color: var(--up); }\n"
        ".json-num { color: #c07a00; }\n"
        ".json-bool { color: #b05cc0; }\n"
        ".json-null { color: var(--text-faint); font-style: italic; }\n"
        ".json-bracket { color: var(--text-faint); cursor: pointer; }\n"
        ".json-list { list-style: none; margin: 0 0 0 18px; padding: 0; }\n"
        "details[open] > summary::before { content: \"\\25BC \"; font-size: 10px; }\n"
        "details:not([open]) > summary::before { content: \"\\25BA \"; font-size: 10px; }\n"
        "\n"
        "/* Sidebar node groups and service rows */\n"
        ".node-group { margin-bottom: 4px; }\n"
        ".node-group-header { display: flex; align-items: center; gap: 7px; padding: 6px 14px 4px; }\n"
        ".node-group-header h2 { margin: 0; font-size: 10.5px; font-weight: 700; text-transform: uppercase;\n"
        "  letter-spacing: .06em; color: var(--text-muted); }\n"
        ".reachable-badge { font-size: 10px; font-weight: 600; color: var(--up);\n"
        "  display: inline-flex; align-items: center; gap: 4px; }\n"
        ".reachable-badge::before { content: \"\"; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }\n"
        ".node-description { font-size: 11px; color: var(--text-faint); }\n"
        ".node-description::before { content: \"\\2014 \"; }\n"
        "\n"
        ".svc-table { width: 100%; border-collapse: collapse; }\n"
        ".svc-table thead { display: none; }\n"
        ".svc-table td { padding: 8px 14px; border-bottom: 1px solid var(--border); vertical-align: middle; }\n"
        ".svc-table tbody tr:last-child td { border-bottom: none; }\n"
        ".svc-table tbody tr.service:hover { background: var(--accent-weak); }\n"
        ".col-name { white-space: nowrap; }\n"
        ".icon { margin-right: 6px; }\n"
        ".service-name { font-weight: 600; font-size: 13px; }\n"
        ".category { margin-left: 7px; font-size: 10px; font-weight: 600; color: var(--accent);\n"
        "  background: var(--accent-weak); padding: 1px 6px; border-radius: 4px; }\n"
        ".col-desc { color: var(--text-muted); font-size: 12px; max-width: 200px; }\n"
        ".tags { margin-left: 6px; }\n"
        ".tag { font-size: 10.5px; color: var(--text-faint); margin-right: 4px; }\n"
        ".tag::before { content: \"#\"; opacity: .6; }\n"
        ".col-status { white-space: nowrap; }\n"
        ".health-pill { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; font-weight: 600;\n"
        "  padding: 2px 7px; border-radius: 4px; text-transform: capitalize; }\n"
        ".health-pill .health-dot { font-size: 6px; line-height: 1; }\n"
        ".health-pill.up { color: var(--up); background: var(--up-bg); }\n"
        ".health-pill.down { color: var(--down); background: var(--down-bg); }\n"
        ".health-pill.unknown { color: var(--unknown); background: var(--unknown-bg); }\n"
        ".col-links { white-space: nowrap; }\n"
        ".link-btn { font-family: var(--mono); font-size: 11px; font-weight: 600; padding: 3px 8px;\n"
        "  border-radius: 5px; margin-right: 4px; display: inline-block; }\n"
        ".link-btn-primary { color: #fff; background: var(--accent); }\n"
        ".link-btn-secondary { color: var(--text-muted); border: 1px solid var(--border-strong); }\n"
        ".col-meta { white-space: nowrap; }\n"
        ".meta { font-size: 11px; color: var(--text-faint); }\n"
        ".owner { margin-right: 8px; }\n"
        ".docs { color: var(--accent); font-weight: 600; }\n"
        ".col-actions { text-align: right; width: 32px; }\n"
        ".remove-service { border: none; background: none; color: var(--text-faint); font-size: 16px;\n"
        "  cursor: pointer; padding: 0 3px; line-height: 1; }\n"
        ".remove-service:hover { color: var(--down); }\n"
        "\n"
        ".empty-state { border: 1px dashed var(--border-strong); border-radius: 10px; padding: 44px;\n"
        "  text-align: center; color: var(--text-muted); background: var(--alt); }\n"
        ".empty-state-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0 0 6px; }\n"
        ".empty-state-hint { margin: 0; font-size: 13px; }\n"
        "\n"
        ".registration-panel { margin: 0; padding: 20px 28px; background: var(--alt);\n"
        "  border-top: 1px solid var(--border); }\n"
        ".panel-title { margin: 0 0 14px; font-size: 12px; font-weight: 700; text-transform: uppercase;\n"
        "  letter-spacing: .05em; color: var(--text-muted); }\n"
        ".write-token-row { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px;\n"
        "  padding-bottom: 16px; border-bottom: 1px solid var(--border); }\n"
        ".write-token-row label { font-size: 12px; color: var(--text-muted); }\n"
        ".write-token-row .hint { color: var(--text-faint); font-weight: 400; }\n"
        "#write-token-input, .add-service-form input { width: 100%; padding: 9px 12px; font-size: 13.5px;\n"
        "  color: var(--text); background: var(--panel); border: 1px solid var(--border-strong); border-radius: 7px; }\n"
        "#write-token-input:focus, .add-service-form input:focus { outline: none; border-color: var(--accent);\n"
        "  box-shadow: 0 0 0 3px var(--accent-weak); }\n"
        ".add-service-form { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }\n"
        ".add-service-form h2 { display: none; }\n"
        ".add-service-form button { padding: 9px 18px; font-size: 13px; font-weight: 600; color: #fff;\n"
        "  background: var(--accent); border: none; border-radius: 7px; cursor: pointer; }\n"
        ".add-service-error { grid-column: 1 / -1; color: var(--down); font-size: 12px; min-height: 1em; }\n"
        "\n"
        "@media (max-width: 720px) {\n"
        "  .workspace { flex-direction: column; height: auto; }\n"
        "  #sidebar { width: 100%; max-width: 100%; border-right: none; border-bottom: 1px solid var(--border); }\n"
        "  #sidebar[data-collapsed=\"true\"] { height: 0; overflow: hidden; }\n"
        "  #viewer { min-height: 60vh; }\n"
        "  .col-links { display: table-cell; }\n"
        "}\n"
        "</style>\n"
    )

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Service Directory</title>"
        + style
        + "</head>"
        "<body>"
        '<div class="page">'
        '<header class="header-band">'
        '<div class="header-top">'
        '<h1 class="brand">Service Directory</h1>'
        f'<div class="node-chip">{identity_html}</div>'
        "</div>"
        "</header>"
        '<div class="workspace">'
        '<nav id="sidebar" data-collapsed="false">'
        '<div class="sidebar-top">'
        '<div class="sidebar-filter-row">'
        '<div class="search-bar">'
        '<input type="text" id="service-filter" '
        'aria-label="Filter services by name, description, tag, or origin" '
        'placeholder="Filter\u2026" />'
        "</div>"
        '<button id="sidebar-collapse-btn" aria-expanded="true" title="Collapse sidebar">'
        "&#x2190;"
        "</button>"
        "</div>"
        "</div>"
        '<div class="sidebar-catalogue" id="sidebar-catalogue">'
        + body
        + empty_state_html
        + "</div>"
        "</nav>"
        '<div id="viewer">'
        '<div class="viewer-default">'
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
        "</div>"
        "</div>"
        "</div>"
        + script
        + "</body></html>"
    )
def _local_services_json(config: RegistryConfig) -> list[dict]:
    """The STATIC, YAML-declared services only -- always tagged
    ``source: "static"`` so the merged catalogue can distinguish them from
    dynamically-registered entries.
    """
    resolved = resolve_all(config)
    # Build a lookup from name -> Service dataclass for view_url/view_kind.
    svc_map = {s.name: s for s in config.services}
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
            # Task 5: pass through optional viewer config (None when unset).
            "view_url": svc_map[svc.name].view_url if svc.name in svc_map else None,
            "view_kind": svc_map[svc.name].view_kind if svc.name in svc_map else None,
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
    embed_probe=None,
    view_proxy=None,
) -> FastAPI:
    """Build the FastAPI app for a given (already-loaded) config.

    ``checker`` is the injectable connectivity-check seam -- production code
    uses the real ``default_checker``; tests pass a stub so no real network
    I/O ever happens in the suite. ``peer_fetcher`` is the equivalent seam
    for federation pull-aggregation against trusted peers. ``http_checker``
    is the equivalent seam for HTTP ``health_url`` checks on dynamic
    registry entries. ``time_fn`` is the injectable clock seam used for
    dynamic-registry TTL/heartbeat expiry (default ``time.time``).
    ``embed_probe`` and ``view_proxy`` are injectable seams for hermetic
    testing of Tasks 3 and 4 -- when set, the real network I/O is bypassed.
    ``embed_probe(url) -> dict`` returns {reachable, embeddable, content_type}.
    ``view_proxy(url) -> dict|None`` returns the parsed JSON body or None for
    SSRF-guarded refusals.
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
    app.state.embed_probe = embed_probe
    app.state.view_proxy = view_proxy

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

    def _target_in_catalogue(url: str) -> bool:
        """SSRF allow-list for the embed-probe / view-proxy endpoints.

        A target is allowed when its (scheme, host, port) matches a catalogue
        entry -- either a resolved service LINK or a service's configured
        ``view_url``. Matching by host:port (not full URL) is deliberate: a
        service legitimately exposes several paths on the same host:port (its
        UI at ``/``, a JSON status at ``/status``), and the admin has already
        declared that host:port as a trusted service. An off-catalogue host or
        port is refused, which is what the SSRF guard exists to enforce.
        """

        def _hostport(u: str):
            try:
                p = urllib.parse.urlparse(u)
            except ValueError:
                return None
            if p.scheme not in ("http", "https") or not p.hostname:
                return None
            return (p.scheme, p.hostname, p.port)

        target = _hostport(url)
        if target is None:
            return False
        allowed: set = set()
        for svc in _all_local_services_json():
            for link in svc.get("links", []):
                hp = _hostport(link.get("url", ""))
                if hp is not None:
                    allowed.add(hp)
            view_url = svc.get("view_url")
            if view_url:
                hp = _hostport(view_url)
                if hp is not None:
                    allowed.add(hp)
        return target in allowed

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

    @app.get("/api/embed-probe")
    def embed_probe(url: str, request: Request) -> JSONResponse:
        """Task 3: Probe whether a catalogue target can be embedded in an iframe.

        SSRF-guarded: only targets whose host:port appear in the resolved
        catalogue for this node are allowed. Returns:
          { reachable: bool, embeddable: bool, content_type: str | null }
        ``embeddable`` is True when neither X-Frame-Options nor a blocking
        CSP frame-ancestors directive is present in the response headers.
        """
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        # Use the injected probe callable if provided (hermetic tests), else default.
        if app.state.embed_probe is not None:
            return JSONResponse(app.state.embed_probe(url))
        # SSRF guard: only allow targets on a catalogue host:port.
        if not _target_in_catalogue(url):
            raise HTTPException(
                status_code=403,
                detail="URL not in catalogue -- SSRF guard",
            )
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "service-directory-embed-probe/1.0")
            with urllib.request.urlopen(req, timeout=4) as resp:
                headers = resp.headers
                ct = headers.get("Content-Type", "") or ""
                xfo = headers.get("X-Frame-Options", "") or ""
                csp = headers.get("Content-Security-Policy", "") or ""
        except Exception:
            return JSONResponse(
                {"reachable": False, "embeddable": False, "content_type": None}
            )
        xfo_blocks = bool(xfo.strip())
        csp_blocks = "frame-ancestors" in csp.lower()
        embeddable = not xfo_blocks and not csp_blocks
        return JSONResponse(
            {
                "reachable": True,
                "embeddable": embeddable,
                "content_type": ct.split(";")[0].strip() if ct else None,
            }
        )

    @app.get("/api/view-proxy")
    def view_proxy(url: str, request: Request) -> Response:
        """Task 4: Proxy a read-only GET for a catalogue target to avoid CORS.

        SSRF-guarded: only targets whose host:port appear in the resolved
        catalogue for this node are allowed. Returns the fetched JSON body.
        Refuses non-catalogue / unsafe targets with 403.
        """
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        # Use the injected proxy callable if provided (hermetic tests).
        if app.state.view_proxy is not None:
            result = app.state.view_proxy(url)
            if result is None:
                raise HTTPException(status_code=403, detail="URL not in catalogue -- SSRF guard")
            return JSONResponse(result)
        # SSRF guard: only allow targets on a catalogue host:port.
        if not _target_in_catalogue(url):
            raise HTTPException(
                status_code=403,
                detail="URL not in catalogue -- SSRF guard",
            )
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "service-directory-view-proxy/1.0")
            with urllib.request.urlopen(req, timeout=8) as resp:
                body = resp.read()
                ct = resp.headers.get("Content-Type", "application/json")
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"upstream fetch failed: {exc}"
            ) from exc
        return Response(content=body, media_type="application/json")


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
