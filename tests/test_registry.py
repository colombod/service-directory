"""Unit tests for the dynamic service registry (registry.py).

Follows the same conventions as trust_store.py's tests: state_dir is always
a tmp_path, the clock is an injectable seam so TTL/heartbeat expiry is
tested deterministically without real sleeping.
"""

from __future__ import annotations

import json
import os
import stat

from service_directory.registry import (
    REGISTRY_FILENAME,
    DynamicService,
    deregister_service,
    find_dynamic_service,
    heartbeat_service,
    is_expired,
    load_registry,
    register_service,
    save_registry,
)


def test_load_registry_missing_file_returns_empty(tmp_path):
    assert load_registry(str(tmp_path)) == []


def test_load_registry_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / REGISTRY_FILENAME
    path.write_text("not valid json {{{")
    assert load_registry(str(tmp_path)) == []


def test_load_registry_non_list_json_returns_empty(tmp_path):
    path = tmp_path / REGISTRY_FILENAME
    path.write_text(json.dumps({"not": "a list"}))
    assert load_registry(str(tmp_path)) == []


def test_register_service_persists_and_is_readable(tmp_path):
    state_dir = str(tmp_path)
    entry = DynamicService(name="agent-svc", port=9000, description="d")
    stored = register_service(state_dir, entry, time_fn=lambda: 1000.0)
    assert stored.name == "agent-svc"
    assert stored.registered_at == 1000.0
    assert stored.last_heartbeat == 1000.0

    loaded = load_registry(state_dir, time_fn=lambda: 1000.0)
    assert len(loaded) == 1
    assert loaded[0].name == "agent-svc"
    assert loaded[0].port == 9000


def test_register_service_upserts_by_name(tmp_path):
    state_dir = str(tmp_path)
    register_service(
        state_dir, DynamicService(name="svc", port=1), time_fn=lambda: 100.0
    )
    register_service(
        state_dir, DynamicService(name="svc", port=2), time_fn=lambda: 200.0
    )

    loaded = load_registry(state_dir, time_fn=lambda: 200.0)
    assert len(loaded) == 1
    assert loaded[0].port == 2


def test_registry_file_persisted_with_mode_0600(tmp_path):
    state_dir = str(tmp_path)
    register_service(
        state_dir, DynamicService(name="svc", port=1), time_fn=lambda: 100.0
    )
    path = os.path.join(state_dir, REGISTRY_FILENAME)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_registry_read_fresh_reflects_external_write(tmp_path):
    """Like peers.json, registry.json must be read FRESH per call -- a
    write from elsewhere (e.g. another process, or a CLI invocation) must
    be visible on the very next read without any caching."""
    state_dir = str(tmp_path)
    register_service(state_dir, DynamicService(name="a", port=1), time_fn=lambda: 100.0)
    assert {e.name for e in load_registry(state_dir, time_fn=lambda: 100.0)} == {"a"}

    # simulate an external write (e.g. a second process)
    save_registry(
        state_dir,
        [
            DynamicService(name="a", port=1, registered_at=100.0, last_heartbeat=100.0),
            DynamicService(name="b", port=2, registered_at=100.0, last_heartbeat=100.0),
        ],
    )
    assert {e.name for e in load_registry(state_dir, time_fn=lambda: 100.0)} == {
        "a",
        "b",
    }


def test_deregister_service_removes_entry(tmp_path):
    state_dir = str(tmp_path)
    register_service(
        state_dir, DynamicService(name="svc", port=1), time_fn=lambda: 100.0
    )
    assert deregister_service(state_dir, "svc", time_fn=lambda: 100.0) is True
    assert load_registry(state_dir, time_fn=lambda: 100.0) == []


def test_deregister_service_unknown_name_returns_false(tmp_path):
    state_dir = str(tmp_path)
    assert deregister_service(state_dir, "ghost", time_fn=lambda: 100.0) is False


def test_find_dynamic_service(tmp_path):
    state_dir = str(tmp_path)
    register_service(
        state_dir, DynamicService(name="svc", port=1), time_fn=lambda: 100.0
    )
    found = find_dynamic_service(state_dir, "svc", time_fn=lambda: 100.0)
    assert found is not None
    assert found.name == "svc"
    assert find_dynamic_service(state_dir, "ghost", time_fn=lambda: 100.0) is None


# --- liveness: persistent vs ttl/heartbeat -----------------------------------


def test_is_expired_persistent_entry_never_expires():
    entry = DynamicService(name="p", registered_at=0.0, last_heartbeat=0.0, ttl=None)
    assert is_expired(entry, now=1_000_000_000.0) is False


def test_is_expired_ttl_entry_expires_after_no_heartbeat():
    entry = DynamicService(name="t", registered_at=0.0, last_heartbeat=0.0, ttl=10.0)
    assert is_expired(entry, now=5.0) is False
    assert is_expired(entry, now=11.0) is True


def test_ttl_entry_pruned_on_read_after_expiry(tmp_path):
    state_dir = str(tmp_path)
    clock = {"t": 1000.0}

    def time_fn():
        return clock["t"]

    register_service(
        state_dir, DynamicService(name="ttl-svc", port=1, ttl=10.0), time_fn=time_fn
    )
    assert {e.name for e in load_registry(state_dir, time_fn=time_fn)} == {"ttl-svc"}

    clock["t"] += 5  # within ttl
    assert {e.name for e in load_registry(state_dir, time_fn=time_fn)} == {"ttl-svc"}

    clock["t"] += 20  # now well past the 10s ttl since last heartbeat
    assert load_registry(state_dir, time_fn=time_fn) == []


def test_heartbeat_refreshes_ttl_entry_preventing_expiry(tmp_path):
    state_dir = str(tmp_path)
    clock = {"t": 1000.0}

    def time_fn():
        return clock["t"]

    register_service(
        state_dir, DynamicService(name="ttl-svc", port=1, ttl=10.0), time_fn=time_fn
    )

    clock["t"] += 8  # still alive
    updated = heartbeat_service(state_dir, "ttl-svc", time_fn=time_fn)
    assert updated is not None
    assert updated.last_heartbeat == 1008.0

    clock["t"] += 8  # would have expired w/o the heartbeat refresh (16s > 10s ttl)
    assert {e.name for e in load_registry(state_dir, time_fn=time_fn)} == {"ttl-svc"}


def test_heartbeat_unknown_name_returns_none(tmp_path):
    state_dir = str(tmp_path)
    assert heartbeat_service(state_dir, "ghost", time_fn=lambda: 100.0) is None


def test_persistent_entry_survives_indefinitely_without_heartbeat(tmp_path):
    state_dir = str(tmp_path)
    clock = {"t": 0.0}

    def time_fn():
        return clock["t"]

    register_service(
        state_dir, DynamicService(name="persist-svc", port=1, ttl=None), time_fn=time_fn
    )

    clock["t"] += 1_000_000  # a very long time, no heartbeat, no ttl
    assert {e.name for e in load_registry(state_dir, time_fn=time_fn)} == {
        "persist-svc"
    }
