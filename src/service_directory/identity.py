"""Stable device identity, persisted to the config/state directory.

A node's ``device_id`` (a uuid4) is generated once on first run and then
persisted to ``identity.json`` in the state directory so it survives
restarts. This identity is exchanged during the pairing handshake and is
never a secret by itself (it's returned unauthenticated via
``GET /api/instance-info``).
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

IDENTITY_FILENAME = "identity.json"


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str


def _identity_path(state_dir: str) -> str:
    return os.path.join(state_dir, IDENTITY_FILENAME)


def load_or_create_identity(state_dir: str) -> DeviceIdentity:
    """Load the persisted device identity, creating one on first run.

    ``state_dir`` is created if missing. The file is written only once;
    subsequent calls read the same ``device_id`` back.
    """
    os.makedirs(state_dir, exist_ok=True)
    path = _identity_path(state_dir)

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            device_id = data.get("device_id")
            if isinstance(device_id, str) and device_id:
                return DeviceIdentity(device_id=device_id)
        except (json.JSONDecodeError, OSError):
            pass  # fall through and regenerate below

    device_id = str(uuid.uuid4())
    _write_identity(path, device_id)
    return DeviceIdentity(device_id=device_id)


def _write_identity(path: str, device_id: str) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"device_id": device_id}, f)
    os.replace(tmp_path, path)


__all__ = ["DeviceIdentity", "load_or_create_identity"]
