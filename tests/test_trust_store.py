from __future__ import annotations

import os
import stat

from service_directory.trust_store import (
    PeerRecord,
    find_peer_by_name,
    find_peer_by_token,
    load_peers,
    remove_peer,
    save_peers,
    upsert_peer,
)


def test_load_peers_missing_file_returns_empty(tmp_path):
    assert load_peers(str(tmp_path / "nope")) == []


def test_upsert_and_load_peers_roundtrip(tmp_path):
    state_dir = str(tmp_path)
    peer = PeerRecord(name="alpha", device_id="dev-1", base_url="http://a:80", token="tok-1")
    upsert_peer(state_dir, peer)

    peers = load_peers(state_dir)
    assert peers == [peer]


def test_upsert_peer_replaces_existing_by_name(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="t1")
    )
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a2", token="t2")
    )

    peers = load_peers(state_dir)
    assert len(peers) == 1
    assert peers[0].base_url == "http://a2"
    assert peers[0].token == "t2"


def test_remove_peer(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="t1")
    )
    upsert_peer(
        state_dir, PeerRecord(name="beta", device_id="d2", base_url="http://b", token="t2")
    )

    assert remove_peer(state_dir, "alpha") is True
    remaining = load_peers(state_dir)
    assert [p.name for p in remaining] == ["beta"]

    # removing again is a clean no-op, not a crash
    assert remove_peer(state_dir, "alpha") is False


def test_peers_file_mode_is_0600(tmp_path):
    state_dir = str(tmp_path)
    save_peers(
        state_dir,
        [PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="secret-token")],
    )
    path = os.path.join(state_dir, "peers.json")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_trust_store_reads_fresh_not_cached(tmp_path):
    """Two independent load_peers calls must reflect changes made to disk
    in between -- there must be no in-process caching layer."""
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="t1")
    )
    assert len(load_peers(state_dir)) == 1

    # Simulate an external process (e.g. `peers remove` CLI) mutating the
    # file directly.
    save_peers(state_dir, [])
    assert load_peers(state_dir) == []


def test_find_peer_by_name(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="t1")
    )
    assert find_peer_by_name(state_dir, "alpha").token == "t1"
    assert find_peer_by_name(state_dir, "missing") is None


def test_find_peer_by_token_correct_and_wrong(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir, PeerRecord(name="alpha", device_id="d1", base_url="http://a", token="correct-token")
    )
    assert find_peer_by_token(state_dir, "correct-token").name == "alpha"
    assert find_peer_by_token(state_dir, "wrong-token") is None
    assert find_peer_by_token(state_dir, None) is None
    assert find_peer_by_token(state_dir, "") is None


def test_load_peers_corrupt_file_returns_empty_not_crash(tmp_path):
    state_dir = str(tmp_path)
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "peers.json"), "w") as f:
        f.write("{not valid json at all")
    assert load_peers(state_dir) == []


def test_load_peers_malformed_entries_are_skipped(tmp_path):
    state_dir = str(tmp_path)
    os.makedirs(state_dir, exist_ok=True)
    import json

    with open(os.path.join(state_dir, "peers.json"), "w") as f:
        json.dump(
            [
                {"name": "good", "device_id": "d1", "base_url": "http://a", "token": "t1"},
                {"name": "missing-fields"},
                "not-even-a-dict",
            ],
            f,
        )
    peers = load_peers(state_dir)
    assert len(peers) == 1
    assert peers[0].name == "good"
