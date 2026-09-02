"""Config loading for service-directory.

Config is the source of truth (not OS-discovered at runtime). It is loaded
from a YAML file whose path comes from the ``SERVICE_REGISTRY_CONFIG``
environment variable (or an explicit path passed to :func:`load_config`).

Shape::

    host_addresses:
      - {label: "Tailnet", host: "100.111.191.22"}   # tailnet-first
      - {label: "LAN",     host: "192.168.1.86"}
    services:
      - {name: "Resolve", port: 8080, path: "/", description: "..."}
      - {name: "muxplex", port: 8088}

A malformed config raises :class:`ConfigError` with a clear, human-readable
message -- never an unhandled stack trace.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

import yaml

DEFAULT_CONFIG_ENV_VAR = "SERVICE_REGISTRY_CONFIG"

# docs_url is rendered as a clickable <a href="..."> on the dashboard (see
# app.py::_service_card_html) and -- via federation -- may also be relayed
# from a peer's /api/services/local response rather than only from local,
# admin-controlled config. Restrict to a scheme allow-list so a
# `javascript:`/`data:`/`vbscript:` URI can never be rendered as a live
# link (stored-XSS-via-metadata). Enforced here (fail closed on bad local
# config) AND defensively again at render time in app.py (since peer-relayed
# values never pass through this parser).
ALLOWED_DOCS_URL_SCHEMES = {"http", "https"}


def is_safe_docs_url(url: str) -> bool:
    """True iff ``url`` parses to an allow-listed scheme (http/https).

    Used both to fail closed on malformed local config (see
    :func:`_parse_service`) and defensively at render time for
    federation-relayed service metadata that never passes through this
    parser at all.
    """
    try:
        scheme = urlparse(url).scheme.lower()
    except ValueError:
        return False
    return scheme in ALLOWED_DOCS_URL_SCHEMES


class ConfigError(Exception):
    """Raised when the service registry config is missing or malformed."""


@dataclass(frozen=True)
class HostAddress:
    label: str
    host: str


@dataclass(frozen=True)
class Service:
    name: str
    port: int
    path: str = "/"
    description: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    icon: str | None = None
    owner: str | None = None
    docs_url: str | None = None


@dataclass(frozen=True)
class FederationConfig:
    """Local-only federation settings (Block 2).

    Every node keeps ONLY its own local config -- there is no static peer
    list here. Trusted peers are discovered/recorded entirely via the
    pairing handshake and persisted to ``state_dir`` (identity.json,
    peers.json), never in this YAML file.
    """

    enabled: bool = False
    name: str = ""
    base_url: str = ""
    state_dir: str | None = None
    require_read_token: bool = False
    description: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class RegistryConfig:
    host_addresses: list[HostAddress] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    federation: FederationConfig = field(default_factory=FederationConfig)


def _require_str(value: object, field_name: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"Invalid config: {context} field '{field_name}' must be a "
            f"non-empty string (got {value!r})"
        )
    return value


def _require_int(value: object, field_name: str, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"Invalid config: {context} field '{field_name}' must be an "
            f"integer (got {value!r})"
        )
    return value


def _parse_host_address(raw: object, index: int) -> HostAddress:
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Invalid config: host_addresses[{index}] must be a mapping "
            f"with 'label' and 'host' keys (got {raw!r})"
        )
    context = f"host_addresses[{index}]"
    label = _require_str(raw.get("label"), "label", context)
    host = _require_str(raw.get("host"), "host", context)
    return HostAddress(label=label, host=host)


def _parse_service(raw: object, index: int) -> Service:
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Invalid config: services[{index}] must be a mapping with "
            f"'name' and 'port' keys (got {raw!r})"
        )
    context = f"services[{index}]"
    name = _require_str(raw.get("name"), "name", context)
    port = _require_int(raw.get("port"), "port", context)
    path = raw.get("path", "/")
    if path is None:
        path = "/"
    if not isinstance(path, str):
        raise ConfigError(
            f"Invalid config: {context} field 'path' must be a string (got {path!r})"
        )
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise ConfigError(
            f"Invalid config: {context} field 'description' must be a "
            f"string (got {description!r})"
        )
    category = raw.get("category")
    if category is not None and not isinstance(category, str):
        raise ConfigError(
            f"Invalid config: {context} field 'category' must be a "
            f"string (got {category!r})"
        )
    tags = raw.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        raise ConfigError(
            f"Invalid config: {context} field 'tags' must be a list (got {tags!r})"
        )
    for i, tag in enumerate(tags):
        if not isinstance(tag, str):
            raise ConfigError(
                f"Invalid config: {context} field 'tags[{i}]' must be a "
                f"string (got {tag!r})"
            )
    icon = raw.get("icon")
    if icon is not None and not isinstance(icon, str):
        raise ConfigError(
            f"Invalid config: {context} field 'icon' must be a string (got {icon!r})"
        )
    owner = raw.get("owner")
    if owner is not None and not isinstance(owner, str):
        raise ConfigError(
            f"Invalid config: {context} field 'owner' must be a string (got {owner!r})"
        )
    docs_url = raw.get("docs_url")
    if docs_url is not None and not isinstance(docs_url, str):
        raise ConfigError(
            f"Invalid config: {context} field 'docs_url' must be a "
            f"string (got {docs_url!r})"
        )
    if docs_url is not None and not is_safe_docs_url(docs_url):
        raise ConfigError(
            f"Invalid config: {context} field 'docs_url' must use an "
            f"http(s) scheme (got {docs_url!r})"
        )
    return Service(
        name=name,
        port=port,
        path=path,
        description=description,
        category=category,
        tags=list(tags),
        icon=icon,
        owner=owner,
        docs_url=docs_url,
    )


def _parse_federation(raw: object) -> FederationConfig:
    if raw is None:
        return FederationConfig()
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Invalid config: 'federation' must be a mapping (got {type(raw).__name__})"
        )
    context = "federation"
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(
            f"Invalid config: {context} field 'enabled' must be a boolean (got {enabled!r})"
        )
    name = raw.get("name", "")
    if not isinstance(name, str):
        raise ConfigError(
            f"Invalid config: {context} field 'name' must be a string (got {name!r})"
        )
    base_url = raw.get("base_url", "")
    if not isinstance(base_url, str):
        raise ConfigError(
            f"Invalid config: {context} field 'base_url' must be a string (got {base_url!r})"
        )
    state_dir = raw.get("state_dir")
    if state_dir is not None and not isinstance(state_dir, str):
        raise ConfigError(
            f"Invalid config: {context} field 'state_dir' must be a string (got {state_dir!r})"
        )
    require_read_token = raw.get("require_read_token", False)
    if not isinstance(require_read_token, bool):
        raise ConfigError(
            f"Invalid config: {context} field 'require_read_token' must be a "
            f"boolean (got {require_read_token!r})"
        )
    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise ConfigError(
            f"Invalid config: {context} field 'description' must be a "
            f"string (got {description!r})"
        )
    role = raw.get("role")
    if role is not None and not isinstance(role, str):
        raise ConfigError(
            f"Invalid config: {context} field 'role' must be a string (got {role!r})"
        )
    return FederationConfig(
        enabled=enabled,
        name=name,
        base_url=base_url,
        state_dir=state_dir,
        require_read_token=require_read_token,
        description=description,
        role=role,
    )


def parse_config(raw_yaml_text: str) -> RegistryConfig:
    """Parse YAML text into a :class:`RegistryConfig`.

    Raises :class:`ConfigError` on any malformed input -- never propagates a
    raw YAML/parse exception.
    """
    try:
        data = yaml.safe_load(raw_yaml_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid config: not valid YAML ({exc})") from exc

    if data is None:
        raise ConfigError("Invalid config: file is empty")

    if not isinstance(data, dict):
        raise ConfigError(
            f"Invalid config: top-level document must be a mapping "
            f"(got {type(data).__name__})"
        )

    raw_hosts = data.get("host_addresses")
    if raw_hosts is None:
        raise ConfigError("Invalid config: missing required key 'host_addresses'")
    if not isinstance(raw_hosts, list):
        raise ConfigError(
            f"Invalid config: 'host_addresses' must be a list "
            f"(got {type(raw_hosts).__name__})"
        )
    if len(raw_hosts) == 0:
        raise ConfigError("Invalid config: 'host_addresses' must not be empty")

    raw_services = data.get("services")
    if raw_services is None:
        raise ConfigError("Invalid config: missing required key 'services'")
    if not isinstance(raw_services, list):
        raise ConfigError(
            f"Invalid config: 'services' must be a list "
            f"(got {type(raw_services).__name__})"
        )
    if len(raw_services) == 0:
        raise ConfigError("Invalid config: 'services' must not be empty")

    host_addresses = [_parse_host_address(h, i) for i, h in enumerate(raw_hosts)]
    services = [_parse_service(s, i) for i, s in enumerate(raw_services)]
    federation = _parse_federation(data.get("federation"))

    return RegistryConfig(
        host_addresses=host_addresses, services=services, federation=federation
    )


STATE_DIR_ENV_VAR = "SERVICE_REGISTRY_STATE_DIR"
DEFAULT_STATE_DIR = os.path.join(
    os.path.expanduser("~"), ".local", "state", "service-directory"
)


def resolve_state_dir(config: RegistryConfig) -> str:
    """Where federation state (identity.json, peers.json) lives.

    Precedence: explicit ``federation.state_dir`` in config > the
    ``SERVICE_REGISTRY_STATE_DIR`` env var > a per-user default path.
    """
    if config.federation.state_dir:
        return config.federation.state_dir
    return os.environ.get(STATE_DIR_ENV_VAR, DEFAULT_STATE_DIR)


def load_config(path: str | None = None) -> RegistryConfig:
    """Load and parse the registry config from ``path``.

    If ``path`` is ``None``, it is read from the ``SERVICE_REGISTRY_CONFIG``
    environment variable. Raises :class:`ConfigError` with a clear message on
    any failure (missing env var, missing file, malformed YAML/shape).
    """
    if path is None:
        path = os.environ.get(DEFAULT_CONFIG_ENV_VAR)
        if not path:
            raise ConfigError(
                f"Invalid config: environment variable "
                f"'{DEFAULT_CONFIG_ENV_VAR}' is not set"
            )

    try:
        with open(path, encoding="utf-8") as f:
            raw_text = f.read()
    except OSError as exc:
        raise ConfigError(f"Invalid config: cannot read file '{path}' ({exc})") from exc

    return parse_config(raw_text)
