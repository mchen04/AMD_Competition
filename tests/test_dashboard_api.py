"""Integration tests for the dashboard /api/* surface.

Spins up a real ThreadingHTTPServer pointed at a temp working copy of the demo
config, then drives it through the snapshot → run → SSE → run-result flow.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pytest

from rocm_doctor.dashboard import DashboardState, _DashboardHandler
from http.server import ThreadingHTTPServer
from functools import partial


@contextmanager
def _running_server(tmp_path: Path) -> Iterator[tuple[str, DashboardState]]:
    template_src = Path("demo/rocm-doctor.yaml").resolve()
    template = tmp_path / "rocm-doctor.yaml"
    shutil.copy2(template_src, template)
    state = DashboardState(template, diagnosis_provider="rules")

    handler_cls = type("BoundHandler", (_DashboardHandler,), {"state": state})
    web_root = tmp_path / "web-empty"
    web_root.mkdir()
    (web_root / "index.html").write_text("<html></html>", encoding="utf-8")
    handler = partial(handler_cls, directory=str(web_root))

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = server.server_address[:2]
    base = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _get(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_snapshot_returns_providers_recipes_failures(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (base, _state):
        snap = _get(f"{base}/api/snapshot")
        assert "providers" in snap and "recipes" in snap and "failures" in snap
        assert any(p["id"] == snap["active_provider"] for p in snap["providers"])
        # Phase 2 contract: recipe DTOs include description from YAML registry.
        assert all("desc" in r for r in snap["recipes"])
        # Phase 4 contract: schema fields live under camelCase too.
        assert all("humanLabel" in r for r in snap["recipes"])


def test_run_returns_run_id_and_completes(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (base, state):
        status, body = _post(f"{base}/api/run", {"scenario": "wrong_endpoint_port"})
        assert status == 202, body
        run_id = body["run_id"]
        assert run_id

        # Poll for completion (background thread).
        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.05)
            record = state.runs.get(run_id)
            if record and record.done:
                break
        else:
            pytest.fail("run did not complete in 10s")

        result = _get(f"{base}/api/run/{run_id}")
        assert result["state"] == "done"
        assert result["scenario"] == "wrong_endpoint_port"
        assert "self_heal" in result
        # Heal pipeline ran end-to-end: at least one repair was attempted and
        # the diagnosis identified the injected failure class.
        sh = result["self_heal"]
        assert isinstance(sh.get("repairs"), list) and sh["repairs"]
        assert result.get("diagnosis", {}).get("failure_class") == "wrong_endpoint_port"


def test_unknown_scenario_returns_400(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (base, _state):
        status, body = _post(f"{base}/api/run", {"scenario": "definitely_not_a_scenario"})
        assert status == 400
        assert "unknown scenario" in body["error"]


def test_run_events_stream_yields_done(tmp_path: Path) -> None:
    with _running_server(tmp_path) as (base, _state):
        _, body = _post(f"{base}/api/run", {"scenario": "wrong_endpoint_port"})
        run_id = body["run_id"]
        with urllib.request.urlopen(f"{base}/api/run/{run_id}/events", timeout=10) as resp:
            saw_done = False
            deadline = time.time() + 10
            while time.time() < deadline:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8").strip()
                if text.startswith("event: done"):
                    saw_done = True
                    break
            assert saw_done, "SSE stream never delivered a `done` event"
