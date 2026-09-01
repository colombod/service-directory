"""FastAPI app: GET /, GET /api/services, GET /api/health."""

from __future__ import annotations

import html as html_escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .config import ConfigError, RegistryConfig, load_config
from .health import Checker, check_services, default_checker
from .urls import ResolvedService, resolve_all


def _render_html(resolved: list[ResolvedService]) -> str:
    rows = []
    for svc in resolved:
        name = html_escape.escape(svc.name)
        desc_html = ""
        if svc.description:
            desc_html = (
                f'<p class="description">{html_escape.escape(svc.description)}</p>'
            )
        links_html = "".join(
            f'<a href="{html_escape.escape(link.url)}">{html_escape.escape(link.label)}</a>'
            for link in svc.links
        )
        rows.append(
            f'<li class="service">'
            f"<h2>{name}</h2>"
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


def _services_json(resolved: list[ResolvedService]) -> list[dict]:
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


def create_app(
    config: RegistryConfig,
    checker: Checker = default_checker,
) -> FastAPI:
    """Build the FastAPI app for a given (already-loaded) config.

    ``checker`` is the injectable connectivity-check seam -- production code
    uses the real ``default_checker``; tests pass a stub so no real network
    I/O ever happens in the suite.
    """
    app = FastAPI(title="service-directory")
    app.state.config = config
    app.state.checker = checker

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        resolved = resolve_all(app.state.config)
        return HTMLResponse(_render_html(resolved))

    @app.get("/api/services")
    def api_services() -> JSONResponse:
        resolved = resolve_all(app.state.config)
        return JSONResponse(_services_json(resolved))

    @app.get("/api/health")
    def api_health() -> JSONResponse:
        resolved = resolve_all(app.state.config)
        results = check_services(resolved, checker=app.state.checker)
        return JSONResponse(results)

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
