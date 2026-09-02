"""Pairing handshake: short-lived, one-time pairing codes.

``service-directory token issue`` (or ``POST /api/federation/pairing-code``,
localhost/admin only) mints a pairing code with a short TTL (~10 minutes).
Another node presents that code to ``POST /api/federation/pair`` along with
its own identity; the receiving node validates the code (one-time,
unexpired), mints a long-lived per-peer token for the caller, records the
caller in its trust-store, and returns its own identity + that token --
mutual per-peer trust is established once the caller does the same locally.

Pairing codes are kept in-memory only (per process) -- they are single-use,
short-lived, and never need to survive a restart the way the durable
identity/trust-store data does.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass

DEFAULT_PAIRING_TTL_SECONDS = 10 * 60


@dataclass
class PairingCode:
    code: str
    expires_at: float
    used: bool = False


class PairingCodeStore:
    """In-memory, one-time pairing code store.

    Injectable ``time_fn`` seam so tests can control expiry deterministically
    without real sleeping.
    """

    def __init__(self, time_fn=time.monotonic) -> None:
        self._time_fn = time_fn
        self._codes: dict[str, PairingCode] = {}

    def issue(self, ttl_seconds: float = DEFAULT_PAIRING_TTL_SECONDS) -> str:
        code = secrets.token_urlsafe(24)
        self._codes[code] = PairingCode(
            code=code, expires_at=self._time_fn() + ttl_seconds
        )
        return code

    def redeem(self, code: str) -> bool:
        """Validate and consume ``code``. Returns True exactly once for a
        valid, unexpired code -- any subsequent redemption of the same code
        (or an unknown/expired one) returns False.
        """
        entry = self._codes.get(code)
        if entry is None:
            return False
        if entry.used:
            return False
        if self._time_fn() >= entry.expires_at:
            return False
        entry.used = True
        return True


__all__ = ["DEFAULT_PAIRING_TTL_SECONDS", "PairingCode", "PairingCodeStore"]
