"""Pure URL resolution: services x host_addresses -> resolved links.

No I/O here -- this module is pure functions over the config data, kept
separate so it is trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import HostAddress, RegistryConfig, Service


@dataclass(frozen=True)
class ResolvedLink:
    label: str
    host: str
    url: str


@dataclass(frozen=True)
class ResolvedService:
    name: str
    description: str | None
    links: list[ResolvedLink]


def build_url(host: str, port: int, path: str = "/") -> str:
    """Construct ``http://{host}:{port}{path}``, defaulting path to '/'."""
    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    return f"http://{host}:{port}{path}"


def resolve_service(
    service: Service, host_addresses: list[HostAddress]
) -> ResolvedService:
    """Resolve one service against all host addresses (order preserved)."""
    links = [
        ResolvedLink(
            label=addr.label,
            host=addr.host,
            url=build_url(addr.host, service.port, service.path),
        )
        for addr in host_addresses
    ]
    return ResolvedService(
        name=service.name, description=service.description, links=links
    )


def resolve_all(config: RegistryConfig) -> list[ResolvedService]:
    """Resolve every service x host_address pair.

    Host address order is taken directly from config, which is expected to be
    tailnet-first per the spec (the config author/sample controls ordering;
    this function preserves it faithfully rather than re-sorting).
    """
    return [resolve_service(svc, config.host_addresses) for svc in config.services]
