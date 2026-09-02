"""Per-peer trust store (peers.json), persisted to the state/config dir.

Each trusted peer has its OWN token (not one shared key) so a single peer
can be revoked without affecting any other peer relationship. The store is
always read fresh from disk on every access (never cached in memory) so
CLI-driven changes (``peers remove`` etc.) take effect on the very next
request without a server restart.

File mode is forced to ``0600`` (owner read/write only) since it holds
bearer tokens.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

PEERS_FILENAME = "peers.json"


@dataclass(frozen=True)
class PeerRecord:
    """A trusted peer node: its name, identity, address, and shared per-peer token."""

    name: str
    device_id: str
    base_url: str
    token: str


def _peers_path(state_dir: str) -> str:
    return os.path.join(state_dir, PEERS_FILENAME)


def load_peers(state_dir: str) -> list[PeerRecord]:
    """Read the trust store fresh from disk. Never raises: a missing or
    corrupt file is treated as "no trusted peers yet" rather than a crash.
    """
    path = _peers_path(state_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []

    peers: list[PeerRecord] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            peers.append(
                PeerRecord(
                    name=item["name"],
                    device_id=item["device_id"],
                    base_url=item["base_url"],
                    token=item["token"],
                )
            )
        except KeyError:
            continue
    return peers


def save_peers(state_dir: str, peers: list[PeerRecord]) -> None:
    """Persist the trust store, forcing file mode 0600 (secrets inside)."""
    os.makedirs(state_dir, exist_ok=True)
    path = _peers_path(state_dir)
    tmp_path = f"{path}.tmp"
    payload = [asdict(p) for p in peers]
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def upsert_peer(state_dir: str, peer: PeerRecord) -> None:
    """Add ``peer``, replacing any existing record with the same name."""
    peers = [p for p in load_peers(state_dir) if p.name != peer.name]
    peers.append(peer)
    save_peers(state_dir, peers)


def remove_peer(state_dir: str, name: str) -> bool:
    """Remove the peer named ``name``. Returns True if a peer was removed."""
    peers = load_peers(state_dir)
    filtered = [p for p in peers if p.name != name]
    removed = len(filtered) != len(peers)
    if removed:
        save_peers(state_dir, filtered)
    return removed


def find_peer_by_name(state_dir: str, name: str) -> PeerRecord | None:
    for p in load_peers(state_dir):
        if p.name == name:
            return p
    return None


def find_peer_by_token(state_dir: str, token: str | None) -> PeerRecord | None:
    """Constant-time-safe lookup: compares ``token`` against every stored
    peer token using ``hmac.compare_digest`` so a wrong/absent token never
    leaks timing information about which (if any) peer it partially matches.
    """
    import hmac

    if not token:
        return None
    match: PeerRecord | None = None
    for p in load_peers(state_dir):
        if hmac.compare_digest(p.token, token):
            match = p
    return match


__all__ = [
    "PeerRecord",
    "find_peer_by_name",
    "find_peer_by_token",
    "load_peers",
    "remove_peer",
    "save_peers",
    "upsert_peer",
]
