from __future__ import annotations

import pytest
from fastapi import HTTPException
from service_directory.auth import (
    extract_bearer_token,
    is_localhost_request,
    require_admin,
    require_read_access,
)
from service_directory.trust_store import PeerRecord, upsert_peer


class _FakeClientAddr:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    def __init__(self, host: str | None, auth_header: str | None = None):
        self.client = _FakeClientAddr(host) if host is not None else None
        self.headers = {}
        if auth_header is not None:
            self.headers["authorization"] = auth_header


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_is_localhost_request_true_for_loopback(host):
    assert is_localhost_request(_FakeRequest(host)) is True


@pytest.mark.parametrize("host", ["10.0.0.5", "192.168.1.2", "100.111.191.22"])
def test_is_localhost_request_false_for_remote(host):
    assert is_localhost_request(_FakeRequest(host)) is False


def test_is_localhost_request_false_when_no_client_info():
    assert is_localhost_request(_FakeRequest(None)) is False


def test_localhost_bypass_cannot_be_forged_via_header():
    """The bypass must be driven by the socket-level client IP, never by a
    client-controlled header like X-Forwarded-For. A remote client claiming
    to be localhost via a header must still be rejected."""
    request = _FakeRequest("203.0.113.9")
    request.headers["x-forwarded-for"] = "127.0.0.1"
    assert is_localhost_request(request) is False


def test_extract_bearer_token():
    assert extract_bearer_token(_FakeRequest("1.2.3.4", "Bearer abc123")) == "abc123"
    assert extract_bearer_token(_FakeRequest("1.2.3.4", "Basic abc123")) is None
    assert extract_bearer_token(_FakeRequest("1.2.3.4", None)) is None
    assert extract_bearer_token(_FakeRequest("1.2.3.4", "Bearer")) is None


def test_require_admin_allows_localhost_without_token(tmp_path):
    request = _FakeRequest("127.0.0.1")
    require_admin(request, str(tmp_path))  # must not raise


def test_require_admin_rejects_remote_without_token(tmp_path):
    request = _FakeRequest("203.0.113.9")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(request, str(tmp_path))
    assert exc_info.value.status_code == 401


def test_require_admin_accepts_remote_with_valid_peer_token(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir,
        PeerRecord(name="peer1", device_id="d1", base_url="http://peer1", token="good-token"),
    )
    request = _FakeRequest("203.0.113.9", "Bearer good-token")
    require_admin(request, state_dir)  # must not raise


def test_require_admin_rejects_remote_with_wrong_token(tmp_path):
    state_dir = str(tmp_path)
    upsert_peer(
        state_dir,
        PeerRecord(name="peer1", device_id="d1", base_url="http://peer1", token="good-token"),
    )
    request = _FakeRequest("203.0.113.9", "Bearer wrong-token")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(request, state_dir)
    assert exc_info.value.status_code == 401


def test_require_read_access_open_by_default(tmp_path):
    request = _FakeRequest("203.0.113.9")  # remote, no token
    require_read_access(request, str(tmp_path), required=False)  # must not raise


def test_require_read_access_locked_down_when_required(tmp_path):
    request = _FakeRequest("203.0.113.9")
    with pytest.raises(HTTPException):
        require_read_access(request, str(tmp_path), required=True)


def test_require_read_access_localhost_bypass_when_required(tmp_path):
    request = _FakeRequest("127.0.0.1")
    require_read_access(request, str(tmp_path), required=True)  # must not raise
