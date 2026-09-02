"""Dynamic service registry (registry.json), persisted to the state dir.

Complements the static, read-only YAML ``services:`` baseline with a
runtime registry that agents write via the HTTP API and a human manages
from the dashboard. Follows the exact same on-disk pattern as
``trust_store.py``/``peers.json``: atomic write, forced ``0600`` file mode,
read fresh from disk on every access (never cached), missing/corrupt file
treated as "empty registry" rather than a crash.

Liveness model:

- **Persistent** (default, no ``ttl``): the entry survives forever until an
  explicit ``DELETE``.
- **Heartbeat-based** (``ttl`` given, seconds): the entry is considered
  "fresh" as long as a heartbeat has been received within the last ``ttl``
  seconds. Once no heartbeat has arrived within ``ttl``, the entry is
  STALE and is pruned the next time the registry is read (see
  :func:`load_registry`).

The clock is an injectable seam (``time_fn``, default ``time.time``) so
tests can control expiry deterministically without real sleeping.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field

REGISTRY_FILENAME = "registry.json"


@dataclass(frozen=True)
class DynamicService:
    """One dynamically-registered service entry."""

    name: str
    port: int | None = None
    url: str | None = None
    path: str = "/"
    description: str | None = None
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    icon: str | None = None
    owner: str | None = None
    docs_url: str | None = None
    health_url: str | None = None
    ttl: float | None = None
    registered_at: float = 0.0
    last_heartbeat: float = 0.0


def _registry_path(state_dir: str) -> str:
    return os.path.join(state_dir, REGISTRY_FILENAME)


def is_expired(entry: DynamicService, now: float) -> bool:
    """True iff ``entry`` has a ttl AND no heartbeat has arrived within it.

    Persistent entries (``ttl`` is ``None``) are never expired.
    """
    if entry.ttl is None:
        return False
    return (now - entry.last_heartbeat) > entry.ttl


def _entry_from_dict(item: dict) -> DynamicService | None:
    if not isinstance(item, dict) or "name" not in item:
        return None
    try:
        return DynamicService(
            name=item["name"],
            port=item.get("port"),
            url=item.get("url"),
            path=item.get("path") or "/",
            description=item.get("description"),
            category=item.get("category"),
            tags=list(item.get("tags") or []),
            icon=item.get("icon"),
            owner=item.get("owner"),
            docs_url=item.get("docs_url"),
            health_url=item.get("health_url"),
            ttl=item.get("ttl"),
            registered_at=item.get("registered_at", 0.0),
            last_heartbeat=item.get("last_heartbeat", 0.0),
        )
    except (KeyError, TypeError):
        return None


def _load_raw(state_dir: str) -> list[DynamicService]:
    """Read the registry fresh from disk, WITHOUT pruning. Never raises."""
    path = _registry_path(state_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []

    entries: list[DynamicService] = []
    for item in data:
        entry = _entry_from_dict(item)
        if entry is not None:
            entries.append(entry)
    return entries


def save_registry(state_dir: str, entries: list[DynamicService]) -> None:
    """Persist the registry, forcing file mode 0600 (atomic replace)."""
    os.makedirs(state_dir, exist_ok=True)
    path = _registry_path(state_dir)
    tmp_path = f"{path}.tmp"
    payload = [asdict(e) for e in entries]
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def load_registry(
    state_dir: str, time_fn=time.time, prune: bool = True
) -> list[DynamicService]:
    """Read the registry fresh from disk, pruning any expired (ttl,
    heartbeat-stale) entries as a side effect (persisted back so the pruning
    sticks and subsequent reads don't need to redo the work).
    """
    entries = _load_raw(state_dir)
    if not prune:
        return entries

    now = time_fn()
    live = [e for e in entries if not is_expired(e, now)]
    if len(live) != len(entries):
        save_registry(state_dir, live)
    return live


def find_dynamic_service(
    state_dir: str, name: str, time_fn=time.time
) -> DynamicService | None:
    for entry in load_registry(state_dir, time_fn=time_fn):
        if entry.name == name:
            return entry
    return None


def register_service(
    state_dir: str, entry: DynamicService, time_fn=time.time
) -> DynamicService:
    """Register/UPSERT a dynamic service entry (by name).

    Sets ``registered_at``/``last_heartbeat`` to "now" (via ``time_fn``) on
    a fresh registration; a re-registration (upsert) of an existing name
    also refreshes both timestamps, treating it like an implicit heartbeat.
    Does NOT check for static-name collisions -- that is the caller's
    (``app.py``) responsibility, since only it knows the static config.
    """
    now = time_fn()
    stamped = DynamicService(
        name=entry.name,
        port=entry.port,
        url=entry.url,
        path=entry.path,
        description=entry.description,
        category=entry.category,
        tags=list(entry.tags),
        icon=entry.icon,
        owner=entry.owner,
        docs_url=entry.docs_url,
        health_url=entry.health_url,
        ttl=entry.ttl,
        registered_at=now,
        last_heartbeat=now,
    )
    entries = [
        e for e in load_registry(state_dir, time_fn=time_fn) if e.name != entry.name
    ]
    entries.append(stamped)
    save_registry(state_dir, entries)
    return stamped


def deregister_service(state_dir: str, name: str, time_fn=time.time) -> bool:
    """Remove the dynamic entry named ``name``. Returns True if removed."""
    entries = load_registry(state_dir, time_fn=time_fn)
    filtered = [e for e in entries if e.name != name]
    removed = len(filtered) != len(entries)
    if removed:
        save_registry(state_dir, filtered)
    return removed


def heartbeat_service(
    state_dir: str, name: str, time_fn=time.time
) -> DynamicService | None:
    """Refresh ``last_heartbeat`` for the named entry. Returns the updated
    entry, or ``None`` if no dynamic entry with that name exists (already
    pruned or never registered).
    """
    now = time_fn()
    entries = load_registry(state_dir, time_fn=time_fn)
    updated: DynamicService | None = None
    new_entries: list[DynamicService] = []
    for e in entries:
        if e.name == name:
            updated = DynamicService(
                name=e.name,
                port=e.port,
                url=e.url,
                path=e.path,
                description=e.description,
                category=e.category,
                tags=list(e.tags),
                icon=e.icon,
                owner=e.owner,
                docs_url=e.docs_url,
                health_url=e.health_url,
                ttl=e.ttl,
                registered_at=e.registered_at,
                last_heartbeat=now,
            )
            new_entries.append(updated)
        else:
            new_entries.append(e)
    if updated is not None:
        save_registry(state_dir, new_entries)
    return updated


__all__ = [
    "REGISTRY_FILENAME",
    "DynamicService",
    "deregister_service",
    "find_dynamic_service",
    "heartbeat_service",
    "is_expired",
    "load_registry",
    "register_service",
    "save_registry",
]
