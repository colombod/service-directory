"""FastAPI app: GET /, GET /api/services, GET /api/health, plus Block 2
federation endpoints (instance-info, pairing handshake).
"""

from __future__ import annotations

import html as html_escape
import secrets
import socket

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from . import __version__
from .auth import require_admin, require_read_access
from .config import ConfigError, RegistryConfig, load_config, resolve_state_dir
from .federation import (
    DEFAULT_PEER_TIMEOUT_SECONDS,
    PeerFetcher,
    aggregate_services,
    default_peer_fetcher,
)
from .health import Checker, check_services, default_checker
from .identity import load_or_create_identity
from .pairing import PairingCodeStore
from .trust_store import PeerRecord, load_peers, upsert_peer
from .urls import resolve_all


def _local_name(config: RegistryConfig) -> str:
    if config.federation.name:
        return config.federation.name
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover - defensive
        return "local"


def _render_html(services: list[dict]) -> str:
    rows = []
    for svc in services:
        name = html_escape.escape(svc["name"])
        desc_html = ""
        if svc.get("description"):
            desc_html = (
                f'<p class="description">{html_escape.escape(svc["description"])}</p>'
            )
        origin_html = ""
        if svc.get("origin"):
            origin_html = (
                f'<span class="origin">{html_escape.escape(svc["origin"])}</span>'
            )
        links_html = "".join(
            f'<a href="{html_escape.escape(link["url"])}">{html_escape.escape(link["label"])}</a>'
            for link in svc["links"]
        )
        rows.append(
            f'<li class="service">'
            f"<h2>{name}{origin_html}</h2>"
            f"{desc_html}"
            f'<div class="links">{links_html}</div>'
            f"</li>"
        )
    body = "\n".join(rows)
    return (
        "<!DOCTYPE html>"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Service Directory</title></head>"
        f"<body><h1>Service Directory</h1><ul>{body}</ul></body></html>"
    )


def _local_services_json(config: RegistryConfig) -> list[dict]:
    resolved = resolve_all(config)
    return [
        {
            "name": svc.name,
            "description": svc.description,
            "links": [
                {"label": link.label, "host": link.host, "url": link.url}
                for link in svc.links
            ],
        }
        for svc in resolved
    ]


class PairRequest(BaseModel):
    device_id: str
    name: str
    base_url: str
    code: str


def create_app(
    config: RegistryConfig,
    checker: Checker = default_checker,
    peer_fetcher: PeerFetcher = default_peer_fetcher,
    peer_timeout: float = DEFAULT_PEER_TIMEOUT_SECONDS,
) -> FastAPI:
    """Build the FastAPI app for a given (already-loaded) config.

    ``checker`` is the injectable connectivity-check seam -- production code
    uses the real ``default_checker``; tests pass a stub so no real network
    I/O ever happens in the suite. ``peer_fetcher`` is the equivalent seam
    for federation pull-aggregation against trusted peers.
    """
    app = FastAPI(title="service-directory")
    app.state.config = config
    app.state.checker = checker
    app.state.peer_fetcher = peer_fetcher
    app.state.peer_timeout = peer_timeout
    app.state.state_dir = resolve_state_dir(config)
    app.state.local_name = _local_name(config)
    app.state.pairing_store = PairingCodeStore()

    def _aggregated_services() -> list[dict]:
        local = _local_services_json(config)
        if not config.federation.enabled:
            # Federation off: still tag origin so the JSON shape is stable,
            # but never attempt any peer I/O.
            return [dict(svc, origin=app.state.local_name) for svc in local]
        peers = load_peers(app.state.state_dir)
        result = aggregate_services(
            local_name=app.state.local_name,
            local_services=local,
            peers=peers,
            fetcher=app.state.peer_fetcher,
            timeout=app.state.peer_timeout,
        )
        return result.services

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        services = _aggregated_services()
        return HTMLResponse(_render_html(services))

    @app.get("/api/services")
    def api_services(request: Request) -> JSONResponse:
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        services = _aggregated_services()
        return JSONResponse(services)

    @app.get("/api/health")
    def api_health(request: Request) -> JSONResponse:
        require_read_access(
            request, app.state.state_dir, config.federation.require_read_token
        )
        resolved = resolve_all(app.state.config)
        results = check_services(resolved, checker=app.state.checker)
        return JSONResponse(results)

    @app.get("/api/instance-info")
    def instance_info() -> JSONResponse:
        """Unauthenticated. Returns ONLY non-secret identity fields -- no
        tokens, no peer list, no config internals.
        """
        identity = load_or_create_identity(app.state.state_dir)
        return JSONResponse(
            {
                "name": app.state.local_name,
                "device_id": identity.device_id,
                "version": __version__,
                "federation_enabled": config.federation.enabled,
            }
        )

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
