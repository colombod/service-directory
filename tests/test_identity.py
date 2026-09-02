from __future__ import annotations

import json
import os

from service_directory.identity import load_or_create_identity


def test_identity_created_on_first_run(tmp_path):
    state_dir = str(tmp_path / "state")
    identity = load_or_create_identity(state_dir)

    assert identity.device_id
    # a real uuid4 -- 36 chars, 4 dashes
    assert len(identity.device_id) == 36
    assert identity.device_id.count("-") == 4

    path = os.path.join(state_dir, "identity.json")
    assert os.path.exists(path)
    with open(path) as f:
        data = json.load(f)
    assert data["device_id"] == identity.device_id


def test_identity_persists_across_calls(tmp_path):
    state_dir = str(tmp_path / "state")
    first = load_or_create_identity(state_dir)
    second = load_or_create_identity(state_dir)
    assert first.device_id == second.device_id


def test_identity_survives_corrupt_file(tmp_path):
    state_dir = str(tmp_path / "state")
    os.makedirs(state_dir)
    path = os.path.join(state_dir, "identity.json")
    with open(path, "w") as f:
        f.write("{not valid json")

    # must not crash -- regenerates a fresh identity instead
    identity = load_or_create_identity(state_dir)
    assert identity.device_id
