"""Security remediation tests: config/host/port injection into the
generated systemd unit / launchd plist.

A prior automated security review (S1, medium severity) flagged that the
new `--config`/`--host`/`--port` -> `extra_env` mechanism in
`service_manager.py` interpolated resolved values verbatim into the
generated unit/plist text with no escaping or validation:

- systemd units are parsed line-by-line, so a value containing an embedded
  newline (e.g. `--config $'x\\nExecStart=/bin/sh -c evil'`) could inject an
  arbitrary additional directive -- including a replacement `ExecStart=` --
  that systemd would then execute when the unit is (re)started.
- The launchd plist path has the analogous XML-injection issue: an
  unescaped `</string>` or embedded `<key>...</key>` sequence in a value
  could inject new plist keys (e.g. a different `ProgramArguments`) that
  launchd would honor.

Fix: `resolve_install_env` (and `render_systemd_unit` directly, as defense
in depth) reject config/host/port values containing a newline, carriage
return, or double quote by raising `InvalidInstallValueError` rather than
baking them in verbatim. `render_launchd_plist` XML-escapes every
extra_env key/value before interpolation.

Hermetic: no real systemctl/launchctl, no real installs.
"""

from __future__ import annotations

import subprocess

import pytest
from service_directory import cli
from service_directory.service_manager import (
    InvalidInstallValueError,
    SystemdUserServiceManager,
    render_launchd_plist,
    render_systemd_unit,
    resolve_install_env,
)


class _RecordingRunner:
    def __init__(self, returncode: int = 0):
        self.calls: list[list[str]] = []
        self.returncode = returncode

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(cmd)
        return subprocess.CompletedProcess(
            args=[], returncode=self.returncode, stdout="ok"
        )


# --- resolve_install_env rejects injection attempts ------------------------


def test_resolve_install_env_rejects_newline_in_config():
    with pytest.raises(InvalidInstallValueError):
        resolve_install_env(config="/x.yaml\nExecStart=/bin/sh -c evil")


def test_resolve_install_env_rejects_carriage_return_in_host():
    with pytest.raises(InvalidInstallValueError):
        resolve_install_env(host="127.0.0.1\rExecStart=/bin/sh -c evil")


def test_resolve_install_env_rejects_double_quote_in_port():
    with pytest.raises(InvalidInstallValueError):
        resolve_install_env(port='8080"\nExecStart=/bin/sh -c evil')


def test_resolve_install_env_accepts_ordinary_values():
    """Negative-space check: legitimate values must still work (no
    over-broad rejection)."""
    env = resolve_install_env(config="/etc/sd/config.yaml", host="127.0.0.1", port=8080)
    assert env == {
        "SERVICE_REGISTRY_CONFIG": "/etc/sd/config.yaml",
        "SERVICE_REGISTRY_HOST": "127.0.0.1",
        "SERVICE_REGISTRY_PORT": "8080",
    }


# --- render_systemd_unit rejects injection even if extra_env is built by hand --


def test_render_systemd_unit_rejects_newline_injection_in_extra_env():
    """Even a caller that bypasses resolve_install_env and builds extra_env
    directly must not be able to smuggle an extra ExecStart= line in."""
    with pytest.raises(InvalidInstallValueError):
        render_systemd_unit(
            "/bin/service-directory",
            "/usr/bin",
            extra_env={
                "SERVICE_REGISTRY_CONFIG": (
                    "/x.yaml\nExecStart=/bin/sh -c 'echo pwned'"
                )
            },
        )


def test_render_systemd_unit_injected_directive_never_appears_in_output():
    """Defense-in-depth: confirm that no matter what, a rejected value never
    makes it into rendered unit text (the call raises before any string is
    returned)."""
    with pytest.raises(InvalidInstallValueError):
        render_systemd_unit(
            "/bin/service-directory",
            "/usr/bin",
            extra_env={"SERVICE_REGISTRY_HOST": "1.2.3.4\nExecStart=evil"},
        )


# --- render_launchd_plist XML-escapes rather than rejecting -----------------


def test_render_launchd_plist_escapes_xml_metacharacters_in_value():
    plist = render_launchd_plist(
        "/bin/service-directory",
        "/usr/bin",
        extra_env={
            "SERVICE_REGISTRY_CONFIG": "</string><key>ProgramArguments</key>",
        },
    )
    # The raw injection payload must never appear verbatim...
    assert (
        "<key>ProgramArguments</key>"
        not in plist.split("<key>SERVICE_REGISTRY_CONFIG</key>")[1].split("</dict>")[0]
        or "&lt;key&gt;ProgramArguments&lt;/key&gt;" in plist
    )
    # ...it must be escaped instead.
    assert "&lt;key&gt;ProgramArguments&lt;/key&gt;" in plist
    assert "&lt;/string&gt;" in plist
    # The plist must still only have ONE ProgramArguments key (the real one).
    assert plist.count("<key>ProgramArguments</key>") == 1


def test_render_launchd_plist_escapes_ampersand_and_lt_gt():
    plist = render_launchd_plist(
        "/bin/service-directory",
        "/usr/bin",
        extra_env={"SERVICE_REGISTRY_HOST": "a&b<c>d"},
    )
    assert "<string>a&amp;b&lt;c&gt;d</string>" in plist


# --- CLI surfaces the error cleanly instead of crashing ---------------------


def test_cli_service_install_with_malicious_config_fails_cleanly(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(
        "service_directory.service_manager.get_service_manager",
        lambda: SystemdUserServiceManager(
            runner=_RecordingRunner(), unit_dir=str(tmp_path)
        ),
    )

    rc = cli.main(
        [
            "service",
            "install",
            "--config",
            "/x.yaml\nExecStart=/bin/sh -c evil",
        ]
    )

    assert rc == 1  # fails cleanly, not an unhandled traceback
    captured = capsys.readouterr()
    assert "Error" in captured.err
    # No unit file must have been written with the injected content.
    unit_file = tmp_path / "service-directory.service"
    if unit_file.exists():
        assert "ExecStart=/bin/sh -c evil" not in unit_file.read_text()
