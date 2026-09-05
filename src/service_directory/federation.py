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

# Transitive-aggregation carriers. A node that fetches a peer's AGGREGATED
# view sends the set of node identities already traversed (comma-separated)
# plus the remaining hop budget. The receiving node excludes any peer already
# in ``visited`` and decrements the budget, so a CONNECTED graph aggregates
# fully while a cycle can never form (visited-set) and depth is bounded (ttl).
FEDERATION_VISITED_HEADER = "x-sd-federation-visited"
FEDERATION_TTL_HEADER = "x-sd-federation-ttl"

# Default hop budget for a top-level (user-facing) /api/services request.
# Bounds the transitive walk's depth (and thus worst-case latency) regardless
# of federation size; 5 comfortably covers any realistic personal federation.
DEFAULT_MAX_HOPS = 5

# A fetcher takes (peer, timeout_seconds) and returns the peer's parsed
# services JSON body (a list of service dicts) on success, or raises on any
# failure (timeout, connection error, non-2xx, bad JSON). Production
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


# A peer-info fetcher takes (peer, timeout_seconds) and returns the peer's
# parsed ``/api/instance-info`` JSON body (a dict) on success, or ``None`` on
# ANY failure (timeout, connection error, non-2xx, bad JSON, peer too old to
# have the endpoint). Used by ``/api/federation/nodes`` to enrich each trust
# -store peer entry with LIVE metadata -- description, role, and version --
# none of which are persisted in ``peers.json`` (which only ever stores
# name/device_id/base_url/token). Unlike ``PeerFetcher`` (which raises on
# failure), this returns ``None`` so the caller can represent those fields
# as explicitly unknown rather than fabricating a value or crashing.
PeerInfoFetcher = Callable[[PeerRecord, float], "dict | None"]


def default_peer_info_fetcher(peer: PeerRecord, timeout: float) -> dict | None:
    """Real implementation: GET {peer.base_url}/api/instance-info, bounded
    to ``timeout`` seconds, using the peer's bearer token (harmless since
    the endpoint is itself unauthenticated, but consistent with every other
    peer call). Returns ``None`` on any failure -- callers must treat that
    as "this peer's live metadata is unknown", never as agreement with the
    local node's own version.
    """
    import httpx2 as httpx

    url = peer.base_url.rstrip("/") + "/api/instance-info"
    headers = {
        "Authorization": f"Bearer {peer.token}",
        FEDERATION_HOP_HEADER: "1",
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001 - peer info is best-effort only
        return None
    if not isinstance(data, dict):
        return None
    return data


def make_default_transitive_fetcher(visited: frozenset[str], ttl: int) -> PeerFetcher:
    """Build a real-HTTP peer fetcher for the TRANSITIVE path.

    Unlike ``default_peer_fetcher`` (which targets ``/api/services/local`` and
    therefore never causes the peer to aggregate further), this targets the
    peer's AGGREGATED ``/api/services`` and passes the current ``visited`` set
    and remaining ``ttl`` in headers. The receiving node excludes peers already
    in ``visited`` and decrements ``ttl`` -- so the graph is walked transitively
    while remaining loop-safe (a node already in ``visited``, or ttl<=0, answers
    local-only and stops the walk). The returned callable has the standard
    ``(peer, timeout)`` PeerFetcher signature; ``visited``/``ttl`` are captured.
    """

    def _fetch(peer: PeerRecord, timeout: float) -> list[dict]:
        import httpx2 as httpx

        url = peer.base_url.rstrip("/") + "/api/services"
        headers = {
            "Authorization": f"Bearer {peer.token}",
            FEDERATION_HOP_HEADER: "1",
            FEDERATION_VISITED_HEADER: ",".join(sorted(visited)),
            FEDERATION_TTL_HEADER: str(ttl),
        }
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, list):
            raise TypeError(f"peer {peer.name!r} returned non-list /api/services body")
        return data

    return _fetch


def dedupe_services(services: list[dict]) -> list[dict]:
    """Collapse duplicate entries by (origin, name).

    A service reachable via more than one path through the federation graph
    would otherwise appear once per path. First occurrence wins (its origin
    tag is the true owner, preserved by ``_tag_origin``). Order is otherwise
    stable.
    """
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for svc in services:
        key = (svc.get("origin") or "", svc.get("name") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(svc)
    return out


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


def _fetch_info_one(
    peer: PeerRecord, fetcher: PeerInfoFetcher, timeout: float
) -> tuple[str, dict | None]:
    try:
        result = fetcher(peer, timeout)
    except Exception:  # noqa: BLE001 - any peer failure must never break the caller
        result = None
    return peer.name, result


def fetch_peers_info(
    peers: list[PeerRecord],
    fetcher: PeerInfoFetcher = default_peer_info_fetcher,
    timeout: float = DEFAULT_PEER_TIMEOUT_SECONDS,
) -> dict[str, dict | None]:
    """Concurrently fetch each peer's live ``/api/instance-info``.

    Returns a dict keyed by peer name; a peer whose fetch failed (down,
    timeout, too old to have the endpoint, malformed body) maps to ``None``
    -- callers must render that as explicitly unknown metadata, never as
    "same as the local node" and never fabricated.
    """
    results: dict[str, dict | None] = {}
    if not peers:
        return results
    with ThreadPoolExecutor(max_workers=max(1, len(peers))) as pool:
        futures = [
            pool.submit(_fetch_info_one, peer, fetcher, timeout) for peer in peers
        ]
        for future in futures:
            name, info = future.result()
            results[name] = info
    return results


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
    "DEFAULT_MAX_HOPS",
    "DEFAULT_PEER_TIMEOUT_SECONDS",
    "FEDERATION_HOP_HEADER",
    "FEDERATION_TTL_HEADER",
    "FEDERATION_VISITED_HEADER",
    "AggregationResult",
    "PeerFetcher",
    "PeerInfoFetcher",
    "aggregate_services",
    "dedupe_services",
    "default_peer_fetcher",
    "default_peer_info_fetcher",
    "fetch_peers_info",
    "make_default_transitive_fetcher",
]
