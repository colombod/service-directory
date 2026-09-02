from __future__ import annotations

from service_directory.pairing import DEFAULT_PAIRING_TTL_SECONDS, PairingCodeStore


def test_pairing_code_valid_once():
    store = PairingCodeStore()
    code = store.issue()
    assert store.redeem(code) is True


def test_pairing_code_one_time_second_use_rejected():
    store = PairingCodeStore()
    code = store.issue()
    assert store.redeem(code) is True
    # second redemption of the SAME code must be rejected
    assert store.redeem(code) is False


def test_pairing_code_unknown_code_rejected():
    store = PairingCodeStore()
    assert store.redeem("never-issued") is False


def test_pairing_code_expires():
    fake_time = [0.0]
    store = PairingCodeStore(time_fn=lambda: fake_time[0])
    code = store.issue(ttl_seconds=DEFAULT_PAIRING_TTL_SECONDS)

    # advance the injected clock beyond the TTL
    fake_time[0] += DEFAULT_PAIRING_TTL_SECONDS + 1

    assert store.redeem(code) is False


def test_pairing_code_not_expired_just_before_ttl():
    fake_time = [0.0]
    store = PairingCodeStore(time_fn=lambda: fake_time[0])
    code = store.issue(ttl_seconds=100)

    fake_time[0] += 99
    assert store.redeem(code) is True


def test_pairing_codes_are_distinct_and_unguessable():
    store = PairingCodeStore()
    codes = {store.issue() for _ in range(20)}
    assert len(codes) == 20
    for code in codes:
        assert len(code) >= 16
