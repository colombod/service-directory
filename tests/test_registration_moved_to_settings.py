"""Registration UI relocation: landing page -> Settings.

Task: registering a service is an ADMINISTRATIVE action (AGENTS.md Sec 2:
"Settings is the home for node/fleet management") and must not live on the
landing page a person sees when they arrive. This module asserts:

1. The landing page's viewer-default area contains NO registration form
   (no `<details class="registration-panel">`, no `id="add-service-form"`
   outside Settings) -- a hermetic, string/DOM-based check.
2. `id="write-token-input"` appears EXACTLY ONCE in the whole rendered
   document (the pre-fix code renders it twice: once in the landing
   registration panel, once in the Settings overlay -- duplicate ids are
   invalid HTML and make ``getElementById`` order-dependent).
3. Registration still WORKS when driven from Settings: a valid write token
   POSTs successfully and the new service is reachable via the API/catalogue;
   a missing/invalid token is refused with the existing error shape and
   nothing is persisted.
4. A REAL end-to-end browser-like check (uvicorn + jsdom, exactly the
   pattern established in test_settings_panel_opens.py): open Settings,
   fill in and submit the real #add-service-form, and observe the new
   service appear in the real DOM's sidebar catalogue WITHOUT a page
   navigation (jsdom's `window.location` stays on the same document/URL
   the whole time -- a `location.reload()`/navigation would be observable
   as the document being torn down and re-fetched, which this test would
   not see if it just polled for page content).

The tests in section 1-2 are written to FAIL against the pre-fix code
(landing page still contains <details class="registration-panel"> and
write-token-input renders twice) and PASS after the relocation.
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
from service_directory.app import _render_html, create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)
from service_directory.write_token import issue_write_token


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path, *, require_write_token: bool = False, name: str = "local-node"):
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name=name,
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_write_token=require_write_token,
        ),
    )


def _localhost_client(app) -> TestClient:
    return TestClient(app, client=("127.0.0.1", 12345))


def _remote_client(app) -> TestClient:
    return TestClient(app, client=("203.0.113.9", 12345))


# ---------------------------------------------------------------------------
# 1 & 2: hermetic HTML-structure assertions (no server, no browser).
# ---------------------------------------------------------------------------


def _viewer_default_html(html: str) -> str:
    """Extract the `<div class="viewer-default">...</div>` block (the
    landing-page content shown before any service is opened) so we can
    assert about ITS contents specifically, not the whole document (the
    Settings overlay legitimately contains an add-service-form; the viewer
    default area must not)."""
    match = re.search(
        r'<div class="viewer-default">(.*?)</div>\s*</div>\s*</div>\s*</div>\s*</div>',
        html,
        re.DOTALL,
    )
    assert match, "could not locate viewer-default block in rendered HTML"
    return match.group(1)


def test_landing_page_viewer_default_has_no_registration_form(tmp_path):
    """THE regression test: the landing page (viewer-default area) must
    contain NEITHER the registration <details> panel NOR the add-service
    form/write-token input. Fails against pre-fix code, where the viewer
    default area embeds <details class="registration-panel"> containing
    #add-service-form and #write-token-input.
    """
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text

    viewer_default = _viewer_default_html(html)

    assert "registration-panel" not in viewer_default
    assert 'id="add-service-form"' not in viewer_default
    assert 'id="write-token-input"' not in viewer_default
    assert "Register a service" not in viewer_default
    assert "Add service" not in viewer_default


def test_landing_page_has_no_registration_panel_anywhere_in_viewer(tmp_path):
    """Belt-and-suspenders: the <details class="registration-panel"> element
    itself must be gone from the document entirely (not merely moved but
    still called that) -- the task removes it as a landing-page concept.
    """
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text
    assert '<details class="registration-panel">' not in html


def test_write_token_input_appears_exactly_once(tmp_path):
    """THE duplicate-id bug: id="write-token-input" must appear EXACTLY
    ONCE in the whole document. Pre-fix code renders it twice (landing
    registration panel + Settings overlay) -- invalid HTML, and
    getElementById silently picks whichever the parser saw first."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text
    assert html.count('id="write-token-input"') == 1


def test_write_token_input_exactly_once_empty_catalogue(tmp_path):
    """Same invariant holds for the empty-catalogue render path
    (_render_html([]) is exercised directly by other tests -- keep it
    covered here too since the empty-state branch renders separate markup)."""
    html = _render_html([], node_info=[{"name": "local-node", "description": None}])
    assert html.count('id="write-token-input"') == 1
    assert '<details class="registration-panel">' not in html


def test_add_service_form_present_exactly_once_in_settings(tmp_path):
    """The form itself must still exist -- just once, and inside Settings."""
    config = _make_config(tmp_path)
    app = create_app(config, checker=_all_down)
    html = _localhost_client(app).get("/").text
    assert html.count('id="add-service-form"') == 1
    assert html.count('id="add-service-error"') == 1

    # It must live inside the settings overlay, not the viewer.
    overlay_start = html.index('id="settings-overlay"')
    form_index = html.index('id="add-service-form"')
    close_settings_index = html.index("</html>")
    assert overlay_start < form_index < close_settings_index

    viewer_default = _viewer_default_html(html)
    assert 'id="add-service-form"' not in viewer_default


# ---------------------------------------------------------------------------
# 3: registration still works end-to-end via the real API (TestClient),
#    exercising the exact auth gate the relocated form calls into.
# ---------------------------------------------------------------------------


def test_registration_with_valid_write_token_succeeds_and_is_visible(tmp_path):
    """A valid write token registers the service and it appears in the
    catalogue -- the real behaviour the relocated Settings form drives."""
    config = _make_config(tmp_path, require_write_token=True)
    token = issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "moved-form-svc", "port": 4321, "description": "via settings"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "moved-form-svc"

    catalogue = client.get(
        "/api/services", headers={"Authorization": f"Bearer {token}"}
    ).json()
    names = {svc["name"] for svc in catalogue}
    assert "moved-form-svc" in names

    html = client.get("/", headers={"Authorization": f"Bearer {token}"}).text
    assert 'data-name="moved-form-svc"' in html


def test_registration_missing_token_refused_with_existing_error_shape(tmp_path):
    """No token from a non-localhost client -- refused (401), same shape
    as before the move, and nothing is registered."""
    config = _make_config(tmp_path, require_write_token=True)
    issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post(
        "/api/services", json={"name": "should-not-exist", "port": 1}
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()

    check = client.get("/api/services")
    names = {svc["name"] for svc in check.json()}
    assert "should-not-exist" not in names


def test_registration_invalid_token_refused_with_existing_error_shape(tmp_path):
    """A wrong token is refused (401) and nothing is registered -- same
    contract as before the move; only the UI location changed."""
    config = _make_config(tmp_path, require_write_token=True)
    issue_write_token(config.federation.state_dir)
    app = create_app(config, checker=_all_down)
    client = _remote_client(app)

    resp = client.post(
        "/api/services",
        json={"name": "should-not-exist-2", "port": 1},
        headers={"Authorization": "Bearer totally-wrong-token"},
    )
    assert resp.status_code == 401
    assert "detail" in resp.json()

    check = client.get("/api/services")
    names = {svc["name"] for svc in check.json()}
    assert "should-not-exist-2" not in names


# ---------------------------------------------------------------------------
# 4: REAL end-to-end -- real uvicorn server, real HTTP fetch, real jsdom DOM,
#    real form submission, asserting the resulting DOM state (not a mock).
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


_JSDOM_DRIVER = r"""
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

  // Landing page: no registration form anywhere in the initial DOM's
  // viewer-default area.
  const viewerDefault = doc.querySelector(".viewer-default");
  results.viewer_default_has_form = !!(viewerDefault && viewerDefault.querySelector("#add-service-form"));

  // Open Settings (real click, same as test_settings_panel_opens.py).
  const settingsBtn = doc.getElementById("settings-btn");
  settingsBtn.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));

  const form = doc.getElementById("add-service-form");
  results.form_present_in_settings = !!form;

  // Fill in and submit the real form.
  const nameInput = form.querySelector('input[name="name"]');
  const portInput = form.querySelector('input[name="port"]');
  nameInput.value = "e2e-registered-svc";
  portInput.value = "9999";

  form.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  // Allow the POST + catalogue refresh fetch to resolve.
  await new Promise((r) => setTimeout(r, 400));

  results.url_after_submit = dom.window.location.href;
  results.navigated = results.url_after_submit !== initialUrl;

  // The new service must now be present in the sidebar catalogue DOM,
  // without any navigation having occurred.
  const newRow = doc.querySelector('.service[data-name="e2e-registered-svc"]');
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
def test_settings_registration_real_e2e_no_page_reload(running_node, tmp_path):
    """Real server + real jsdom DOM + a real form submission: opening
    Settings and submitting #add-service-form registers the service and it
    shows up in the sidebar catalogue, all WITHOUT navigating away from the
    original document (no location.reload()/navigation)."""
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; DOM-level e2e test skipped")

    driver_path = tmp_path / "driver.js"
    driver_path.write_text(_JSDOM_DRIVER)

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
    assert data["viewer_default_has_form"] is False, (
        "the landing page's viewer-default area still contains the "
        "registration form -- it must live in Settings only"
    )
    assert data["form_present_in_settings"] is True

    assert data["navigated"] is False, (
        "submitting the registration form triggered a page navigation "
        "(e.g. window.location.reload()) -- the task requires the new "
        "service to appear in the catalogue WITHOUT a page reload"
    )
    assert data["new_row_present"] is True, (
        "the newly registered service did not appear in the sidebar "
        "catalogue after submitting the form"
    )
    assert data["add_error_text"] == ""
    assert data["js_errors"] == [], f"uncaught JS error(s): {data['js_errors']}"
