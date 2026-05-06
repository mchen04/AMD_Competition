"""ROCm Doctor dashboard server.

Serves the static React console under ``web/`` and bridges it to the actual
harness via a small ``/api/*`` JSON layer. All mutating endpoints operate on
an isolated working copy of the supplied template config so the source config
is never touched.

API:
  GET  /api/snapshot          — full bundle (providers, recipes, failures,
                                incidents, state, sample YAML)
  POST /api/check             — run check_config on the working copy
  POST /api/run               — optional inject_failure(scenario), then
                                self_heal_config, then generate_report
  POST /api/reset             — restore working copy from template
  POST /api/active-provider   — switch active_model_provider on the copy
  GET  /api/incident?id=...   — full markdown body of an incident report
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from collections import OrderedDict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from .config import load_config, save_config
from .failure_injection import SCENARIOS, inject_failure
from .healing_policy import FAILURE_TAXONOMY
from .operations import check_config, self_heal_config
from .recipes import RECIPE_REGISTRY
from .reporting import generate_report
from .schemas import to_jsonable

_PACKAGE_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_ROOT.parent
DEFAULT_WEB_ROOT = _REPO_ROOT / "web"
DEFAULT_CONFIG = _REPO_ROOT / "demo" / "rocm-doctor.yaml"

_LOCK = threading.Lock()


# Curated descriptions overlay the registry: the dataclass has no `desc`
# field, but the design surface needs one for the recipe cards.
_RECIPE_DESC: dict[str, str] = {
    "noop": "Make no change. Used when the system is healthy or the failure is unactionable.",
    "retry_without_config_change": "Re-run the health check once. Catches transient rate limits with no edit.",
    "update_endpoint_url": "Restore the active provider base_url from expected_base_url.",
    "increase_health_max_tokens": "Raise validation.health_max_tokens for models that need more headroom.",
    "lower_health_max_tokens": "Drop health_max_tokens to suppress over-answering on weak models.",
    "increase_timeout": "Raise request.timeout_seconds for slow cold starts and large prompts.",
    "increase_retry_backoff": "Bump retry.backoff_seconds for noisy upstreams.",
    "disable_streaming": "Force request.stream=false when SSE framing breaks tool-call parsing.",
    "switch_prompt_template": "Fall back to the next health-chat template under templates.health_chat_fallbacks.",
    "fallback_model_provider": "Switch active_model_provider to self_healing.fallback_model_provider.",
    "restore_last_known_good_config": "Roll the workspace back to the most recent verified config snapshot.",
    "tighten_expected_health_response": "Replace expected_health_response with a stricter sentinel string.",
    "disable_tool_probe_for_weak_model": "Skip tool_call_parser probe for providers that don't support tool calls.",
    "lower_max_model_len": "Reduce model.context.max_tokens to fit within the runtime safe ceiling.",
    "set_tool_parser": "Set model.tool_calling.parser to the expected_parser baked into the YAML.",
    "set_rocm_device_flags": "Restore launch.required_device_flags before the next service restart.",
    "restart_known_service": "Issue a dry-run restart through service.restart_mode.",
}


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


def _recipe_dto(recipe: Any) -> dict[str, Any]:
    risk_map = {"medium": "med"}
    return {
        "id": recipe.id,
        "desc": _RECIPE_DESC.get(recipe.id, ""),
        "classes": list(recipe.supported_failure_classes),
        "risk": risk_map.get(recipe.risk_level, recipe.risk_level),
        "editPath": recipe.config_path_templates[0] if recipe.config_path_templates else None,
        "editFrom": None,
        "editTo": None,
        "verifies": list(recipe.verification_steps) or ["full check sequence"],
    }


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
    """Pull the value off a `- Key: \\`value\\`` style report header line."""
    needles = (f"- {key}:", f"{key}:")
    for line in text.splitlines():
        stripped = line.strip()
        for needle in needles:
            if stripped.startswith(needle):
                value = stripped[len(needle):].strip()
                return value.strip("`").strip('"').strip("'")
    return None


# ── Workspace state ──────────────────────────────────────────────────────

class DashboardState:
    """Owns the working-copy config and the dashboard's isolated state file."""

    DURATION_HISTORY = 50

    def __init__(self, template_config: Path) -> None:
        self.template_config = template_config.resolve()
        self.workspace = self.template_config.parent
        self.working_config = self.workspace / ".rocm-doctor.dashboard.yaml"
        self.state_file = ".rocm-doctor.dashboard-state.json"
        self.reports_subdir = "reports/dashboard"
        # In-memory rolling map of incident_id → duration in ms for runs
        # observed during this dashboard process. Older incidents on disk
        # carry no duration in their report files, so this is the cleanest
        # place to surface "mean recovery" without modifying the report
        # writer in rocm_doctor.reporting.
        self.run_durations: OrderedDict[str, int] = OrderedDict()
        self.reset()

    def record_duration(self, incident_id: str | None, duration_ms: int) -> None:
        if not incident_id:
            return
        self.run_durations[incident_id] = duration_ms
        while len(self.run_durations) > self.DURATION_HISTORY:
            self.run_durations.popitem(last=False)

    def reset(self) -> None:
        shutil.copy2(self.template_config, self.working_config)
        cfg = load_config(self.working_config)
        cfg["state_file"] = self.state_file
        cfg["reports_dir"] = self.reports_subdir
        save_config(self.working_config, cfg)
        # Best-effort: clear stale dashboard state from a previous boot.
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

def _api_snapshot(state: DashboardState, _body: dict, _query: dict) -> dict:
    cfg = load_config(state.working_config)
    active = str(cfg.get("active_model_provider", ""))
    providers_raw = cfg.get("model_providers", {}) or {}
    providers = [_provider_dto(pid, raw, active) for pid, raw in providers_raw.items()]

    recipes = [_recipe_dto(r) for r in RECIPE_REGISTRY.values()]
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
    }


def _api_check(state: DashboardState, _body: dict, _query: dict) -> dict:
    health, evidence = check_config(state.working_config)
    return {"health": to_jsonable(health), "evidence": to_jsonable(evidence)}


def _api_run(state: DashboardState, body: dict, _query: dict) -> dict:
    scenario = body.get("scenario")
    inject_result = None
    if scenario:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        inject_result = inject_failure(state.working_config, scenario)

    t0 = time.perf_counter()
    result = self_heal_config(state.working_config, provider_name="rules")

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
    except Exception:  # noqa: BLE001
        report_path = None
    duration_ms = int((time.perf_counter() - t0) * 1000)
    state.record_duration(incident_id, duration_ms)

    return {
        "scenario": scenario,
        "inject": inject_result,
        "self_heal": to_jsonable(result),
        "diagnosis": state_json.get("diagnosis"),
        "before_evidence": state_json.get("before_evidence"),
        "after_evidence": state_json.get("after_evidence"),
        "report_path": report_path,
        "incident_id": incident_id,
        "duration_ms": duration_ms,
        "incidents": _list_incidents(state.reports_dir, dict(state.run_durations)),
    }


def _api_reset(state: DashboardState, _body: dict, _query: dict) -> dict:
    state.reset()
    return {"reset": True, "config_path": str(state.working_config)}


def _api_active_provider(state: DashboardState, body: dict, _query: dict) -> dict:
    pid = body.get("provider_id")
    if not pid:
        raise ValueError("provider_id required")
    cfg = load_config(state.working_config)
    if pid not in (cfg.get("model_providers") or {}):
        raise ValueError(f"unknown provider: {pid}")
    cfg["active_model_provider"] = pid
    save_config(state.working_config, cfg)
    return {"active_provider": pid}


def _api_incident(state: DashboardState, _body: dict, query: dict) -> dict:
    incident_id = (query.get("id") or [None])[0]
    if not incident_id:
        raise ValueError("id required")
    path = state.reports_dir / f"{incident_id}.md"
    if not path.is_file():
        raise FileNotFoundError(f"no such incident: {incident_id}")
    return {"id": incident_id, "path": str(path), "body": path.read_text(encoding="utf-8")}


ROUTES: dict[tuple[str, str], Callable[[DashboardState, dict, dict], dict]] = {
    ("GET",  "/api/snapshot"):        _api_snapshot,
    ("POST", "/api/check"):           _api_check,
    ("POST", "/api/run"):             _api_run,
    ("POST", "/api/reset"):           _api_reset,
    ("POST", "/api/active-provider"): _api_active_provider,
    ("GET",  "/api/incident"):        _api_incident,
}


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
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
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
        handler = ROUTES.get((method, path))
        if handler is None:
            self._json(404, {"error": f"not found: {method} {path}"})
            return
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": f"invalid JSON body: {exc}"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "request body must be a JSON object"})
            return
        query_params = parse_qs(query)
        try:
            with _LOCK:
                result = handler(self.state, payload, query_params)
        except (ValueError, FileNotFoundError) as exc:
            self._json(400, {"error": str(exc), "type": type(exc).__name__})
            return
        except Exception as exc:  # noqa: BLE001
            self._json(500, {
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(limit=5),
            })
            return
        self._json(200, result)

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
) -> None:
    web = (web_root or DEFAULT_WEB_ROOT).resolve()
    if not (web / "index.html").is_file():
        raise FileNotFoundError(f"web console not found at {web}/index.html")

    template = (config or DEFAULT_CONFIG).resolve()
    if not template.is_file():
        raise FileNotFoundError(f"config template not found: {template}")

    state = DashboardState(template)

    handler_cls = type(
        "BoundDashboardHandler",
        (_DashboardHandler,),
        {"state": state},
    )
    handler = partial(handler_cls, directory=str(web))
    server = ThreadingHTTPServer((host, port), handler)

    actual_host, actual_port = server.server_address[:2]
    display_host = "localhost" if actual_host in {"127.0.0.1", "0.0.0.0", "::", ""} else actual_host
    print(f"ROCm Doctor console")
    print(f"  web root:        {web}")
    print(f"  template config: {template}")
    print(f"  working config:  {state.working_config}")
    print(f"  reports dir:     {state.reports_dir}")
    print(f"  open: http://{display_host}:{actual_port}/")
    print("press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping dashboard server.")
    finally:
        server.server_close()
