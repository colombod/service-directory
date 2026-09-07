"""Settings restructured into a LATERAL (vertical) tab rail.

Acceptance criteria under test (see task spec):

1. A vertical tab rail (`role="tablist"`, `aria-orientation="vertical"`)
   lists the sections, and only the SELECTED section's panel is visible
   beside it -- not all sections stacked in one scrolling column.
2. Switching tabs swaps the visible pane with no page reload, and the rail
   marks the active tab via `aria-selected="true"` (exactly one at a time).
3. Roles are correct: `role="tablist"` / `role="tab"` / `role="tabpanel"`.
4. When `federation.enabled` is False, the Federation and Peers sections
   say so plainly and offer no peer actions.
5. Services tab: registration still works end-to-end.
6. `write-token-input` and `add-service-form` each appear exactly once.

These are REAL DOM tests (jsdom via a real running uvicorn server -- no
mocks of the thing under test) plus a couple of pure-HTML static assertions
that are cheap and still meaningful. The core "only one pane visible /
switching changes which pane is visible" tests below must FAIL against the
pre-restructure code (all sections in `.settings-body` with no rail, no
`hidden` panels) and pass after the fix.
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
from fastapi.testclient import TestClient
from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path, *, enabled: bool = True, name: str = "my-node"):
    return RegistryConfig(
        host_addresses=[HostAddress(label="Tailnet", host="100.1.2.3")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=enabled,
            name=name,
            description="Test node",
            role="primary",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_write_token=False,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 12345))


# ---------------------------------------------------------------------------
# Static HTML assertions (cheap, no node required)
# ---------------------------------------------------------------------------


def test_vertical_tablist_exists_with_correct_roles(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text

    tablist_match = re.search(
        r'<div[^>]*role="tablist"[^>]*>', html
    )
    assert tablist_match is not None, "no element with role=\"tablist\" found"
    assert 'aria-orientation="vertical"' in tablist_match.group(0), (
        "tablist must be aria-orientation=\"vertical\" (a LATERAL rail, "
        "not horizontal tabs)"
    )

    tabs = re.findall(r'<button[^>]*role="tab"[^>]*>', html)
    assert len(tabs) >= 5, f"expected at least 5 role=tab buttons, found {len(tabs)}"

    panels = re.findall(r'<div[^>]*role="tabpanel"[^>]*>', html)
    assert len(panels) >= 5, (
        f"expected at least 5 role=tabpanel elements, found {len(panels)}"
    )

    # Exactly one tab is marked selected in the initial server-rendered markup.
    selected_true = re.findall(r'aria-selected="true"', "".join(tabs))
    assert len(selected_true) == 1, (
        f"expected exactly one tab with aria-selected=\"true\", got {len(selected_true)}"
    )


def test_only_one_tabpanel_lacks_hidden_attribute_initially(tmp_path):
    """Only the selected section's panel is visible beside the rail --
    every other panel must carry the `hidden` attribute in the initial
    server-rendered markup. This is the direct HTML-level guard against
    'all sections stacked in one scrolling column' (the pre-fix shape had
    no `hidden` panels at all -- everything was always visible)."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text

    panels = re.findall(r'<div\s+role="tabpanel"[^>]*>', html)
    assert len(panels) >= 5
    hidden_count = sum(1 for p in panels if "hidden" in p)
    visible_count = len(panels) - hidden_count
    assert visible_count == 1, (
        f"expected exactly 1 visible (non-hidden) tabpanel initially, "
        f"got {visible_count} of {len(panels)} -- sections must not all be "
        f"stacked/visible at once"
    )


def test_write_token_input_and_add_service_form_appear_exactly_once(tmp_path):
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text

    assert html.count('id="write-token-input"') == 1
    assert html.count('id="add-service-form"') == 1


def test_all_named_dom_hooks_still_present(tmp_path):
    """Every DOM hook the task requires be preserved must still exist,
    exactly once where an id is involved."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text

    single_ids = [
        "settings-btn",
        "settings-overlay",
        "settings-close-btn",
        "settings-identity-content",
        "settings-peers-content",
        "settings-pairing-content",
        "settings-issue-code-btn",
        "settings-code-result",
        "settings-peer-url",
        "settings-peer-code",
        "settings-pair-btn",
        "settings-pair-error",
        "settings-pair-success",
        "sidebar-collapse-btn",
        "sidebar-expand-btn",
        "add-service-error",
    ]
    for hook in single_ids:
        count = html.count(f'id="{hook}"')
        assert count == 1, f"expected id=\"{hook}\" exactly once, found {count}"


# ---------------------------------------------------------------------------
# Real end-to-end: real server, real HTTP fetch, real jsdom DOM, real clicks.
# ---------------------------------------------------------------------------


def _find_jsdom_root() -> str | None:
    candidates = [
        "/tmp/node_modules/jsdom",
        os.path.join(os.getcwd(), "node_modules", "jsdom"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


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


@pytest.fixture
def running_node_no_federation(tmp_path):
    config = _make_config(tmp_path, enabled=False, name="standalone-node")
    app = create_app(config, checker=_all_down)
    server = _ServerThread(app)
    base_url = server.start()
    try:
        yield base_url
    finally:
        server.stop()


_TAB_SWITCH_DRIVER = r"""
const { JSDOM } = require(process.argv[2]);
const baseUrl = process.argv[3];

(async () => {
  const results = {};
  const errors = [];

  const pageResp = await fetch(baseUrl + "/");
  const html = await pageResp.text();
  results.page_status = pageResp.status;

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: baseUrl + "/",
    beforeParse(window) {
      window.fetch = (url, opts) => fetch(new URL(url, baseUrl).toString(), opts);
    },
  });
  dom.window.onerror = (msg) => { errors.push(String(msg)); };

  await new Promise((r) => setTimeout(r, 150));

  const doc = dom.window.document;
  const initialUrl = dom.window.location.href;

  // Open Settings.
  const settingsBtn = doc.getElementById("settings-btn");
  settingsBtn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));

  const tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
  results.tab_count = tabs.length;

  function visiblePanelIds() {
    return Array.from(doc.querySelectorAll('[role="tabpanel"]'))
      .filter((p) => !p.hidden)
      .map((p) => p.id);
  }

  results.visible_before_switch = visiblePanelIds();
  results.selected_before_switch = tabs
    .filter((t) => t.getAttribute("aria-selected") === "true")
    .map((t) => t.id);

  // Find the Services tab (registration) and the Security tab (write token)
  // by their aria-controls target, so this test doesn't hard-code exact
  // tab count/order beyond what the acceptance criteria require.
  const servicesTab = tabs.find((t) => {
    const panel = doc.getElementById(t.getAttribute("aria-controls"));
    return panel && panel.querySelector("#add-service-form");
  });
  const securityTab = tabs.find((t) => {
    const panel = doc.getElementById(t.getAttribute("aria-controls"));
    return panel && panel.querySelector("#write-token-input");
  });
  results.found_services_tab = !!servicesTab;
  results.found_security_tab = !!securityTab;

  // Switch to the Services tab.
  servicesTab.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));

  results.visible_after_switch_to_services = visiblePanelIds();
  results.services_tab_selected = servicesTab.getAttribute("aria-selected") === "true";
  results.only_one_other_selected = tabs.filter(
    (t) => t !== servicesTab && t.getAttribute("aria-selected") === "true"
  ).length;

  // Switch to Security tab.
  securityTab.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));
  results.visible_after_switch_to_security = visiblePanelIds();
  results.security_tab_selected = securityTab.getAttribute("aria-selected") === "true";

  results.url_after_switching = dom.window.location.href;
  results.navigated = results.url_after_switching !== initialUrl;

  results.js_errors = errors;

  process.stdout.write(JSON.stringify(results));
})().catch((e) => {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_switching_tabs_changes_visible_pane_no_reload(running_node, tmp_path):
    """GIVEN Settings is open with the vertical tab rail, WHEN a different
    tab is clicked, THEN the visible tabpanel changes, exactly one tab is
    marked aria-selected=true at a time, and no page navigation occurs.

    This is the direct acceptance test for 'switching works without
    reload' and 'exactly one pane visible at a time'. It FAILS against the
    pre-restructure code, which has no `role="tab"`/`role="tabpanel"`
    elements and no per-panel `hidden` toggling at all (everything was
    always visible, stacked).
    """
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; DOM-level e2e test skipped")

    driver_path = tmp_path / "driver.js"
    driver_path.write_text(_TAB_SWITCH_DRIVER)

    result = subprocess.run(
        ["node", str(driver_path), jsdom_root, running_node],
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
    assert data["tab_count"] >= 5
    assert data["found_services_tab"] is True
    assert data["found_security_tab"] is True

    # Exactly one pane visible before switching.
    assert len(data["visible_before_switch"]) == 1, (
        f"expected exactly one visible panel before switching, "
        f"got {data['visible_before_switch']}"
    )
    assert len(data["selected_before_switch"]) == 1

    # After switching to Services: exactly one visible panel, and it's the
    # Services panel; the previously visible panel must now be hidden.
    assert len(data["visible_after_switch_to_services"]) == 1, (
        f"expected exactly one visible panel after switching, got "
        f"{data['visible_after_switch_to_services']}"
    )
    assert data["visible_after_switch_to_services"] != data["visible_before_switch"], (
        "switching tabs did not change which pane is visible"
    )
    assert data["services_tab_selected"] is True
    assert data["only_one_other_selected"] == 0, (
        "more than one tab is marked aria-selected=true at once"
    )

    # Switch again to Security: pane changes again.
    assert len(data["visible_after_switch_to_security"]) == 1
    assert (
        data["visible_after_switch_to_security"]
        != data["visible_after_switch_to_services"]
    )
    assert data["security_tab_selected"] is True

    # No page reload/navigation occurred while switching tabs.
    assert data["navigated"] is False, "switching tabs triggered a page navigation"

    assert data["js_errors"] == [], f"uncaught JS errors: {data['js_errors']}"


_SERVICES_TAB_REGISTRATION_DRIVER = r"""
const { JSDOM } = require(process.argv[2]);
const baseUrl = process.argv[3];

(async () => {
  const results = {};
  const errors = [];

  const pageResp = await fetch(baseUrl + "/");
  const html = await pageResp.text();

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: baseUrl + "/",
    beforeParse(window) {
      window.fetch = (url, opts) => fetch(new URL(url, baseUrl).toString(), opts);
    },
  });
  dom.window.onerror = (msg) => { errors.push(String(msg)); };

  await new Promise((r) => setTimeout(r, 150));

  const doc = dom.window.document;
  const initialUrl = dom.window.location.href;

  const settingsBtn = doc.getElementById("settings-btn");
  settingsBtn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));

  const form = doc.getElementById("add-service-form");
  // The Services panel may start hidden (another tab selected by default);
  // navigate to its tab first, exactly as a real user would.
  const tabs = Array.from(doc.querySelectorAll('[role="tab"]'));
  const servicesTab = tabs.find((t) => {
    const panel = doc.getElementById(t.getAttribute("aria-controls"));
    return panel && panel.contains(form);
  });
  servicesTab.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 50));

  results.form_visible = !form.closest('[role="tabpanel"]').hidden;

  const nameInput = form.querySelector('input[name="name"]');
  const portInput = form.querySelector('input[name="port"]');
  nameInput.value = "lateral-tab-e2e-svc";
  portInput.value = "9321";

  form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 400));

  results.url_after_submit = dom.window.location.href;
  results.navigated = results.url_after_submit !== initialUrl;

  const newRow = doc.querySelector('.service[data-name="lateral-tab-e2e-svc"]');
  results.new_row_present = !!newRow;
  results.add_error_text = (doc.getElementById("add-service-error") || {}).textContent || "";

  results.js_errors = errors;
  process.stdout.write(JSON.stringify(results));
})().catch((e) => {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_services_tab_registration_still_works_e2e(running_node, tmp_path):
    """Relocating registration into a tabpanel must not break it: a real
    submission on the Services tab still registers the service and it
    appears in the catalogue with no page reload."""
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; DOM-level e2e test skipped")

    driver_path = tmp_path / "driver.js"
    driver_path.write_text(_SERVICES_TAB_REGISTRATION_DRIVER)

    result = subprocess.run(
        ["node", str(driver_path), jsdom_root, running_node],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"jsdom driver failed.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    data = json.loads(result.stdout)

    assert data["form_visible"] is True
    assert data["navigated"] is False
    assert data["new_row_present"] is True, "registered service did not appear in catalogue"
    assert data["add_error_text"] == ""
    assert data["js_errors"] == []


# ---------------------------------------------------------------------------
# Registration negative path still works from the Services tab (existing
# error shape, nothing registered).
# ---------------------------------------------------------------------------


def test_registration_missing_token_refused_with_existing_error_shape(tmp_path):
    config = RegistryConfig(
        host_addresses=[],
        services=[],
        federation=FederationConfig(
            enabled=True,
            name="tok-node",
            state_dir=str(tmp_path / "state"),
            require_write_token=True,
        ),
    )
    app = create_app(config, checker=_all_down)
    client = _localhost_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "nope", "port": 1234},
    )
    assert resp.status_code in (401, 403)
    body = resp.json()
    assert "detail" in body

    # Nothing was registered.
    listing = client.get("/api/services").json()
    names = [s["name"] for s in listing] if isinstance(listing, list) else []
    assert "nope" not in names


# ---------------------------------------------------------------------------
# Federation-disabled: Federation and Peers panels say so plainly, no peer
# actions offered.
# ---------------------------------------------------------------------------

_FEDERATION_DISABLED_DRIVER = r"""
const { JSDOM } = require(process.argv[2]);
const baseUrl = process.argv[3];

(async () => {
  const results = {};
  const errors = [];

  const pageResp = await fetch(baseUrl + "/");
  const html = await pageResp.text();

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    resources: "usable",
    url: baseUrl + "/",
    beforeParse(window) {
      window.fetch = (url, opts) => fetch(new URL(url, baseUrl).toString(), opts);
    },
  });
  dom.window.onerror = (msg) => { errors.push(String(msg)); };

  await new Promise((r) => setTimeout(r, 150));

  const doc = dom.window.document;
  const settingsBtn = doc.getElementById("settings-btn");
  settingsBtn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));

  const pairingContent = doc.getElementById("settings-pairing-content");
  const peersContent = doc.getElementById("settings-peers-content");

  results.pairing_html = pairingContent.innerHTML;
  results.peers_html = peersContent.innerHTML;

  // No peer-action controls should be usable/visible: the issue-code and
  // pair buttons live inside .pairing-subsection elements which must be
  // hidden when federation is disabled.
  const subsections = Array.from(pairingContent.querySelectorAll(".pairing-subsection"));
  results.any_subsection_visible = subsections.some((s) => !s.hidden);

  results.js_errors = errors;
  process.stdout.write(JSON.stringify(results));
})().catch((e) => {
  process.stderr.write(String((e && e.stack) || e));
  process.exit(1);
});
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_federation_disabled_says_so_plainly_no_peer_actions(
    running_node_no_federation, tmp_path
):
    """GIVEN a node with federation.enabled: false, THEN the Federation and
    Peers panels say so plainly and offer no peer actions."""
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; DOM-level e2e test skipped")

    driver_path = tmp_path / "driver.js"
    driver_path.write_text(_FEDERATION_DISABLED_DRIVER)

    result = subprocess.run(
        ["node", str(driver_path), jsdom_root, running_node_no_federation],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (
        f"jsdom driver failed.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    data = json.loads(result.stdout)

    assert "disabled" in data["pairing_html"].lower()
    assert "disabled" in data["peers_html"].lower()
    assert data["any_subsection_visible"] is False, (
        "pairing action controls (issue code / pair with peer) are still "
        "visible even though federation is disabled"
    )
    assert data["js_errors"] == []
