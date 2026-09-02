"""Pull-aggregation across trusted peers.

Each node keeps ONLY its own local config. On every read of the services
list, the node concurrently fetches each trusted peer's LOCAL-ONLY services
view (``/api/services/local``, best-effort, <=1s each), merges the results
with the local list, and tags every entry with its origin node name. A
down/unreachable peer is silently omitted -- it never breaks rendering, and
the local list always renders.

Peer fetches deliberately target ``/api/services/local`` -- a view that
NEVER itself aggregates peers -- rather than the aggregated ``/api/services``
endpoint. Federation is bidirectional (mutual trust is common), and hitting
the aggregated endpoint would cause the peer to recurse into fetching ITS
peers (including us), recursively, exhausting the per-peer timeout budget on
every nested hop until the outer fetch itself times out and gets silently
dropped by ``_fetch_one``. Targeting the local-only view breaks that
recursion at the root. ``HOP_HEADER`` is a defensive belt-and-suspenders
guard against a misconfigured (or future) peer fetcher pointed at the
aggregated endpoint instead: any handler that sees ``HOP_HEADER`` on an
incoming request knows the caller is another node's peer-fetch, and must
respond with ITS local-only view rather than aggregating further.

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

# Sent by ``default_peer_fetcher`` on every outgoing peer request, and
# checked by the receiving node (see ``app._aggregated_services``) as a
# defensive hop/visited guard: any request bearing this header is known to
# be a peer-fetch hop, so the receiver must answer with its LOCAL-ONLY view
# and must never itself fan out to ITS peers. This is belt-and-suspenders
# on top of pointing the fetcher at ``/api/services/local`` in the first
# place -- it means even a misconfigured fetcher (or a future caller) that
# hits the aggregated ``/api/services`` endpoint on a peer still cannot
# trigger recursive aggregation, so a mutual-trust or 3+ node graph can
# never recurse regardless of which endpoint gets called.
FEDERATION_HOP_HEADER = "x-sd-federation-hop"

# A fetcher takes (peer, timeout_seconds) and returns the peer's parsed
# local-services JSON body (a list of service dicts) on success, or raises
# on any failure (timeout, connection error, non-2xx, bad JSON). Production
# implements this with a real HTTP client; tests inject a stub/fake.
PeerFetcher = Callable[[PeerRecord, float], list[dict]]


def default_peer_fetcher(peer: PeerRecord, timeout: float) -> list[dict]:
    """Real implementation: GET {peer.base_url}/api/services/local with the
    peer's bearer token, bounded to ``timeout`` seconds. Any failure
    propagates as an exception -- callers (``aggregate_services``) treat
    that as "peer down" and omit it.

    Deliberately targets the LOCAL-ONLY view (never the aggregated
    ``/api/services``) so that fetching a peer can never trigger another
    round of peer aggregation on that peer -- this is what makes mutual
    (bidirectional) trust safe: A fetching B never causes B to fetch A.
    """
    import httpx2 as httpx

    url = peer.base_url.rstrip("/") + "/api/services/local"
    headers = {
        "Authorization": f"Bearer {peer.token}",
        FEDERATION_HOP_HEADER: "1",
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, list):
        raise TypeError(
            f"peer {peer.name!r} returned non-list /api/services/local body"
        )
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
    "FEDERATION_HOP_HEADER",
    "AggregationResult",
    "PeerFetcher",
    "aggregate_services",
    "default_peer_fetcher",
]
