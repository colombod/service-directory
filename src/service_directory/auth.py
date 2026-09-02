"""Authentication/authorization for federation endpoints.

Two independent mechanisms:

- **Per-peer bearer tokens**: verified with ``hmac.compare_digest`` against
  the trust store (read fresh per request -- never cached). Each peer has
  its own token so a single peer is revocable without affecting others.
- **Localhost admin bypass**: based on the SOCKET-level client IP
  (``request.client.host in {"127.0.0.1", "::1"}``) -- this is unforgeable
  (it comes from the TCP connection itself, not a header a remote client
  could spoof), unlike e.g. ``X-Forwarded-For``.

Read endpoints (``/``, ``/api/services``, ``/api/services/local``,
``/api/health``) are open by
default; the ``require_read_token`` config flag flips them to
bearer-required. Admin endpoints (pairing-code issuance, peer management)
always require either the localhost bypass or a valid peer bearer token.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

LOCALHOST_IPS = {"127.0.0.1", "::1"}


def is_localhost_request(request: Request) -> bool:
    """True iff the TCP client address is loopback.

    Deliberately uses ``request.client.host`` (the socket peer address ASGI
    servers set from the real connection) rather than any client-supplied
    header, so it cannot be forged by a remote caller.
    """
    client = request.client
    if client is None:
        return False
    return client.host in LOCALHOST_IPS


def extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        return None
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def require_admin(request: Request, state_dir: str) -> None:
    """Admin endpoints: localhost bypass, else a valid peer bearer token.

    Raises :class:`fastapi.HTTPException` (401) otherwise.
    """
    if is_localhost_request(request):
        return
    from .trust_store import find_peer_by_token

    token = extract_bearer_token(request)
    peer = find_peer_by_token(state_dir, token)
    if peer is None:
        raise HTTPException(status_code=401, detail="unauthorized")


def require_read_access(request: Request, state_dir: str, required: bool) -> None:
    """Read endpoints: open by default, else same rules as ``require_admin``
    when ``required`` (the ``require_read_token`` config flag) is set.
    """
    if not required:
        return
    require_admin(request, state_dir)


def require_write_access(
    request: Request, state_dir: str, require_write_token: bool
) -> None:
    """Registry-mutation endpoints (``POST /api/services``, ``DELETE
    /api/services/{name}``, ``POST /api/services/{name}/heartbeat``): EVERY
    mutation requires authorization -- there is no unauthenticated path.

    - A valid ``Authorization: Bearer <write-token>`` (verified with
      ``hmac.compare_digest`` against the token persisted in the state dir
      via ``write_token.py``) always authorizes the request.
    - The localhost socket-IP bypass (same unforgeable mechanism as
      ``require_admin``) is allowed BY DEFAULT as a local-convenience path,
      but is gated by ``require_write_token`` (the ``federation
      .require_write_token`` config flag, default ``False``): when True,
      even localhost must present a valid write token -- no bypass.

    Raises :class:`fastapi.HTTPException` (401) otherwise.
    """
    from .write_token import verify_write_token

    token = extract_bearer_token(request)
    if verify_write_token(state_dir, token):
        return
    if not require_write_token and is_localhost_request(request):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


__all__ = [
    "LOCALHOST_IPS",
    "extract_bearer_token",
    "is_localhost_request",
    "require_admin",
    "require_read_access",
    "require_write_access",
]
