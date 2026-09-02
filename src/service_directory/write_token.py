"""Write-token store (write_token.json), persisted to the state dir.

A single, node-wide bearer token that authorizes MUTATIONS to the dynamic
service registry (``POST /api/services``, ``DELETE /api/services/{name}``,
``POST /api/services/{name}/heartbeat``). Unlike per-peer trust-store tokens
(one per federated peer, for federation reads/pairing), this is a single
shared secret an operator mints once via ``service-directory token
issue-write`` and hands to agents/scripts/remote browsers that need to
register services.

Follows the exact same on-disk pattern as ``trust_store.py``/``peers.json``:
atomic write, forced ``0600`` file mode, read fresh from disk on every
access (never cached), missing/corrupt file treated as "no token set" rather
than a crash.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets

WRITE_TOKEN_FILENAME = "write_token.json"


def _write_token_path(state_dir: str) -> str:
    return os.path.join(state_dir, WRITE_TOKEN_FILENAME)


def load_write_token(state_dir: str) -> str | None:
    """Read the persisted write token fresh from disk.

    Never raises: a missing or corrupt file is treated as "no token set"
    rather than a crash.
    """
    path = _write_token_path(state_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    token = data.get("token")
    if isinstance(token, str) and token:
        return token
    return None


def _save_write_token(state_dir: str, token: str) -> None:
    """Persist the write token, forcing file mode 0600 (secret inside)."""
    os.makedirs(state_dir, exist_ok=True)
    path = _write_token_path(state_dir)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def issue_write_token(state_dir: str) -> str:
    """Mint a new write token, persist it (0600, overwriting any existing
    one -- this doubles as rotation), and return it.
    """
    token = secrets.token_urlsafe(32)
    _save_write_token(state_dir, token)
    return token


def verify_write_token(state_dir: str, token: str | None) -> bool:
    """Constant-time-safe check of ``token`` against the persisted write
    token using ``hmac.compare_digest`` (never a plain ``==``, so a
    wrong/absent token never leaks timing information).
    """
    if not token:
        return False
    stored = load_write_token(state_dir)
    if not stored:
        return False
    return hmac.compare_digest(stored, token)


__all__ = [
    "WRITE_TOKEN_FILENAME",
    "issue_write_token",
    "load_write_token",
    "verify_write_token",
]
