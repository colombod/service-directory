"""Tests for auth.require_write_access -- the gate on every registry
mutation endpoint (POST /api/services, DELETE /api/services/{name},
POST /api/services/{name}/heartbeat).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from service_directory.auth import require_write_access
from service_directory.write_token import issue_write_token


class _FakeClientAddr:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None, auth_header: str | None = None) -> None:
        self.client = _FakeClientAddr(host) if host is not None else None
        self.headers = {}
        if auth_header is not None:
            self.headers["authorization"] = auth_header


def test_localhost_bypass_allowed_by_default(tmp_path):
    request = _FakeRequest("127.0.0.1")
    require_write_access(
        request, str(tmp_path), require_write_token=False
    )  # must not raise


def test_remote_without_token_rejected_by_default(tmp_path):
    request = _FakeRequest("203.0.113.9")
    with pytest.raises(HTTPException) as exc_info:
        require_write_access(request, str(tmp_path), require_write_token=False)
    assert exc_info.value.status_code == 401


def test_remote_with_valid_write_token_allowed(tmp_path):
    token = issue_write_token(str(tmp_path))
    request = _FakeRequest("203.0.113.9", f"Bearer {token}")
    require_write_access(
        request, str(tmp_path), require_write_token=False
    )  # must not raise


def test_remote_with_wrong_write_token_rejected(tmp_path):
    issue_write_token(str(tmp_path))
    request = _FakeRequest("203.0.113.9", "Bearer totally-wrong")
    with pytest.raises(HTTPException) as exc_info:
        require_write_access(request, str(tmp_path), require_write_token=False)
    assert exc_info.value.status_code == 401


def test_require_write_token_flag_forces_token_even_on_localhost(tmp_path):
    """The hard requirement: when require_write_token=True, EVEN localhost
    must present a valid write token -- no bypass."""
    request = _FakeRequest("127.0.0.1")
    with pytest.raises(HTTPException) as exc_info:
        require_write_access(request, str(tmp_path), require_write_token=True)
    assert exc_info.value.status_code == 401


def test_require_write_token_flag_localhost_with_valid_token_allowed(tmp_path):
    token = issue_write_token(str(tmp_path))
    request = _FakeRequest("127.0.0.1", f"Bearer {token}")
    require_write_access(
        request, str(tmp_path), require_write_token=True
    )  # must not raise


def test_require_write_token_flag_remote_with_valid_token_still_allowed(tmp_path):
    token = issue_write_token(str(tmp_path))
    request = _FakeRequest("203.0.113.9", f"Bearer {token}")
    require_write_access(
        request, str(tmp_path), require_write_token=True
    )  # must not raise


def test_no_token_ever_issued_localhost_still_bypasses_by_default(tmp_path):
    """No write_token.json exists at all -- localhost bypass still works
    when require_write_token is False (default)."""
    request = _FakeRequest("127.0.0.1")
    require_write_access(
        request, str(tmp_path), require_write_token=False
    )  # must not raise


def test_no_token_ever_issued_remote_rejected(tmp_path):
    request = _FakeRequest("203.0.113.9")
    with pytest.raises(HTTPException) as exc_info:
        require_write_access(request, str(tmp_path), require_write_token=False)
    assert exc_info.value.status_code == 401
