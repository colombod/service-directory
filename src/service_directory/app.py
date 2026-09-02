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
        owner_html = f'<span class="owner">{html_escape.escape(svc["owner"])}</span>'
    # Defense in depth: docs_url can arrive not just from local config
    # (already validated in config.py) but also relayed verbatim from a
    # federated peer's /api/services/local response (see federation.py
    # aggregate_services), which never passes through that parser. Only
    # ever render it as a clickable link if it's an allow-listed http(s)
    # scheme -- otherwise drop the link but keep the rest of the card intact.
    docs_html = ""
    docs_url = svc.get("docs_url")
    if docs_url and is_safe_docs_url(docs_url):
        docs_html = f'<a class="docs" href="{html_escape.escape(docs_url)}">docs</a>'
    origin = svc.get("origin") or ""
    # Defense in depth: a resolved link's URL can arrive not just from
    # local, admin-controlled config but also from a caller-supplied
    # dynamic registration ("url"/"port" fields, see _dynamic_service_json)
    # or relayed verbatim from a federated peer. Apply the SAME allow-listed
    # http(s)-scheme check used for docs_url before ever rendering a link as
    # a clickable href -- otherwise a stored `javascript:`-scheme value
    # would execute in the dashboard origin when clicked. Drop the
    # individual unsafe link but keep the rest of the card intact.
    links_html = "".join(
        f'<a href="{html_escape.escape(link["url"])}">{html_escape.escape(link["label"])}</a>'
        for link in svc["links"]
        if is_safe_docs_url(link["url"])
    )
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
    return (
        f'<li class="service" data-name="{name}" data-search="{search_blob}">'
        f'<span class="health-dot" data-health-name="{name}">&#9679;</span>'
        f"{icon_html}<h3>{name}</h3>{category_html}"
        f"{remove_html}"
        f"{desc_html}"
        f"{tags_html}"
        f'<div class="meta">{owner_html}{docs_html}</div>'
        f'<div class="links">{links_html}</div>'
        f"</li>"
    )


def _render_html(services: list[dict], node_info: list[dict] | None = None) -> str:
    """Render the single self-contained dashboard page.

    Services are grouped BY ORIGIN NODE (a section per node, header = node
    name + description when known). A plain inline-JS search/filter input
    filters cards by name/description/tag/origin. A health dot per service
    is rendered as a placeholder and updated client-side from /api/health --
    no build step, no external/CDN assets.
    """
    node_info = node_info or []
    node_descriptions = {n["name"]: n.get("description") for n in node_info}

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
        if desc:
            desc_html = f'<p class="node-description">{html_escape.escape(desc)}</p>'
        cards = "\n".join(_service_card_html(svc) for svc in group)
        sections.append(
            f'<section class="node-group" data-origin="{origin_name}">'
            f"<h2>{origin_name}</h2>"
            f"{desc_html}"
            f'<ul class="services">{cards}</ul>'
            f"</section>"
        )
    body = "\n".join(sections)

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
        if (!dot) return;
        var status = data[name];
        dot.className = 'health-dot ' + (status === 'up' ? 'up' : 'down');
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
.health-dot { color: #999; margin-right: 0.35em; }
.health-dot.up { color: #2ecc71; }
.health-dot.down { color: #e74c3c; }
.node-group { margin-bottom: 1.5em; }
.tag { display: inline-block; background: #eee; border-radius: 3px;
       padding: 0 0.4em; margin-right: 0.3em; font-size: 0.85em; }
</style>
"""

    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Service Directory</title>"
        f"{style}"
        "</head>"
        "<body><h1>Service Directory</h1>"
        '<div class="write-token-row">'
        '<label for="write-token-input">Write token '
        "(only needed for remote/tailnet mutations, or when the server "
        "requires one even on localhost):</label> "
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
        '<input type="text" id="service-filter" '
        'placeholder="Filter by name, description, tag, or origin\u2026" />'
        f"{body}"
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
                    "url": f"http://{addr.host}:{entry.port}{path}",
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
