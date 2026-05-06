"""TypedDict shapes for /api/* requests, responses, and SSE events.

The shapes are deliberately permissive (Any for nested dataclass-as-dict
payloads coming from the harness) so we don't double-validate things
schemas.py already validates. The point is: every endpoint listed here
appears in the generated JSON Schema, and the frontend codegen reads
from that file rather than re-typing endpoint shapes by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict


# ── Request bodies ────────────────────────────────────────────────────


class CheckRequest(TypedDict, total=False):
    pass


class RunRequest(TypedDict, total=False):
    scenario: str | None
    provider_name: str | None


class ResetRequest(TypedDict, total=False):
    pass


class ActiveProviderRequest(TypedDict, total=False):
    provider_id: str


class ConfigSelectRequest(TypedDict, total=False):
    id: str
    path: str
    source: str


class ConfigImportRequest(TypedDict, total=False):
    name: str
    yaml: str
    overwrite: bool
    select: bool


# ── Response bodies ───────────────────────────────────────────────────


class ProviderDTO(TypedDict, total=False):
    id: str
    label: str
    runtime: str
    adapter: str
    model: str
    baseUrl: str
    contextMax: int
    safeContextMax: int
    timeout: float
    accelerator: str
    backend: str
    rocm: bool
    toolCalls: bool
    toolParser: str | None
    capabilities: list[str]
    probes: list[str]
    safeRecipes: list[str]
    active: bool
    status: str
    health: int
    lastChecked: str
    note: str


class RecipeDTO(TypedDict, total=False):
    id: str
    desc: str
    humanLabel: str
    tags: list[str]
    classes: list[str]
    risk: str
    editPath: str | None
    editFrom: Any
    editTo: Any
    verifies: list[str]


class FailureDTO(TypedDict, total=False):
    id: str
    label: str
    description: str
    candidates: list[str]
    expectedRecipe: str | None
    scenario: str | None


class IncidentDTO(TypedDict, total=False):
    id: str
    ts: str
    provider: str
    failure: str
    recipe: str
    outcome: str
    path: str
    size: int
    durationMs: int


class SnapshotResponse(TypedDict):
    config_path: str
    template_path: str
    workspace: str
    active_provider: str
    providers: list[ProviderDTO]
    recipes: list[RecipeDTO]
    failures: list[FailureDTO]
    scenarios: list[str]
    incidents: list[IncidentDTO]
    state_json: dict[str, Any]
    config_yaml: str
    diagnosis_providers: list[str]
    diagnosis_provider: str


class CheckResponse(TypedDict):
    health: dict[str, Any]
    evidence: dict[str, Any]


class RunStartedResponse(TypedDict):
    run_id: str
    scenario: str | None
    diagnosis_provider: str


class RunResultResponse(TypedDict, total=False):
    run_id: str
    state: str
    scenario: str | None
    inject: dict[str, Any] | None
    self_heal: dict[str, Any] | None
    diagnosis: dict[str, Any] | None
    before_evidence: dict[str, Any] | None
    after_evidence: dict[str, Any] | None
    report_path: str | None
    incident_id: str | None
    duration_ms: int
    diagnosis_provider: str
    incidents: list[IncidentDTO]
    error: str | None


class ResetResponse(TypedDict):
    reset: bool
    config_path: str


class ActiveProviderResponse(TypedDict):
    active_provider: str


class ConfigChoiceDTO(TypedDict, total=False):
    id: str
    label: str
    path: str
    source: str
    current: bool
    valid: bool
    error: str | None
    providers: int
    provider_ids: list[str]
    active: str
    diagnosis_active: str


class ConfigsListResponse(TypedDict):
    bundled: list[ConfigChoiceDTO]
    user: list[ConfigChoiceDTO]
    current_path: str
    user_dir: str


class ConfigSelectResponse(TypedDict):
    selected: str
    path: str
    diagnosis_provider: str


class ConfigImportResponse(TypedDict):
    imported: str
    name: str
    path: str
    selected: bool


class IncidentResponse(TypedDict):
    id: str
    path: str
    body: str


class SSEEvent(TypedDict, total=False):
    event: str
    run_id: str
    seq: int
    ts: str
    data: dict[str, Any]


# ── Endpoint table ────────────────────────────────────────────────────

API_REQUEST_SCHEMAS: dict[str, type[TypedDict]] = {  # type: ignore[type-arg]
    "POST /api/check": CheckRequest,
    "POST /api/run": RunRequest,
    "POST /api/reset": ResetRequest,
    "POST /api/active-provider": ActiveProviderRequest,
    "POST /api/configs/select": ConfigSelectRequest,
    "POST /api/configs/import": ConfigImportRequest,
}


API_RESPONSE_SCHEMAS: dict[str, type[TypedDict]] = {  # type: ignore[type-arg]
    "GET /api/snapshot": SnapshotResponse,
    "POST /api/check": CheckResponse,
    "POST /api/run": RunStartedResponse,
    "GET /api/run/{run_id}": RunResultResponse,
    "POST /api/reset": ResetResponse,
    "POST /api/active-provider": ActiveProviderResponse,
    "GET /api/configs": ConfigsListResponse,
    "POST /api/configs/select": ConfigSelectResponse,
    "POST /api/configs/import": ConfigImportResponse,
    "GET /api/incident/{id}": IncidentResponse,
}


SSE_EVENTS: list[str] = [
    "run.queued",
    "check.started",
    "check.failed",
    "inject.applied",
    "diagnosis.started",
    "diagnosis.completed",
    "repair.applied",
    "repair.rejected",
    "verification.completed",
    "report.written",
    "done",
    "error",
]


# ── JSON Schema codegen (TypedDict → JSON Schema) ─────────────────────


_PRIMITIVE_TYPES = {
    str: {"type": "string"},
    int: {"type": "integer"},
    float: {"type": "number"},
    bool: {"type": "boolean"},
}


def _typeddict_to_json_schema(td: type) -> dict[str, Any]:
    hints = getattr(td, "__annotations__", {}) or {}
    required = list(getattr(td, "__required_keys__", set()))
    properties: dict[str, Any] = {}
    for key, hint in hints.items():
        properties[key] = _hint_to_schema(hint)
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": properties,
        "required": required,
    }


def _hint_to_schema(hint: Any) -> dict[str, Any]:
    origin = getattr(hint, "__origin__", None)
    args = getattr(hint, "__args__", ())

    if hint in _PRIMITIVE_TYPES:
        return dict(_PRIMITIVE_TYPES[hint])

    if origin is list:
        return {"type": "array", "items": _hint_to_schema(args[0]) if args else {}}
    if origin is dict:
        return {"type": "object", "additionalProperties": True}

    # Unions (e.g. str | None, dict[str, Any] | None)
    union_args = []
    if origin is type(None):
        return {"type": "null"}
    try:
        from types import UnionType  # py3.10+
        if isinstance(hint, UnionType):
            union_args = list(hint.__args__)
    except ImportError:
        pass
    if not union_args and origin is not None:
        # Generic Union from typing module
        try:
            from typing import Union, get_origin

            if get_origin(hint) is Union:
                union_args = list(args)
        except ImportError:
            pass

    if union_args:
        non_none = [a for a in union_args if a is not type(None)]
        nullable = any(a is type(None) for a in union_args)
        if len(non_none) == 1:
            schema = _hint_to_schema(non_none[0])
            if nullable:
                # Permit null alongside the inner type without bloating output
                inner_type = schema.get("type")
                if isinstance(inner_type, str):
                    schema["type"] = [inner_type, "null"]
            return schema
        return {"anyOf": [_hint_to_schema(a) for a in non_none]}

    if hint is Any:
        return {}
    if isinstance(hint, type) and issubclass(hint, dict):
        return _typeddict_to_json_schema(hint)
    return {}


def build_schema_document() -> dict[str, Any]:
    request_defs = {
        endpoint: _typeddict_to_json_schema(td)
        for endpoint, td in API_REQUEST_SCHEMAS.items()
    }
    response_defs = {
        endpoint: _typeddict_to_json_schema(td)
        for endpoint, td in API_RESPONSE_SCHEMAS.items()
    }
    typeddef_table = {}
    for td in {*API_REQUEST_SCHEMAS.values(), *API_RESPONSE_SCHEMAS.values()}:
        typeddef_table[td.__name__] = _typeddict_to_json_schema(td)
    # Also include the inner DTOs for codegen.
    for td in (ProviderDTO, RecipeDTO, FailureDTO, IncidentDTO, ConfigChoiceDTO, SSEEvent):
        typeddef_table[td.__name__] = _typeddict_to_json_schema(td)
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "ROCm Doctor API",
        "version": "1",
        "endpoints": {
            "request": request_defs,
            "response": response_defs,
        },
        "definitions": typeddef_table,
        "sse_events": SSE_EVENTS,
    }


def write_schema_json(target: str | Path | None = None) -> Path:
    target = Path(target) if target else Path(__file__).resolve().parent / "schema.json"
    document = build_schema_document()
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def validate_request(endpoint: str, body: dict[str, Any] | None) -> None:
    """Light-weight body validation: only checks that required keys exist."""
    schema_cls = API_REQUEST_SCHEMAS.get(endpoint)
    if schema_cls is None:
        return
    body = body or {}
    if not isinstance(body, dict):
        raise ValueError("request body must be a JSON object")
    required = list(getattr(schema_cls, "__required_keys__", set()))
    missing = [key for key in required if key not in body]
    if missing:
        raise ValueError(f"missing required keys: {', '.join(missing)}")
