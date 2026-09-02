"""Pull-aggregation across trusted peers.

Each node keeps ONLY its own local config. On every read of the services
list, the node concurrently fetches each trusted peer's ``/api/services``
(best-effort, <=1s each), merges the results with the local list, and tags
every entry with its origin node name. A down/unreachable peer is silently
omitted -- it never breaks rendering, and the local list always renders.

The peer HTTP client is fully injectable (``PeerFetcher``) so the hermetic
test suite never performs real network I/O; production wires in
``default_peer_fetcher``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .trust_store import PeerRecord

DEFAULT_PEER_TIMEOUT_SECONDS = 1.0

# A fetcher takes (peer, timeout_seconds) and returns the peer's parsed
# /api/services JSON body (a list of service dicts) on success, or raises
# on any failure (timeout, connection error, non-2xx, bad JSON). Production
# implements this with a real HTTP client; tests inject a stub/fake.
PeerFetcher = Callable[[PeerRecord, float], list[dict]]


def default_peer_fetcher(peer: PeerRecord, timeout: float) -> list[dict]:
    """Real implementation: GET {peer.base_url}/api/services with the
    peer's bearer token, bounded to ``timeout`` seconds. Any failure
    propagates as an exception -- callers (``aggregate_services``) treat
    that as "peer down" and omit it.
    """
    import httpx2 as httpx

    url = peer.base_url.rstrip("/") + "/api/services"
    headers = {"Authorization": f"Bearer {peer.token}"}
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        raise TypeError(f"peer {peer.name!r} returned non-list /api/services body")
    return data


@dataclass(frozen=True)
class AggregationResult:
    services: list[dict]
    reachable_peers: list[str]
    unreachable_peers: list[str]


def _tag_origin(services: list[dict], origin: str) -> list[dict]:
    """Tag each entry with its origin node name.

    If an entry already carries an ``origin`` (e.g. it arrived from a peer
    whose own ``/api/services`` had already aggregated across ITS peers),
    that origin is preserved rather than overwritten -- credit always goes
    to the node that actually owns the service, not the intermediate peer
    that happened to relay it.
    """
    tagged = []
    for svc in services:
        entry = dict(svc)
        entry.setdefault("origin", origin)
        tagged.append(entry)
    return tagged


def _fetch_one(
    peer: PeerRecord, fetcher: PeerFetcher, timeout: float
) -> tuple[str, list[dict] | None]:
    try:
        result = fetcher(peer, timeout)
        return peer.name, result
    except Exception:  # noqa: BLE001 - any peer failure must never break aggregation
        return peer.name, None


def aggregate_services(
    local_name: str,
    local_services: list[dict],
    peers: list[PeerRecord],
    fetcher: PeerFetcher = default_peer_fetcher,
    timeout: float = DEFAULT_PEER_TIMEOUT_SECONDS,
) -> AggregationResult:
    """Merge the local service list with every trusted peer's list.

    Local entries are tagged with ``local_name``. Peer fetches happen
    concurrently and are individually best-effort: an exception or timeout
    from any one peer is swallowed and that peer is simply omitted from the
    merged result -- the local list (and any peers that DID respond) always
    renders regardless.
    """
    merged = _tag_origin(local_services, local_name)
    reachable: list[str] = [local_name]
    unreachable: list[str] = []

    if peers:
        with ThreadPoolExecutor(max_workers=max(1, len(peers))) as pool:
            futures = [
                pool.submit(_fetch_one, peer, fetcher, timeout) for peer in peers
            ]
            for future in futures:
                name, result = future.result()
                if result is None:
                    unreachable.append(name)
                else:
                    merged.extend(_tag_origin(result, name))
                    reachable.append(name)

    return AggregationResult(
        services=merged, reachable_peers=reachable, unreachable_peers=unreachable
    )


__all__ = [
    "DEFAULT_PEER_TIMEOUT_SECONDS",
    "AggregationResult",
    "PeerFetcher",
    "aggregate_services",
    "default_peer_fetcher",
]
