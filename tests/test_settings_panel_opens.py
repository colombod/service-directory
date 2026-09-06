"""Regression test: clicking #settings-btn must actually open the panel.

Bug: the served page's second inline <script> block (the settings-panel
script) contained a malformed JS string literal -- a literal backslash-n
(two characters: '\\' 'n') baked into the JS source instead of a real
newline escape. That is a JavaScript syntax error, which means the ENTIRE
<script> block containing `openSettings`/`settingsBtn.addEventListener(...)`
throws during parsing and never executes, so nothing is ever wired up.
Clicking the (present, but unwired) button then does nothing.

This test proves the fix two ways:

1. `node --check` on the raw extracted script text: the classic "does the
   JS even parse" check. This is the most direct regression guard for the
   exact defect (a syntax error) and fails hard against the pre-fix code.

2. A REAL end-to-end browser-like check: boot the actual FastAPI app with
   uvicorn on an ephemeral 127.0.0.1 port (never mocked), fetch the real
   served HTML from a real HTTP response, load it into a real DOM (jsdom)
   with scripts actually executing, and simulate a real click via
   dispatchEvent. This asserts the *result* (the overlay's hidden state
   changes, and the panel's content sections populate from the real
   /api/settings and /api/federation/peers endpoints served by the real
   app) rather than merely checking a listener object was attached.

Both node and a local jsdom install are required for the DOM-level test;
if either is unavailable in the environment the DOM test is skipped (the
syntax-check test has no such dependency and always runs).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time

import pytest
import uvicorn
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)


def _all_down(url: str) -> bool:
    return False


def _find_jsdom_root() -> str | None:
    """Locate a local (already-installed) jsdom, if any.

    We do not install anything as a side effect of running tests; if jsdom
    isn't present in one of the usual node_modules locations the DOM-level
    test is skipped, but the syntax-check test (which has no such
    dependency) still runs and still catches the regression.
    """
    candidates = [
        "/tmp/node_modules/jsdom",
        os.path.join(os.getcwd(), "node_modules", "jsdom"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def _make_config(tmp_path):
    return RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="100.1.2.3")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name="my-node",
            description="Test node",
            role="primary",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_write_token=False,
        ),
    )


class _ServerThread:
    """Runs the real FastAPI app via real uvicorn on a real ephemeral port."""

    def __init__(self, app):
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> str:
        self.thread.start()
        for _ in range(200):
            if getattr(self.server, "started", False):
                break
            time.sleep(0.01)
        sockets = self.server.servers[0].sockets
        host, port = sockets[0].getsockname()[:2]
        return f"http://{host}:{port}"

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


@pytest.fixture
def running_node(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    server = _ServerThread(app)
    base_url = server.start()
    try:
        yield base_url
    finally:
        server.stop()


# ---------------------------------------------------------------------------
# 1. Direct syntax-check of the extracted settings <script> block.
# ---------------------------------------------------------------------------


def _extract_settings_script(html: str) -> str:
    """Pull out the second inline <script> block (the settings-panel script).

    Identified by content, not position, so it's robust to unrelated
    ordering changes elsewhere on the page.
    """
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    for s in scripts:
        if "openSettings" in s and "settingsBtn" in s:
            return s
    raise AssertionError("could not find the settings-panel <script> block in HTML")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_settings_script_is_syntactically_valid_js(tmp_path):
    """The settings <script> block must parse as valid JavaScript.

    This is the most direct regression test for the reported defect: a
    stray literal backslash-n inside a JS string literal is a syntax
    error that aborts the WHOLE script block (including handler
    registration), even though the rest of the page loads fine and the
    API works. `node --check` parses without executing, so this fails
    hard against the pre-fix code and requires no browser/DOM stack.
    """
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 12345))
    resp = client.get("/")
    assert resp.status_code == 200
    script = _extract_settings_script(resp.text)

    script_path = tmp_path / "settings_script.js"
    script_path.write_text(script)

    result = subprocess.run(
        ["node", "--check", str(script_path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        "settings <script> block failed to parse as JavaScript "
        f"(this means NONE of its handlers -- including the settings-btn "
        f"click listener -- are ever registered):\n{result.stderr}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_main_script_is_also_syntactically_valid_js(tmp_path):
    """Sanity check: the OTHER inline script block (filter/viewer/etc.)
    must also remain syntactically valid -- guards against an unrelated
    regression introduced while fixing the settings script."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 12345))
    resp = client.get("/")
    html = resp.text
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    main_script = next(s for s in scripts if "service-filter" in s)

    script_path = tmp_path / "main_script.js"
    script_path.write_text(main_script)
    result = subprocess.run(
        ["node", "--check", str(script_path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# 2. Real end-to-end: real server, real HTTP fetch of the page, real DOM,
#    real click, asserting the resulting visible state (not just that a
#    listener got attached).
# ---------------------------------------------------------------------------

_JSDOM_DRIVER = r"""
const path = require("path");
const { JSDOM } = require(process.argv[2]);
const baseUrl = process.argv[3];

(async () => {
  const results = {};
  const errors = [];

  // Fetch the REAL served page over a REAL HTTP connection to the running
  // uvicorn server (not a mock, not a canned string).
  const pageResp = await fetch(baseUrl + "/");
  const html = await pageResp.text();
  results.page_status = pageResp.status;

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: baseUrl + "/",
    beforeParse(window) {
      // jsdom does not ship a fetch implementation; wire the real page's
      // fetch() calls through to Node's real fetch, hitting the REAL
      // running server for /api/settings and /api/federation/peers.
      window.fetch = (url, opts) => fetch(new URL(url, baseUrl).toString(), opts);
    },
  });
  dom.window.onerror = (msg) => { errors.push(String(msg)); };

  // Let inline <script> blocks finish executing.
  await new Promise((r) => setTimeout(r, 150));

  const doc = dom.window.document;
  const overlay = doc.getElementById("settings-overlay");
  const btn = doc.getElementById("settings-btn");
  const closeBtn = doc.getElementById("settings-close-btn");

  results.overlay_present = !!overlay;
  results.btn_present = !!btn;
  results.hidden_before_click = overlay.hasAttribute("hidden");

  btn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  // Allow the async /api/settings + /api/federation/peers fetches (real
  // network round trips to the real server) to resolve.
  await new Promise((r) => setTimeout(r, 300));

  results.hidden_after_click = overlay.hasAttribute("hidden");
  results.identity_html = doc.getElementById("settings-identity-content").innerHTML;
  results.peers_html = doc.getElementById("settings-peers-content").innerHTML;
  results.pairing_html = doc.getElementById("settings-pairing-content").innerHTML;

  // Escape key should close it again.
  doc.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));
  results.hidden_after_escape = overlay.hasAttribute("hidden");

  // Reopen, then close via the explicit close control.
  btn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  closeBtn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));
  results.hidden_after_close_btn = overlay.hasAttribute("hidden");

  results.js_errors = errors;

  process.stdout.write(JSON.stringify(results));
})().catch((e) => {
  process.stderr.write(String(e && e.stack || e));
  process.exit(1);
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_settings_button_click_opens_and_populates_panel_real_e2e(
    running_node, tmp_path
):
    """GIVEN the real dashboard served by a real running server,
    WHEN a real DOM dispatches a real click on #settings-btn,
    THEN the overlay's hidden state actually flips to visible, the
    identity/peers/pairing sections populate from the real API (no longer
    "Loading..."), Escape and the close button close it again, and no
    uncaught JS error occurs during load.

    This is the acceptance test: it inspects RESULTING STATE (hidden
    attribute, rendered content), not merely that a handler object exists.
    It fails against the pre-fix code (script syntax error => handler never
    registered => hidden attribute never changes) and passes after the fix.
    """
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; DOM-level e2e test skipped")

    driver_path = tmp_path / "driver.js"
    driver_path.write_text(_JSDOM_DRIVER)

    result = subprocess.run(
        [
            "node",
            str(driver_path),
            jsdom_root,
            running_node,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"jsdom driver failed.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    data = json.loads(result.stdout)

    assert data["page_status"] == 200
    assert data["overlay_present"] is True
    assert data["btn_present"] is True

    # Overlay starts hidden (matches the server-rendered `hidden` attribute).
    assert data["hidden_before_click"] is True, "overlay should start hidden"

    # THE regression: clicking the button must actually reveal the overlay.
    assert data["hidden_after_click"] is False, (
        "clicking #settings-btn did not make the overlay visible -- "
        "the click handler was never registered (this is the reported bug)"
    )

    # Content sections must be populated from the real API, not left on
    # their static "Loading..." placeholder.
    assert "Loading" not in data["identity_html"]
    assert "Loading" not in data["peers_html"]
    assert "Loading" not in data["pairing_html"]
    assert "my-node" in data["identity_html"]

    # Escape closes it again.
    assert data["hidden_after_escape"] is True, "Escape key did not close the overlay"

    # The explicit close control also closes it.
    assert data["hidden_after_close_btn"] is True, (
        "close button did not close the overlay"
    )

    # No uncaught JS error anywhere during the whole flow.
    assert data["js_errors"] == [], (
        f"uncaught JS error(s) during load/interaction: {data['js_errors']}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_settings_button_click_does_nothing_without_fix_would_fail(tmp_path):
    """Adversarial: directly assert that a script containing the exact
    original defect (a literal backslash-n baked into a JS string) fails
    `node --check`, while the corrected form passes. This nails down the
    precise mechanism (a JS syntax error), not just a plausible-sounding
    narrative -- run against a minimal reproduction of the bug pattern.
    """
    buggy = tmp_path / "buggy.js"
    buggy.write_text(
        "(function(){\n"
        "  function escHtml(s) {\n"
        "    return String(s || '').replace(/&/g,'&amp;');\\n\n"
        "  }\n"
        "})();\n"
    )
    result_buggy = subprocess.run(
        ["node", "--check", str(buggy)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result_buggy.returncode != 0, "expected the buggy pattern to fail to parse"

    fixed = tmp_path / "fixed.js"
    fixed.write_text(
        "(function(){\n"
        "  function escHtml(s) {\n"
        "    return String(s || '').replace(/&/g,'&amp;');\n"
        "  }\n"
        "})();\n"
    )
    result_fixed = subprocess.run(
        ["node", "--check", str(fixed)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result_fixed.returncode == 0, result_fixed.stderr
