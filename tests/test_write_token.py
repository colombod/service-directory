from __future__ import annotations

import os
import stat

from service_directory.write_token import (
    WRITE_TOKEN_FILENAME,
    issue_write_token,
    load_write_token,
    verify_write_token,
)


def test_load_write_token_missing_file_returns_none(tmp_path):
    assert load_write_token(str(tmp_path)) is None


def test_load_write_token_corrupt_file_returns_none(tmp_path):
    path = tmp_path / WRITE_TOKEN_FILENAME
    path.write_text("not valid json {{{")
    assert load_write_token(str(tmp_path)) is None


def test_issue_write_token_mints_a_usable_token(tmp_path):
    state_dir = str(tmp_path)
    token = issue_write_token(state_dir)
    assert isinstance(token, str)
    assert len(token) > 10
    assert load_write_token(state_dir) == token
    assert verify_write_token(state_dir, token) is True


def test_issue_write_token_persists_with_mode_0600(tmp_path):
    state_dir = str(tmp_path)
    issue_write_token(state_dir)
    path = os.path.join(state_dir, WRITE_TOKEN_FILENAME)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_issue_write_token_rotates_previous_token(tmp_path):
    state_dir = str(tmp_path)
    first = issue_write_token(state_dir)
    second = issue_write_token(state_dir)
    assert first != second
    assert verify_write_token(state_dir, first) is False
    assert verify_write_token(state_dir, second) is True


def test_verify_write_token_rejects_wrong_token(tmp_path):
    state_dir = str(tmp_path)
    issue_write_token(state_dir)
    assert verify_write_token(state_dir, "totally-wrong") is False


def test_verify_write_token_rejects_none_and_empty(tmp_path):
    state_dir = str(tmp_path)
    issue_write_token(state_dir)
    assert verify_write_token(state_dir, None) is False
    assert verify_write_token(state_dir, "") is False


def test_verify_write_token_when_no_token_ever_issued(tmp_path):
    assert verify_write_token(str(tmp_path), "anything") is False
