"""ROCm Doctor dashboard server.

Serves the static frontend (web/dist when built, falls back to web/) and bridges
it to the harness via a small ``/api/*`` JSON layer with SSE for live runs. All
mutating endpoints operate on an isolated working copy of the supplied template
config so the source config is never touched.

API:
  GET  /api/snapshot                — full bundle (providers, recipes, failures,
                                       incidents, state, sample YAML)
  POST /api/check                   — run check_config on the working copy
  POST /api/run                     — start a heal job → 202 {run_id}
  GET  /api/run/{run_id}/events     — SSE stream of run events
  GET  /api/run/{run_id}            — final result snapshot (idempotent)
  POST /api/reset                   — restore working copy from template
  POST /api/active-provider         — switch active_model_provider on the copy
  GET  /api/incident/{id}           — full markdown body of an incident report
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
import uuid
from collections import OrderedDict, deque
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .api.schemas import validate_request
from .config import load_config, save_config
from .failure_injection import SCENARIOS, inject_failure
from .healing_policy import FAILURE_TAXONOMY
from .logging import get_logger
from .operations import check_config, self_heal_config
from .recipes import RECIPE_REGISTRY
from .reporting import generate_report
from .schemas import to_jsonable
from .timeutil import utc_now

_log = get_logger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_WEB_DIST = _REPO_ROOT / "web" / "dist"
_WEB_LEGACY = _REPO_ROOT / "web"
DEFAULT_WEB_ROOT = _WEB_DIST if (_WEB_DIST / "index.html").exists() else _WEB_LEGACY
DEFAULT_CONFIG = _REPO_ROOT / "demo" / "rocm-doctor.yaml"

_LOCK = threading.Lock()


# ── DTO builders ─────────────────────────────────────────────────────────

def _provider_dto(pid: str, raw: dict[str, Any], active_id: str) -> dict[str, Any]:
    model = raw.get("model", {}) or {}
    endpoint = model.get("endpoint", {}) or {}
    context = model.get("context", {}) or {}
    tool = model.get("tool_calling", {}) or {}
    request = raw.get("request", {}) or {}
    capabilities = raw.get("capabilities", {}) or {}
    probes = (raw.get("health", {}) or {}).get("probes", []) or []
    safe_recipes = (raw.get("repair", {}) or {}).get("safe_recipes", []) or []
    return {
        "id": pid,
        "label": pid,
        "runtime": str(raw.get("runtime_type") or raw.get("adapter") or "unknown"),
        "adapter": str(raw.get("adapter") or "openai-compatible"),
        "model": str(model.get("id") or pid),
        "baseUrl": str(endpoint.get("base_url") or ""),
        "contextMax": int(context.get("max_tokens") or 0),
        "safeContextMax": int(context.get("safe_max_tokens") or 0),
        "timeout": float(request.get("timeout_seconds") or 0),
        "accelerator": str(raw.get("accelerator") or "none"),
        "backend": str(raw.get("backend") or "local"),
        "rocm": bool(raw.get("rocm_required") or "rocm" in str(raw.get("accelerator") or "").lower()),
        "toolCalls": bool(tool.get("enabled")),
        "toolParser": tool.get("parser"),
        "capabilities": [k for k, v in capabilities.items() if v],
        "probes": list(probes),
        "safeRecipes": list(safe_recipes),
        "active": pid == active_id,
        "status": "healthy" if pid == active_id else "idle",
        "health": 100 if pid == active_id else 0,
        "lastChecked": "—",
        "note": "",
    }


def _recipe_dto(recipe: Any, config: dict[str, Any] | None = None) -> dict[str, Any]:
    risk_map = {"medium": "med"}
    edit_path: str | None = None
    edit_from: Any = None
    edit_to: Any = None
    if recipe.config_path_templates:
        edit_path = recipe.config_path_templates[0]
        if config is not None:
            try:
                changes = recipe.build_changes(config) or {}
            except (KeyError, TypeError, ValueError):
                changes = {}
            resolved = recipe.config_paths(config)
            primary = resolved[0] if resolved else edit_path
            if primary in changes:
                edit_to = changes[primary]
                try:
                    edit_from = _get_dotted(config, primary)
                except KeyError:
                    edit_from = None
    return {
        "id": recipe.id,
        "desc": recipe.description,
        "humanLabel": recipe.human_label,
        "tags": list(recipe.tags),
        "classes": list(recipe.supported_failure_classes),
        "risk": risk_map.get(recipe.risk_level, recipe.risk_level),
        "editPath": edit_path,
        "editFrom": _coerce_preview(edit_from),
        "editTo": _coerce_preview(edit_to),
        "verifies": list(recipe.verification_steps) or ["full check sequence"],
    }


def _coerce_preview(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, sort_keys=True)


def _get_dotted(data: dict[str, Any], dotted_key: str) -> Any:
    cursor: Any = data
    for part in dotted_key.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            raise KeyError(dotted_key)
        cursor = cursor[part]
    return cursor


def _failure_dto(entry: Any) -> dict[str, Any]:
    fc = entry.failure_class
    return {
        "id": fc,
        "label": fc.replace("_", " "),
        "description": entry.description,
        "candidates": list(entry.candidate_recipe_ids),
        "expectedRecipe": entry.candidate_recipe_ids[0] if entry.candidate_recipe_ids else None,
        "scenario": fc if fc in SCENARIOS else None,
    }


def _scenario_to_failure_dto(scenario: str) -> dict[str, Any]:
    return {
        "id": scenario,
        "label": scenario.replace("_", " "),
        "description": f"injectable scenario: {scenario}",
        "candidates": [],
        "expectedRecipe": None,
        "scenario": scenario,
    }


def _list_incidents(reports_dir: Path, durations: dict[str, int] | None = None) -> list[dict[str, Any]]:
    if not reports_dir.is_dir():
        return []
    durations = durations or {}
    out = []
    for path in sorted(reports_dir.glob("*.md"), reverse=True):
        try:
            head = path.read_text(encoding="utf-8")[:4096]
        except OSError:
            continue
        verification_healthy = (_scrape(head, "Verification healthy") or "").lower() == "true"
        rolled_back = (_scrape(head, "Repair rolled back") or _scrape(head, "Rolled back") or "").lower() == "true"
        record: dict[str, Any] = {
            "id": path.stem,
            "ts": _scrape(head, "Created") or _scrape(head, "Incident ID") or "",
            "provider": _scrape(head, "Model provider") or _scrape(head, "model_provider") or "",
            "failure": _scrape(head, "Failure class") or _scrape(head, "failure_class") or "",
            "recipe": _scrape(head, "Repair recipe") or _scrape(head, "recipe_id") or "",
            "outcome": "rolled-back" if rolled_back else ("healed" if verification_healthy else "degraded"),
            "path": str(path),
            "size": path.stat().st_size,
        }
        if path.stem in durations:
            record["durationMs"] = durations[path.stem]
        out.append(record)
    return out


def _scrape(text: str, key: str) -> str | None:
    needles = (f"- {key}:", f"{key}:")
    for line in text.splitlines():
        stripped = line.strip()
        for needle in needles:
            if stripped.startswith(needle):
                value = stripped[len(needle):].strip()
                return value.strip("`").strip('"').strip("'")
    return None


# ── Run records (SSE-friendly background jobs) ───────────────────────────


class _RunRecord:
    """Per-run buffer of SSE events + final result for late subscribers."""

    BUFFER_LIMIT = 256

    def __init__(self, run_id: str, scenario: str | None, provider_name: str) -> None:
        self.run_id = run_id
        self.scenario = scenario
        self.diagnosis_provider = provider_name
        self.events: deque[dict[str, Any]] = deque(maxlen=self.BUFFER_LIMIT)
        self.condition = threading.Condition()
        self.done = False
        self.error: str | None = None
        self.result: dict[str, Any] | None = None
        self.started_at = time.time()
        self._seq = 0

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        with self.condition:
            self._seq += 1
            self.events.append({
                "event": event,
                "run_id": self.run_id,
                "seq": self._seq,
                "ts": utc_now(),
                "data": data or {},
            })
            self.condition.notify_all()

    def finish(self, result: dict[str, Any] | None, error: str | None = None) -> None:
        with self.condition:
            self.result = result
            self.error = error
            self.done = True
            self.condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": "done" if self.done else "running",
            "scenario": self.scenario,
            "diagnosis_provider": self.diagnosis_provider,
            "error": self.error,
            **(self.result or {}),
        }


# ── Workspace state ──────────────────────────────────────────────────────

class DashboardState:
    """Owns the working-copy config, run buffers, and the dashboard's state file."""

    DURATION_HISTORY = 50
    RUN_HISTORY = 32

    def __init__(self, template_config: Path, diagnosis_provider: str = "rules") -> None:
        self.template_config = template_config.resolve()
        self.workspace = self.template_config.parent
        self.working_config = self.workspace / ".rocm-doctor.dashboard.yaml"
        self.state_file = ".rocm-doctor.dashboard-state.json"
        self.reports_subdir = "reports/dashboard"
        self.diagnosis_provider = diagnosis_provider
        self.run_durations: OrderedDict[str, int] = OrderedDict()
        self.runs: OrderedDict[str, _RunRecord] = OrderedDict()
        self.reset()

    def record_duration(self, incident_id: str | None, duration_ms: int) -> None:
        if not incident_id:
            return
        self.run_durations[incident_id] = duration_ms
        while len(self.run_durations) > self.DURATION_HISTORY:
            self.run_durations.popitem(last=False)

    def register_run(self, run: _RunRecord) -> None:
        self.runs[run.run_id] = run
        while len(self.runs) > self.RUN_HISTORY:
            self.runs.popitem(last=False)

    def reset(self) -> None:
        shutil.copy2(self.template_config, self.working_config)
        cfg = load_config(self.working_config)
        cfg["state_file"] = self.state_file
        cfg["reports_dir"] = self.reports_subdir
        save_config(self.working_config, cfg)
        for stale in (self.workspace / self.state_file,):
            if stale.is_file():
                try:
                    stale.unlink()
                except OSError:
                    pass

    @property
    def reports_dir(self) -> Path:
        return self.workspace / self.reports_subdir

    @property
    def state_path(self) -> Path:
        return self.workspace / self.state_file


# ── API handlers ─────────────────────────────────────────────────────────

def _api_snapshot(state: DashboardState, _body: dict, _query: dict, _route: dict) -> dict:
    cfg = load_config(state.working_config)
    active = str(cfg.get("active_model_provider", ""))
    providers_raw = cfg.get("model_providers", {}) or {}
    providers = [_provider_dto(pid, raw, active) for pid, raw in providers_raw.items()]

    recipes = [_recipe_dto(r, cfg) for r in RECIPE_REGISTRY.values()]
    failures = [_failure_dto(f) for f in FAILURE_TAXONOMY.values()]
    known_failure_ids = {f["id"] for f in failures}
    for scenario in sorted(SCENARIOS):
        if scenario not in known_failure_ids:
            failures.append(_scenario_to_failure_dto(scenario))

    state_json: dict[str, Any] = {}
    if state.state_path.is_file():
        try:
            state_json = json.loads(state.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state_json = {}

    yaml_text = state.working_config.read_text(encoding="utf-8")

    diagnosis_cfg = cfg.get("diagnosis") or {}
    diagnosis_providers_raw = diagnosis_cfg.get("providers") or {}
    diagnosis_providers = sorted(diagnosis_providers_raw.keys())

    return {
        "config_path": str(state.working_config),
        "template_path": str(state.template_config),
        "workspace": str(state.workspace),
        "active_provider": active,
        "providers": providers,
        "recipes": recipes,
        "failures": failures,
        "scenarios": sorted(SCENARIOS),
        "incidents": _list_incidents(state.reports_dir, dict(state.run_durations)),
        "state_json": state_json,
        "config_yaml": yaml_text,
        "diagnosis_providers": diagnosis_providers,
        "diagnosis_provider": state.diagnosis_provider,
    }


def _api_check(state: DashboardState, _body: dict, _query: dict, _route: dict) -> dict:
    health, evidence = check_config(state.working_config)
    return {"health": to_jsonable(health), "evidence": to_jsonable(evidence)}


def _api_run(state: DashboardState, body: dict, _query: dict, _route: dict) -> dict:
    scenario = body.get("scenario")
    if scenario and scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")

    requested_provider = body.get("provider_name")
    if requested_provider is not None and not isinstance(requested_provider, str):
        raise ValueError("provider_name must be a string")
    provider_name = (requested_provider or state.diagnosis_provider or "rules").strip() or "rules"
    cfg_for_check = load_config(state.working_config)
    available = (cfg_for_check.get("diagnosis", {}) or {}).get("providers", {}) or {}
    if provider_name not in available:
        raise ValueError(f"unknown diagnosis provider: {provider_name}")

    run_id = uuid.uuid4().hex[:12]
    record = _RunRecord(run_id, scenario, provider_name)
    state.register_run(record)

    thread = threading.Thread(
        target=_execute_run,
        args=(state, record, scenario, provider_name),
        name=f"rocm-doctor-run-{run_id}",
        daemon=True,
    )
    thread.start()

    return {
        "run_id": run_id,
        "scenario": scenario,
        "diagnosis_provider": provider_name,
    }


def _execute_run(state: DashboardState, record: _RunRecord, scenario: str | None, provider_name: str) -> None:
    record.emit("run.queued", {"scenario": scenario, "provider": provider_name})
    inject_result: dict[str, Any] | None = None
    try:
        if scenario:
            inject_result = inject_failure(state.working_config, scenario)
            record.emit("inject.applied", {"scenario": scenario, "inject": inject_result})

        record.emit("check.started", {})
        record.emit("diagnosis.started", {"provider": provider_name})

        t0 = time.perf_counter()
        with _LOCK:
            result = self_heal_config(state.working_config, provider_name=provider_name)

        repairs = getattr(result, "repairs", []) or []
        for repair in repairs:
            repair_dto = to_jsonable(repair)
            event = "repair.applied" if not repair_dto.get("rejected") else "repair.rejected"
            record.emit(event, {"repair": repair_dto})

        record.emit("verification.completed", {
            "healthy": getattr(result, "healthy", False),
            "recovered": getattr(result, "recovered", False),
        })

        state_json: dict[str, Any] = {}
        if state.state_path.is_file():
            try:
                state_json = json.loads(state.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state_json = {}

        report_path = None
        incident_id = None
        try:
            _, rp = generate_report(state.working_config)
            report_path = str(rp)
            incident_id = Path(report_path).stem
            record.emit("report.written", {"path": report_path, "incident_id": incident_id})
        except Exception:  # noqa: BLE001
            report_path = None

        duration_ms = int((time.perf_counter() - t0) * 1000)
        state.record_duration(incident_id, duration_ms)

        record.finish({
            "scenario": scenario,
            "inject": inject_result,
            "self_heal": to_jsonable(result),
            "diagnosis": state_json.get("diagnosis"),
            "before_evidence": state_json.get("before_evidence"),
            "after_evidence": state_json.get("after_evidence"),
            "report_path": report_path,
            "incident_id": incident_id,
            "duration_ms": duration_ms,
            "diagnosis_provider": provider_name,
            "incidents": _list_incidents(state.reports_dir, dict(state.run_durations)),
        })
        record.emit("done", {"healthy": getattr(result, "healthy", False)})
    except Exception as exc:  # noqa: BLE001
        record.emit("error", {"error": str(exc), "type": type(exc).__name__})
        record.finish(None, error=str(exc))


def _api_run_result(state: DashboardState, _body: dict, _query: dict, route_args: dict) -> dict:
    run_id = route_args.get("run_id", "")
    record = state.runs.get(run_id)
    if record is None:
        raise FileNotFoundError(f"unknown run: {run_id}")
    return record.snapshot()


def _api_reset(state: DashboardState, _body: dict, _query: dict, _route: dict) -> dict:
    state.reset()
    return {"reset": True, "config_path": str(state.working_config)}


def _api_active_provider(state: DashboardState, body: dict, _query: dict, _route: dict) -> dict:
    pid = body.get("provider_id")
    if not pid:
        raise ValueError("provider_id required")
    cfg = load_config(state.working_config)
    if pid not in (cfg.get("model_providers") or {}):
        raise ValueError(f"unknown provider: {pid}")
    cfg["active_model_provider"] = pid
    save_config(state.working_config, cfg)
    return {"active_provider": pid}


def _api_incident(state: DashboardState, _body: dict, _query: dict, route_args: dict) -> dict:
    incident_id = route_args.get("id", "")
    if not incident_id:
        raise ValueError("id required")
    path = state.reports_dir / f"{incident_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no such incident: {incident_id}")
    return {"id": incident_id, "path": str(path), "body": path.read_text(encoding="utf-8")}


HandlerFn = Callable[[DashboardState, dict, dict, dict], dict]

# Each entry: (method, path_template, handler, request_endpoint_for_validation)
ROUTES: list[tuple[str, str, HandlerFn, str | None]] = [
    ("GET", "/api/snapshot", _api_snapshot, None),
    ("POST", "/api/check", _api_check, "POST /api/check"),
    ("POST", "/api/run", _api_run, "POST /api/run"),
    ("GET", "/api/run/{run_id}", _api_run_result, None),
    ("POST", "/api/reset", _api_reset, "POST /api/reset"),
    ("POST", "/api/active-provider", _api_active_provider, "POST /api/active-provider"),
    ("GET", "/api/incident/{id}", _api_incident, None),
]


def _match_route(method: str, path: str) -> tuple[HandlerFn, dict[str, str], str | None] | None:
    for route_method, template, handler, validation_key in ROUTES:
        if route_method != method:
            continue
        args = _match_template(template, path)
        if args is not None:
            return handler, args, validation_key
    return None


def _match_template(template: str, path: str) -> dict[str, str] | None:
    template_parts = template.strip("/").split("/")
    path_parts = path.strip("/").split("/")
    if len(template_parts) != len(path_parts):
        return None
    args: dict[str, str] = {}
    for tpl, val in zip(template_parts, path_parts):
        if tpl.startswith("{") and tpl.endswith("}"):
            args[tpl[1:-1]] = val
        elif tpl != val:
            return None
    return args


# ── HTTP handler ─────────────────────────────────────────────────────────

class _DashboardHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".jsx": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    state: DashboardState  # injected via subclass

    def end_headers(self) -> None:
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/run/") and parsed.path.endswith("/events"):
            run_id = parsed.path[len("/api/run/"): -len("/events")]
            return self._stream_events(run_id)
        if parsed.path.startswith("/api/"):
            return self._handle_api(parsed.path, parsed.query, "GET", b"")
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if parsed.path.startswith("/api/"):
            return self._handle_api(parsed.path, parsed.query, "POST", body)
        self.send_error(405, "method not allowed")

    def _handle_api(self, path: str, query: str, method: str, body: bytes) -> None:
        match = _match_route(method, path)
        if match is None:
            self._json(404, {"error": f"not found: {method} {path}"})
            return
        handler, route_args, validation_key = match
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": f"invalid JSON body: {exc}"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "request body must be a JSON object"})
            return
        if validation_key:
            try:
                validate_request(validation_key, payload)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
        query_params = parse_qs(query)
        try:
            # /api/run starts a background thread itself; everything else is
            # short-lived enough that a single global lock is fine.
            if method == "POST" and path == "/api/run":
                result = handler(self.state, payload, query_params, route_args)
                status = 202
            else:
                with _LOCK:
                    result = handler(self.state, payload, query_params, route_args)
                status = 200
        except (ValueError, FileNotFoundError) as exc:
            code = 404 if isinstance(exc, FileNotFoundError) else 400
            self._json(code, {"error": str(exc), "type": type(exc).__name__})
            return
        except Exception as exc:  # noqa: BLE001
            self._json(500, {
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(limit=5),
            })
            return
        self._json(status, result)

    def _stream_events(self, run_id: str) -> None:
        record = self.state.runs.get(run_id)
        if record is None:
            self._json(404, {"error": f"unknown run: {run_id}"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self._drain_to_client(record)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _drain_to_client(self, record: _RunRecord) -> None:
        sent = 0
        while True:
            with record.condition:
                while sent < len(record.events) or not record.done:
                    if sent < len(record.events):
                        break
                    record.condition.wait(timeout=10.0)
                    if not record.done and sent >= len(record.events):
                        # heartbeat
                        try:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                pending = list(record.events)[sent:]
                sent = len(record.events)
                done = record.done

            for event in pending:
                payload = json.dumps(event, default=str)
                line = f"event: {event['event']}\ndata: {payload}\n\n".encode("utf-8")
                self.wfile.write(line)
                self.wfile.flush()

            if done:
                return

    def _json(self, code: int, data: object) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_forever(
    host: str = "127.0.0.1",
    port: int = 8765,
    web_root: Path | None = None,
    config: Path | None = None,
    diagnosis_provider: str = "rules",
) -> None:
    web = (web_root or DEFAULT_WEB_ROOT).resolve()
    if not (web / "index.html").is_file():
        raise FileNotFoundError(f"web console not found at {web}/index.html")

    template = (config or DEFAULT_CONFIG).resolve()
    if not template.is_file():
        raise FileNotFoundError(f"config template not found: {template}")

    state = DashboardState(template, diagnosis_provider=diagnosis_provider)

    handler_cls = type(
        "BoundDashboardHandler",
        (_DashboardHandler,),
        {"state": state},
    )
    handler = partial(handler_cls, directory=str(web))
    server = ThreadingHTTPServer((host, port), handler)

    actual_host, actual_port = server.server_address[:2]
    display_host = "localhost" if actual_host in {"127.0.0.1", "0.0.0.0", "::", ""} else actual_host
    _log.info("ROCm Doctor console")
    _log.info("  web root:        %s", web)
    _log.info("  template config: %s", template)
    _log.info("  working config:  %s", state.working_config)
    _log.info("  reports dir:     %s", state.reports_dir)
    _log.info("  open: http://%s:%s/", display_host, actual_port)
    _log.info("press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log.info("stopping dashboard server.")
    finally:
        server.server_close()
