"""Maintenance settings UI regression coverage.

These tests exercise the existing inline Settings -> Maintenance panel with a
real Node + jsdom DOM, but without launching a real browser or HTTP server.
The page HTML comes from the real FastAPI app; the maintenance/settings fetches
are stubbed inside jsdom so the tests can drive exact polling, disconnects,
reconnects, and ambiguous POST outcomes hermetically.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service_directory.app import create_app
from service_directory.config import (
    FederationConfig,
    HostAddress,
    RegistryConfig,
    Service,
)


CURRENT_REVISION = "a" * 40
TARGET_REVISION = "b" * 40


def _all_down(url: str) -> bool:
    return False


def _make_config(tmp_path) -> RegistryConfig:
    return RegistryConfig(
        host_addresses=[HostAddress(label="LAN", host="10.0.0.1")],
        services=[Service(name="Resolve", port=8080, path="/", description="d")],
        federation=FederationConfig(
            enabled=True,
            name="local-node",
            description="Test node",
            role="primary",
            base_url="http://10.0.0.1:80",
            state_dir=str(tmp_path / "state"),
            require_write_token=False,
            require_read_token=False,
        ),
    )


def _render_page_html(tmp_path) -> str:
    app = create_app(_make_config(tmp_path), checker=_all_down)
    client = TestClient(app, raise_server_exceptions=True, client=("127.0.0.1", 12345))
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def _extract_settings_script(html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    for script in scripts:
        if "settings-maintenance-content" in script and "openSettings" in script:
            return script
    raise AssertionError("could not find the settings maintenance script block")


def _find_jsdom_root() -> str | None:
    candidates = [
        "/tmp/node_modules/jsdom",
        os.path.join(os.getcwd(), "node_modules", "jsdom"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def _settings_payload() -> dict:
    return {
        "name": "local-node",
        "description": "Test node",
        "role": "primary",
        "base_url": "http://10.0.0.1:80",
        "host_addresses": [{"label": "LAN", "host": "10.0.0.1"}],
        "federation_enabled": True,
    }


def _job_payload(
    job_id: str,
    *,
    status: str,
    message: str,
    steps: list[str] | None = None,
    started_at: float = 1_700_000_000,
    finished_at: float | None = None,
) -> dict:
    return {
        "id": job_id,
        "status": status,
        "message": message,
        "steps": steps or [],
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _status_payload(
    *,
    update_available,
    update_supported: bool = True,
    unsupported_reason: str | None = None,
    checked_at: float | None = 1_700_000_000,
    latest_revision: str | None = TARGET_REVISION,
    latest_version: str | None = "1.2.4",
    job: dict | None = None,
) -> dict:
    return {
        "version": "1.2.3",
        "install_kind": "git",
        "update_supported": update_supported,
        "unsupported_reason": unsupported_reason,
        "current_revision": CURRENT_REVISION,
        "update_available": update_available,
        "latest_revision": latest_revision,
        "latest_version": latest_version,
        "checked_at": checked_at,
        "job": job,
    }


def _base_routes(*maintenance_statuses: dict, extra: dict[str, list[dict]] | None = None) -> dict[str, list[dict]]:
    routes: dict[str, list[dict]] = {
        "GET /api/settings": [{"json": _settings_payload()}],
        "GET /api/federation/peers": [{"json": []}],
        "GET /api/maintenance": [{"json": status} for status in maintenance_statuses],
    }
    if extra:
        routes.update(extra)
    return routes


_JSDOM_DRIVER = r"""
const fs = require("fs");
const { JSDOM } = require(process.argv[2]);
const scenario = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const html = fs.readFileSync(scenario.html_path, "utf8");
const baseUrl = scenario.base_url || "http://example.test/";
const errors = [];
const fetchLog = [];

function deepCopy(value) {
  return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

class Scheduler {
  constructor() {
    this.now = 0;
    this.nextId = 1;
    this.tasks = new Map();
  }

  setTimeout(fn, delay) {
    const id = this.nextId++;
    this.tasks.set(id, { due: this.now + Number(delay || 0), fn });
    return id;
  }

  clearTimeout(id) {
    this.tasks.delete(id);
  }

  advance(ms) {
    this.now += Number(ms || 0);
    this.runDue();
  }

  runDue() {
    while (true) {
      const ready = Array.from(this.tasks.entries())
        .filter(([, task]) => task.due <= this.now)
        .sort((a, b) => a[1].due - b[1].due || a[0] - b[0]);
      if (!ready.length) {
        break;
      }
      const [id, task] = ready[0];
      this.tasks.delete(id);
      task.fn();
    }
  }

  pendingDelays() {
    return Array.from(this.tasks.values())
      .map((task) => task.due - this.now)
      .sort((a, b) => a - b);
  }
}

const scheduler = new Scheduler();
const routeQueues = {};
for (const [key, specs] of Object.entries(scenario.routes || {})) {
  routeQueues[key] = specs.map((spec) => deepCopy(spec));
}

function nextSpec(key) {
  const queue = routeQueues[key];
  if (!queue || !queue.length) {
    throw new Error("No stub for " + key);
  }
  if (queue.length > 1) {
    return queue.shift();
  }
  return deepCopy(queue[0]);
}

function fetchStub(url, opts) {
  opts = opts || {};
  const method = String(opts.method || "GET").toUpperCase();
  const absolute = new URL(url, baseUrl);
  const key = method + " " + absolute.pathname;
  const spec = nextSpec(key);
  const record = { key, method, path: absolute.pathname, result: "pending" };
  fetchLog.push(record);

  return new Promise((resolve, reject) => {
    let settled = false;
    let abortListener = null;

    function settle(kind, payload) {
      if (settled) {
        return;
      }
      settled = true;
      record.result = kind;
      if (abortListener && opts.signal) {
        opts.signal.removeEventListener("abort", abortListener);
      }
      if (kind === "resolved") {
        resolve(payload);
      } else {
        reject(payload);
      }
    }

    abortListener = () => {
      const error = new Error(spec.abortMessage || "The operation was aborted");
      error.name = "AbortError";
      record.error_name = error.name;
      settle("aborted", error);
    };

    if (opts.signal) {
      if (opts.signal.aborted) {
        abortListener();
        return;
      }
      opts.signal.addEventListener("abort", abortListener, { once: true });
    }

    const deliver = () => {
      if (spec.type === "reject") {
        const error = new Error(spec.message || "network error");
        error.name = spec.name || "Error";
        record.error_name = error.name;
        settle("rejected", error);
        return;
      }
      if (spec.type === "hang") {
        return;
      }
      const status = spec.status == null ? 200 : spec.status;
      const body = spec.json == null ? {} : spec.json;
      const response = {
        ok: status >= 200 && status < 300,
        status,
        json() {
          return Promise.resolve(deepCopy(body));
        },
        text() {
          return Promise.resolve(JSON.stringify(body));
        },
      };
      settle("resolved", response);
    };

    const delayMs = Number(spec.delayMs || 0);
    if (delayMs > 0) {
      scheduler.setTimeout(deliver, delayMs);
    } else {
      deliver();
    }
  });
}

async function flushMicrotasks(turns = 8) {
  for (let i = 0; i < turns; i += 1) {
    await Promise.resolve();
  }
}

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  resources: "usable",
  url: baseUrl,
  pretendToBeVisual: true,
  beforeParse(window) {
    window.fetch = fetchStub;
    window.confirm = () => scenario.confirm !== false;
    window.alert = () => {};
    window.AbortController = global.AbortController;
    window.setTimeout = (fn, delay) => scheduler.setTimeout(fn, delay);
    window.clearTimeout = (id) => scheduler.clearTimeout(id);
    window.Date.now = () => scheduler.now;
  },
});
dom.window.onerror = (msg) => {
  errors.push(String(msg));
};

function text(selector) {
  const el = dom.window.document.querySelector(selector);
  return el ? el.textContent.trim() : null;
}

function htmlOf(selector) {
  const el = dom.window.document.querySelector(selector);
  return el ? el.innerHTML : null;
}

function countsByKey() {
  const counts = {};
  for (const call of fetchLog) {
    counts[call.key] = (counts[call.key] || 0) + 1;
  }
  return counts;
}

function collectState() {
  const content = dom.window.document.getElementById("settings-maintenance-content");
  return {
    overlay_hidden: dom.window.document.getElementById("settings-overlay")?.hasAttribute("hidden") ?? null,
    tracked_job_id: content?.dataset.trackedJobId || null,
    ownership_state: content?.dataset.ownershipState || null,
    poll_reads: Number(content?.dataset.pollReads || 0),
    elapsed_ms: Number(content?.dataset.pollElapsedMs || 0),
    running_version: text("#settings-maintenance-running-version"),
    current_revision: text("#settings-maintenance-current-revision"),
    install_kind: text("#settings-maintenance-install-kind"),
    support_text: text("#settings-maintenance-support"),
    support_html: htmlOf("#settings-maintenance-support"),
    last_checked: text("#settings-maintenance-last-checked"),
    update_state: text("#settings-maintenance-update-state"),
    update_target: text("#settings-maintenance-update-target"),
    job_id_text: text("#settings-maintenance-job-id"),
    status_text: text("#settings-maintenance-job-status"),
    started_text: text("#settings-maintenance-job-started"),
    finished_text: text("#settings-maintenance-job-finished"),
    job_message_text: text("#settings-maintenance-job-message"),
    job_message_html: htmlOf("#settings-maintenance-job-message"),
    note_text: text("#settings-maintenance-note"),
    steps: Array.from(dom.window.document.querySelectorAll("#settings-maintenance-job-steps li")).map((li) => li.textContent.trim()),
    update_button_disabled: Boolean(dom.window.document.getElementById("settings-update-btn")?.disabled),
    update_button_label: text("#settings-update-btn"),
    counts_by_key: countsByKey(),
    fetch_calls: fetchLog.map((call) => ({ ...call })),
    pending_timer_delays: scheduler.pendingDelays(),
    xss_support_present: Boolean(dom.window.document.getElementById("xss-support")),
    xss_job_present: Boolean(dom.window.document.getElementById("xss-job")),
    xss_flag: Boolean(dom.window.__xss__),
    js_errors: errors.slice(),
  };
}

async function click(action) {
  const selector = action.id ? "#" + action.id : action.selector;
  const el = dom.window.document.querySelector(selector);
  if (!el) {
    throw new Error("Missing element for click: " + selector);
  }
  el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  await flushMicrotasks();
}

(async () => {
  await flushMicrotasks();
  const results = { snapshots: {} };

  for (const action of scenario.actions || []) {
    if (action.type === "click") {
      await click(action);
    } else if (action.type === "advance") {
      const times = Number(action.times || 1);
      for (let i = 0; i < times; i += 1) {
        scheduler.advance(Number(action.ms || 0));
        await flushMicrotasks();
      }
    } else if (action.type === "flush") {
      await flushMicrotasks(Number(action.turns || 8));
    } else if (action.type === "capture") {
      await flushMicrotasks();
      results.snapshots[action.name] = collectState();
    } else {
      throw new Error("Unknown action type: " + action.type);
    }
  }

  results.final = collectState();
  process.stdout.write(JSON.stringify(results));
})().catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exit(1);
});
"""


def _run_jsdom_scenario(tmp_path: Path, scenario: dict) -> dict:
    jsdom_root = _find_jsdom_root()
    if jsdom_root is None:
        pytest.skip("jsdom not installed locally; maintenance DOM test skipped")

    html_path = tmp_path / "maintenance_page.html"
    html_path.write_text(_render_page_html(tmp_path))

    driver_path = tmp_path / "maintenance_driver.js"
    driver_path.write_text(_JSDOM_DRIVER)

    scenario_path = tmp_path / "maintenance_scenario.json"
    scenario_path.write_text(
        json.dumps(
            {
                "html_path": str(html_path),
                "base_url": "http://example.test/",
                **scenario,
            }
        )
    )

    result = subprocess.run(
        ["node", str(driver_path), jsdom_root, str(scenario_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (
        "maintenance jsdom driver failed.\n"
        f"stdout={result.stdout}\n"
        f"stderr={result.stderr}"
    )
    return json.loads(result.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_status_states_and_disable_rules(tmp_path):
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=None, checked_at=None, latest_revision=None, latest_version=None),
                _status_payload(
                    update_available=False,
                    checked_at=1_700_000_300,
                    latest_revision=CURRENT_REVISION,
                    latest_version="1.2.3",
                ),
                _status_payload(update_available=True, checked_at=1_700_000_600),
                _status_payload(
                    update_available=True,
                    update_supported=False,
                    unsupported_reason="managed service required",
                    checked_at=1_700_000_900,
                ),
                _status_payload(
                    update_available=True,
                    checked_at=1_700_001_200,
                    job=_job_payload(
                        "1" * 32,
                        status="running",
                        message="Updating; the directory may disconnect while its service restarts.",
                        steps=["stop"],
                    ),
                ),
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "unknown"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "current"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "available"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "unsupported"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "busy"},
            ],
        },
    )

    unknown = data["snapshots"]["unknown"]
    current = data["snapshots"]["current"]
    available = data["snapshots"]["available"]
    unsupported = data["snapshots"]["unsupported"]
    busy = data["snapshots"]["busy"]

    assert unknown["running_version"] == "1.2.3"
    assert unknown["current_revision"] == CURRENT_REVISION
    assert unknown["install_kind"] == "git"
    assert unknown["support_text"] == "supported"
    assert unknown["last_checked"] == "—"
    assert unknown["update_state"] == "unknown"
    assert unknown["update_target"] == "—"
    assert unknown["update_button_disabled"] is True

    assert current["update_state"] == "current"
    assert current["update_target"] == "1.2.3 · " + CURRENT_REVISION
    assert current["update_button_disabled"] is True

    assert available["update_state"] == "available"
    assert available["update_target"] == "1.2.4 · " + TARGET_REVISION
    assert available["update_button_disabled"] is False
    assert available["update_button_label"] == "Install update & restart"

    assert unsupported["support_text"] == "managed service required"
    assert unsupported["update_button_disabled"] is True

    assert busy["status_text"] == "running"
    assert busy["update_button_disabled"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_polls_exact_returned_job_id(tmp_path):
    job_id = "2" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        }
                    ],
                    f"GET /api/maintenance/jobs/{job_id}": [
                        {
                            "json": _job_payload(
                                job_id,
                                status="running",
                                message="Updating; the directory may disconnect while its service restarts.",
                                steps=["stop"],
                            )
                        },
                        {
                            "json": _job_payload(
                                job_id,
                                status="succeeded",
                                message="Update completed and the restarted directory responded.",
                                steps=["stop", "reinstall", "restart"],
                                finished_at=1_700_000_900,
                            )
                        },
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_post"},
                {"type": "advance", "ms": 2999},
                {"type": "capture", "name": "before_first_poll"},
                {"type": "advance", "ms": 1},
                {"type": "capture", "name": "after_first_poll"},
                {"type": "advance", "ms": 3000},
                {"type": "capture", "name": "after_second_poll"},
            ],
        },
    )

    after_post = data["snapshots"]["after_post"]
    before_first_poll = data["snapshots"]["before_first_poll"]
    after_first_poll = data["snapshots"]["after_first_poll"]
    after_second_poll = data["snapshots"]["after_second_poll"]

    assert after_post["tracked_job_id"] == job_id
    assert after_post["ownership_state"] == "exact"
    assert after_post["update_button_disabled"] is True
    assert after_post["counts_by_key"]["POST /api/maintenance/update"] == 1
    assert before_first_poll["counts_by_key"].get(f"GET /api/maintenance/jobs/{job_id}", 0) == 0
    assert after_first_poll["counts_by_key"][f"GET /api/maintenance/jobs/{job_id}"] == 1
    assert after_first_poll["status_text"] == "running"
    assert after_second_poll["counts_by_key"][f"GET /api/maintenance/jobs/{job_id}"] == 2
    assert after_second_poll["status_text"] == "succeeded"
    assert after_second_poll["steps"] == ["stop", "reinstall", "restart"]
    assert all(
        call["path"] == f"/api/maintenance/jobs/{job_id}"
        for call in after_second_poll["fetch_calls"]
        if call["key"].startswith("GET /api/maintenance/jobs/")
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_hiding_overlay_stops_polling(tmp_path):
    job_id = "3" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        }
                    ],
                    f"GET /api/maintenance/jobs/{job_id}": [
                        {
                            "json": _job_payload(
                                job_id,
                                status="running",
                                message="Updating; the directory may disconnect while its service restarts.",
                                steps=["stop"],
                            )
                        },
                        {"type": "hang"},
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "capture", "name": "before_hide"},
                {"type": "click", "id": "settings-close-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_hide"},
                {"type": "advance", "ms": 12000},
                {"type": "flush"},
                {"type": "capture", "name": "after_wait"},
            ],
        },
    )

    before_hide = data["snapshots"]["before_hide"]
    after_hide = data["snapshots"]["after_hide"]
    after_wait = data["snapshots"]["after_wait"]

    assert before_hide["counts_by_key"][f"GET /api/maintenance/jobs/{job_id}"] == 2
    assert any(
        call["path"] == f"/api/maintenance/jobs/{job_id}" and call["result"] == "aborted"
        for call in after_hide["fetch_calls"]
    )
    assert after_hide["overlay_hidden"] is True
    assert after_wait["counts_by_key"][f"GET /api/maintenance/jobs/{job_id}"] == 2
    assert after_wait["pending_timer_delays"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_reopen_resumes_known_job_without_new_post(tmp_path):
    tracked_job_id = "4" * 32
    latest_job_id = "f" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                _status_payload(
                    update_available=True,
                    job=_job_payload(
                        latest_job_id,
                        status="running",
                        message="Some updater is running on this node.",
                        steps=["stop"],
                    ),
                ),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                tracked_job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        }
                    ],
                    f"GET /api/maintenance/jobs/{tracked_job_id}": [
                        {
                            "json": _job_payload(
                                tracked_job_id,
                                status="running",
                                message="Updating; the directory may disconnect while its service restarts.",
                                steps=["stop"],
                            )
                        },
                        {
                            "json": _job_payload(
                                tracked_job_id,
                                status="succeeded",
                                message="Update completed and the restarted directory responded.",
                                steps=["stop", "reinstall", "restart"],
                                finished_at=1_700_000_900,
                            )
                        },
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "click", "id": "settings-close-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 6000},
                {"type": "flush"},
                {"type": "capture", "name": "while_hidden"},
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "reopened"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "capture", "name": "after_resume_poll"},
            ],
        },
    )

    reopened = data["snapshots"]["reopened"]
    after_resume_poll = data["snapshots"]["after_resume_poll"]

    assert reopened["tracked_job_id"] == tracked_job_id
    assert reopened["job_id_text"] == tracked_job_id
    assert reopened["ownership_state"] == "exact"
    assert reopened["counts_by_key"]["POST /api/maintenance/update"] == 1
    assert reopened["counts_by_key"]["GET /api/maintenance"] == 2
    assert reopened["counts_by_key"].get(f"GET /api/maintenance/jobs/{latest_job_id}", 0) == 0
    assert after_resume_poll["counts_by_key"][f"GET /api/maintenance/jobs/{tracked_job_id}"] == 2
    assert after_resume_poll["status_text"] == "succeeded"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_budget_exhaustion_marks_unconfirmed_not_failed(tmp_path):
    job_id = "5" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        }
                    ],
                    f"GET /api/maintenance/jobs/{job_id}": [
                        {
                            "json": _job_payload(
                                job_id,
                                status="running",
                                message="Updating; the directory may disconnect while its service restarts.",
                                steps=["stop"],
                            )
                        }
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 3000, "times": 340},
                {"type": "capture", "name": "exhausted"},
                {"type": "advance", "ms": 9000},
                {"type": "capture", "name": "after_wait"},
            ],
        },
    )

    exhausted = data["snapshots"]["exhausted"]
    after_wait = data["snapshots"]["after_wait"]

    assert exhausted["poll_reads"] == 340 or exhausted["elapsed_ms"] >= 1_020_000
    assert exhausted["status_text"] == "unconfirmed"
    assert "manual refresh" in exhausted["note_text"].lower()
    assert exhausted["job_message_text"] != "Update did not complete. Check service-directory logs/doctor on this node."
    assert after_wait["counts_by_key"][f"GET /api/maintenance/jobs/{job_id}"] == exhausted["counts_by_key"][
        f"GET /api/maintenance/jobs/{job_id}"
    ]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_post_failure_does_not_replay_or_claim_latest_job(tmp_path):
    latest_job_id = "6" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                _status_payload(
                    update_available=True,
                    job=_job_payload(
                        latest_job_id,
                        status="running",
                        message="A node update may already be in progress.",
                        steps=["stop"],
                    ),
                ),
                extra={
                    "POST /api/maintenance/update": [
                        {"type": "reject", "message": "socket hang up", "name": "TypeError"}
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_failure"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_refresh"},
            ],
        },
    )

    after_failure = data["snapshots"]["after_failure"]
    after_refresh = data["snapshots"]["after_refresh"]

    assert after_failure["counts_by_key"]["POST /api/maintenance/update"] == 1
    assert after_failure["tracked_job_id"] is None
    assert after_failure["ownership_state"] == "unconfirmed"
    assert after_failure["counts_by_key"].get("GET /api/maintenance/jobs/" + latest_job_id, 0) == 0
    assert after_refresh["tracked_job_id"] is None
    assert after_refresh["ownership_state"] == "unconfirmed"
    assert after_refresh["job_id_text"] == latest_job_id


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize(
    ("ambiguous_post_spec", "scenario_id"),
    [
        (
            {
                "status": 202,
                "json": {
                    "status": "queued",
                    "message": "Independent updater queued.",
                    "steps": [],
                    "started_at": 1_700_001_000,
                    "finished_at": None,
                },
            },
            "accepted_without_exact_id",
        ),
        (
            {"type": "reject", "message": "socket hang up", "name": "TypeError"},
            "network_response_unknown",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_maintenance_ui_ambiguous_update_invalidates_prior_exact_ownership(
    tmp_path, ambiguous_post_spec, scenario_id
):
    prior_job_id = "a" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                _status_payload(
                    update_available=True,
                    job=_job_payload(
                        prior_job_id,
                        status="succeeded",
                        message="Update completed and the restarted directory responded.",
                        steps=["stop", "reinstall", "restart"],
                        finished_at=1_700_000_900,
                    ),
                ),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                prior_job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        },
                        ambiguous_post_spec,
                    ],
                    f"GET /api/maintenance/jobs/{prior_job_id}": [
                        {
                            "json": _job_payload(
                                prior_job_id,
                                status="succeeded",
                                message="Update completed and the restarted directory responded.",
                                steps=["stop", "reinstall", "restart"],
                                finished_at=1_700_000_900,
                            )
                        }
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "capture", "name": "known_exact"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_ambiguous"},
                {"type": "click", "id": "settings-maintenance-refresh-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "after_refresh"},
            ],
        },
    )

    known_exact = data["snapshots"]["known_exact"]
    after_ambiguous = data["snapshots"]["after_ambiguous"]
    after_refresh = data["snapshots"]["after_refresh"]

    assert known_exact["tracked_job_id"] == prior_job_id, scenario_id
    assert known_exact["ownership_state"] == "exact", scenario_id
    assert known_exact["counts_by_key"][f"GET /api/maintenance/jobs/{prior_job_id}"] == 1, scenario_id

    assert after_ambiguous["counts_by_key"]["POST /api/maintenance/update"] == 2, scenario_id
    assert after_ambiguous["tracked_job_id"] is None, scenario_id
    assert after_ambiguous["ownership_state"] == "unconfirmed", scenario_id
    assert after_ambiguous["job_id_text"] == prior_job_id, scenario_id

    assert after_refresh["counts_by_key"]["POST /api/maintenance/update"] == 2, scenario_id
    assert after_refresh["counts_by_key"]["GET /api/maintenance"] == 2, scenario_id
    assert after_refresh["counts_by_key"].get(f"GET /api/maintenance/jobs/{prior_job_id}", 0) == 1, scenario_id
    assert after_refresh["tracked_job_id"] is None, scenario_id
    assert after_refresh["ownership_state"] == "unconfirmed", scenario_id
    assert after_refresh["job_id_text"] == prior_job_id, scenario_id


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_transient_disconnect_never_reposts_update(tmp_path):
    job_id = "7" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(update_available=True, job=None),
                extra={
                    "POST /api/maintenance/update": [
                        {
                            "status": 202,
                            "json": _job_payload(
                                job_id,
                                status="queued",
                                message="Independent updater queued.",
                            ),
                        }
                    ],
                    f"GET /api/maintenance/jobs/{job_id}": [
                        {
                            "json": _job_payload(
                                job_id,
                                status="running",
                                message="Updating; the directory may disconnect while its service restarts.",
                                steps=["stop"],
                            )
                        },
                        {"type": "hang"},
                        {
                            "json": _job_payload(
                                job_id,
                                status="succeeded",
                                message="Update completed and the restarted directory responded.",
                                steps=["stop", "reinstall", "restart"],
                                finished_at=1_700_000_900,
                            )
                        },
                    ],
                },
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "click", "id": "settings-update-btn"},
                {"type": "flush"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "capture", "name": "running"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "advance", "ms": 5000},
                {"type": "flush"},
                {"type": "capture", "name": "after_disconnect"},
                {"type": "advance", "ms": 3000},
                {"type": "flush"},
                {"type": "capture", "name": "after_reconnect"},
            ],
        },
    )

    running = data["snapshots"]["running"]
    after_disconnect = data["snapshots"]["after_disconnect"]
    after_reconnect = data["snapshots"]["after_reconnect"]

    assert running["status_text"] == "running"
    assert after_disconnect["counts_by_key"]["POST /api/maintenance/update"] == 1
    assert after_disconnect["status_text"] == "unconfirmed"
    assert "reconnect" in after_disconnect["note_text"].lower()
    assert after_disconnect["job_message_text"] != "Update did not complete. Check service-directory logs/doctor on this node."
    assert any(
        call["path"] == f"/api/maintenance/jobs/{job_id}" and call["result"] == "aborted"
        for call in after_disconnect["fetch_calls"]
    )
    assert after_reconnect["counts_by_key"]["POST /api/maintenance/update"] == 1
    assert after_reconnect["status_text"] == "succeeded"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_renders_recorded_steps_only(tmp_path):
    job_id = "8" * 32
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(
                    update_available=False,
                    latest_revision=CURRENT_REVISION,
                    latest_version="1.2.3",
                    job=_job_payload(
                        job_id,
                        status="succeeded",
                        message="Update completed and the restarted directory responded.",
                        steps=["stop", "reinstall", "restart"],
                        finished_at=1_700_000_900,
                    ),
                )
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "loaded"},
            ],
        },
    )

    loaded = data["snapshots"]["loaded"]
    assert loaded["steps"] == ["stop", "reinstall", "restart"]
    assert "queued" not in loaded["steps"]
    assert "running" not in loaded["steps"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_ui_uses_safe_text_for_reason_and_job_message(tmp_path):
    malicious_reason = '<img id="xss-support" src=x onerror="window.__xss__ = true">'
    malicious_message = '<span id="xss-job">not real html</span>'
    data = _run_jsdom_scenario(
        tmp_path,
        {
            "routes": _base_routes(
                _status_payload(
                    update_available=None,
                    update_supported=False,
                    unsupported_reason=malicious_reason,
                    latest_revision=None,
                    latest_version=None,
                    job=_job_payload(
                        "9" * 32,
                        status="failed",
                        message=malicious_message,
                        steps=[],
                        finished_at=1_700_000_900,
                    ),
                )
            ),
            "actions": [
                {"type": "click", "id": "settings-btn"},
                {"type": "flush"},
                {"type": "capture", "name": "loaded"},
            ],
        },
    )

    loaded = data["snapshots"]["loaded"]
    assert loaded["xss_support_present"] is False
    assert loaded["xss_job_present"] is False
    assert loaded["xss_flag"] is False
    assert loaded["support_text"] == malicious_reason
    assert "<img" not in loaded["support_html"]
    assert loaded["job_message_text"] == malicious_message
    assert "<span" not in loaded["job_message_html"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
def test_maintenance_script_parses_under_node_check(tmp_path):
    script = _extract_settings_script(_render_page_html(tmp_path))
    script_path = tmp_path / "maintenance_settings_script.js"
    script_path.write_text(script)

    result = subprocess.run(
        ["node", "--check", str(script_path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr