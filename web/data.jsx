/* Static-ish data shaped after the actual ROCm Doctor YAML configs and recipes. */

const PROVIDERS = [
  {
    id: "fake-openai",
    label: "fake-openai",
    runtime: "fake",
    adapter: "openai-compatible",
    model: "fake-qwen3",
    baseUrl: "http://127.0.0.1:8000/v1",
    contextMax: 2048,
    safeContextMax: 4096,
    timeout: 1.5,
    accelerator: "none",
    backend: "local",
    rocm: false,
    toolCalls: true,
    toolParser: "qwen3",
    capabilities: ["models", "chat_completions", "tool_calls", "context_length", "rocm_device_flags", "restart"],
    probes: ["endpoint_models", "chat_completion", "context_length", "rocm_device_flags", "tool_call_parser"],
    status: "healthy",
    health: 100,
    lastChecked: "12s ago",
    note: "Deterministic fake endpoint — used for local proof loop.",
    safeRecipes: ["noop","retry_without_config_change","update_endpoint_url","increase_health_max_tokens","lower_health_max_tokens","increase_timeout","increase_retry_backoff","disable_streaming","switch_prompt_template","fallback_model_provider","restore_last_known_good_config","tighten_expected_health_response","disable_tool_probe_for_weak_model","lower_max_model_len","set_tool_parser","set_rocm_device_flags","restart_known_service"],
  },
  {
    id: "ollama-qwen3-0-6b",
    label: "ollama-qwen3-0-6b",
    runtime: "ollama",
    adapter: "openai-compatible",
    model: "qwen3:0.6b",
    baseUrl: "http://127.0.0.1:11434/v1",
    contextMax: 1024,
    safeContextMax: 2048,
    timeout: 30.0,
    accelerator: "cpu-or-available-gpu",
    backend: "local",
    rocm: false,
    toolCalls: false,
    toolParser: null,
    capabilities: ["models", "chat_completions", "context_length"],
    probes: ["endpoint_models", "chat_completion", "context_length"],
    status: "healthy",
    health: 98,
    lastChecked: "47s ago",
    note: "Primary local model proof path.",
    safeRecipes: ["noop","retry_without_config_change","update_endpoint_url","increase_health_max_tokens","lower_health_max_tokens","increase_timeout","increase_retry_backoff","disable_streaming","switch_prompt_template","fallback_model_provider","restore_last_known_good_config","tighten_expected_health_response","lower_max_model_len"],
  },
  {
    id: "ollama-smollm2-135m",
    label: "ollama-smollm2-135m",
    runtime: "ollama",
    adapter: "openai-compatible",
    model: "smollm2:135m",
    baseUrl: "http://127.0.0.1:11434/v1",
    contextMax: 512,
    safeContextMax: 1024,
    timeout: 30.0,
    accelerator: "cpu-or-available-gpu",
    backend: "local",
    rocm: false,
    toolCalls: false,
    toolParser: null,
    capabilities: ["models", "chat_completions", "context_length"],
    probes: ["endpoint_models", "chat_completion", "context_length"],
    status: "degraded",
    health: 62,
    lastChecked: "1m ago",
    note: "Negative control — over-answers strict sentinel.",
    safeRecipes: ["noop","retry_without_config_change","update_endpoint_url","increase_health_max_tokens","lower_health_max_tokens","increase_timeout","increase_retry_backoff","disable_streaming","switch_prompt_template","fallback_model_provider","restore_last_known_good_config","tighten_expected_health_response","lower_max_model_len"],
  },
  {
    id: "ollama-tinyllama-1-1b",
    label: "ollama-tinyllama-1-1b",
    runtime: "ollama",
    adapter: "openai-compatible",
    model: "tinyllama:1.1b",
    baseUrl: "http://127.0.0.1:11434/v1",
    contextMax: 768,
    safeContextMax: 1536,
    timeout: 30.0,
    accelerator: "cpu-or-available-gpu",
    backend: "local",
    rocm: false,
    toolCalls: false,
    toolParser: null,
    capabilities: ["models", "chat_completions", "context_length"],
    probes: ["endpoint_models", "chat_completion", "context_length"],
    status: "degraded",
    health: 58,
    lastChecked: "1m ago",
    note: "Negative control — strict sentinel rejection.",
    safeRecipes: ["noop","retry_without_config_change","update_endpoint_url","increase_health_max_tokens","lower_health_max_tokens","increase_timeout","increase_retry_backoff","disable_streaming","switch_prompt_template","fallback_model_provider","restore_last_known_good_config","tighten_expected_health_response","lower_max_model_len"],
  },
  {
    id: "amd-vllm-mi300x",
    label: "amd-vllm-mi300x",
    runtime: "vllm",
    adapter: "openai-compatible",
    model: "Qwen3-32B",
    baseUrl: "http://10.0.0.42:8000/v1",
    contextMax: 32768,
    safeContextMax: 65536,
    timeout: 60.0,
    accelerator: "MI300X",
    backend: "amd-developer-cloud",
    rocm: true,
    toolCalls: true,
    toolParser: "qwen3",
    capabilities: ["models", "chat_completions", "tool_calls", "context_length", "rocm_device_flags", "restart"],
    probes: ["endpoint_models", "chat_completion", "context_length", "rocm_device_flags", "tool_call_parser"],
    status: "offline",
    health: 0,
    lastChecked: "—",
    note: "Awaiting AMD Developer Cloud credit allocation.",
    safeRecipes: ["noop","retry_without_config_change","update_endpoint_url","increase_timeout","increase_retry_backoff","disable_streaming","switch_prompt_template","restore_last_known_good_config","lower_max_model_len","set_tool_parser","set_rocm_device_flags","restart_known_service","fallback_model_provider"],
  },
];

/* Recipe registry mirrors rocm_doctor/recipes.py — one entry per registered RepairRecipe.
   editPath / editFrom / editTo describe the deterministic config delta the recipe applies,
   so the loop can render an authentic before/after diff. */
const RECIPES = [
  { id: "noop", desc: "Make no change. Used when the system is healthy or the failure is unactionable.",
    classes: ["no_failure", "unknown_failure"], risk: "none",
    editPath: null, editFrom: null, editTo: null,
    verifies: ["No verification required."] },
  { id: "retry_without_config_change", desc: "Re-run the health check once. Catches transient rate limits with no edit.",
    classes: ["one_time_rate_limit"], risk: "none",
    editPath: null, editFrom: null, editTo: null,
    verifies: ["rerun health check once"] },
  { id: "update_endpoint_url", desc: "Restore the active provider base_url from expected_base_url.",
    classes: ["endpoint_broken", "endpoint_unreachable", "wrong_endpoint_port"], risk: "low",
    editPath: "model_providers.{p}.model.endpoint.base_url",
    editFrom: "http://127.0.0.1:8001/v1", editTo: "http://127.0.0.1:8000/v1",
    verifies: ["GET /v1/models", "POST /v1/chat/completions"] },
  { id: "increase_health_max_tokens", desc: "Raise validation.health_max_tokens for models that need more headroom to emit the sentinel.",
    classes: ["empty_qwen_output"], risk: "low",
    editPath: "model_providers.{p}.validation.health_max_tokens",
    editFrom: "32", editTo: "128",
    verifies: ["POST /v1/chat/completions"] },
  { id: "lower_health_max_tokens", desc: "Drop health_max_tokens to suppress over-answering on weak models.",
    classes: ["health_response_too_long", "repetitive_loop", "timeout"], risk: "low",
    editPath: "model_providers.{p}.validation.health_max_tokens",
    editFrom: "256", editTo: "32",
    verifies: ["POST /v1/chat/completions"] },
  { id: "increase_timeout", desc: "Raise request.timeout_seconds for slow cold starts and large prompt loads.",
    classes: ["timeout"], risk: "low",
    editPath: "model_providers.{p}.request.timeout_seconds",
    editFrom: "1.5", editTo: "5.0",
    verifies: ["GET /v1/models", "POST /v1/chat/completions"] },
  { id: "increase_retry_backoff", desc: "Bump retry.backoff_seconds for noisy upstreams that benefit from spaced retries.",
    classes: ["intermittent_5xx", "rate_limit", "repeated_rate_limit"], risk: "low",
    editPath: "model_providers.{p}.request.retry.backoff_seconds",
    editFrom: "0.05", editTo: "0.5",
    verifies: ["rerun health check once"] },
  { id: "disable_streaming", desc: "Force request.stream=false when SSE framing breaks tool-call parsing.",
    classes: ["sse_parse_error", "stream_truncated", "broken_streaming", "timeout"], risk: "low",
    editPath: "model_providers.{p}.request.stream",
    editFrom: "true", editTo: "false",
    verifies: ["POST /v1/chat/completions"] },
  { id: "switch_prompt_template", desc: "Fall back to the next health-chat template under templates.health_chat_fallbacks.",
    classes: ["health_response_invalid", "empty_qwen_output", "instruction_drift", "repetitive_loop", "bad_template"], risk: "low",
    editPath: "model_providers.{p}.templates.health_chat",
    editFrom: "../templates/health_chat.j2",
    editTo:   "../templates/health_chat.qwen_strict.j2",
    verifies: ["POST /v1/chat/completions"] },
  { id: "fallback_model_provider", desc: "Switch active_model_provider to self_healing.fallback_model_provider.",
    classes: ["provider_unrecoverable", "endpoint_broken", "permanent_500", "repeated_rate_limit"], risk: "med",
    editPath: "active_model_provider",
    editFrom: "fake-openai", editTo: "ollama-qwen3-0-6b",
    verifies: ["GET /v1/models", "POST /v1/chat/completions"] },
  { id: "restore_last_known_good_config", desc: "Roll the workspace back to the most recent verified config snapshot.",
    classes: ["config_drift", "post_repair_regression", "invalid_config"], risk: "med",
    editPath: "<config>",
    editFrom: "current",
    editTo:   "state/snapshots/INC-2026-04-12-002.snap.yaml",
    verifies: ["full check sequence"] },
  { id: "tighten_expected_health_response", desc: "Replace expected_health_response with a stricter sentinel string.",
    classes: ["weak_model_overanswer", "instruction_drift"], risk: "low",
    editPath: "model_providers.{p}.validation.expected_health_response",
    editFrom: "OK", editTo: "ROCM_DOCTOR_OK",
    verifies: ["POST /v1/chat/completions"] },
  { id: "disable_tool_probe_for_weak_model", desc: "Skip tool_call_parser probe for providers whose capabilities exclude tool_calls.",
    classes: ["tool_call_unsupported", "tool_parser_mismatch"], risk: "none",
    editPath: "model_providers.{p}.capabilities.tool_calls",
    editFrom: "true", editTo: "false",
    verifies: ["full check sequence"] },
  { id: "lower_max_model_len", desc: "Reduce model.context.max_tokens to fit within the runtime safe ceiling.",
    classes: ["context_length_too_large"], risk: "low",
    editPath: "model_providers.{p}.model.context.max_tokens",
    editFrom: "8192", editTo: "2048",
    verifies: ["POST /v1/chat/completions"] },
  { id: "set_tool_parser", desc: "Set model.tool_calling.parser to the expected_parser baked into the YAML.",
    classes: ["tool_parser_mismatch"], risk: "low",
    editPath: "model_providers.{p}.model.tool_calling.parser",
    editFrom: "hermes", editTo: "qwen3",
    verifies: ["POST /v1/chat/completions"] },
  { id: "set_rocm_device_flags", desc: "Restore launch.required_device_flags (/dev/kfd, /dev/dri) before the next service restart.",
    classes: ["missing_rocm_device_flags"], risk: "med",
    editPath: "launch.required_device_flags",
    editFrom: "[]", editTo: '["/dev/kfd", "/dev/dri"]',
    verifies: ["GET /v1/models"] },
  { id: "restart_known_service", desc: "Issue a dry-run restart through service.restart_mode and increment service.restart_count.",
    classes: ["unrecoverable_endpoint", "permanent_500"], risk: "high",
    editPath: "service.restart_count",
    editFrom: "0", editTo: "1",
    verifies: ["full check sequence"] },
];

/* Probe-failure messages keyed by failure class — used by the loop's "check" step. */
const PROBE_FAILURE_MSGS = {
  endpoint_broken:        "GET /v1/models failed · ECONNREFUSED",
  wrong_endpoint_port:    "GET /v1/models failed · ECONNREFUSED 127.0.0.1:8001",
  one_time_rate_limit:    "POST /v1/chat/completions 429 Too Many Requests",
  repeated_rate_limit:    "POST /v1/chat/completions 429 · 4 retries exhausted",
  timeout:                "POST /v1/chat/completions exceeded request.timeout_seconds=1.5",
  empty_qwen_output:      "POST /v1/chat/completions returned empty content",
  instruction_drift:      "health response did not match expected_health_response",
  repetitive_loop:        "health response repeated token > max_repeated_token_count",
  broken_streaming:       "SSE stream interrupted before [DONE]",
  bad_template:           "templates.health_chat could not be rendered",
  permanent_500:          "POST /v1/chat/completions 500 · 4 retries exhausted",
  invalid_config:         "config validation failed",
  context_length_too_large:"max_model_len 8192 exceeds safe_max_model_len 4096",
  tool_parser_mismatch:   "POST /v1/chat/completions: response did not contain a tool call",
  missing_rocm_device_flags:"launch.required_device_flags missing /dev/kfd, /dev/dri",
  weak_model_overanswer:  "expected_health_response too permissive — sentinel ambiguous",
};

/* Risk ordering for candidate sort (matches healing_policy ordering preference). */
const RISK_ORDER = { none: 0, low: 1, med: 2, high: 3 };

/* Mirrors FAILURE_TAXONOMY in rocm_doctor/healing_policy.py.
   Each entry's candidates list = the same tuple from the Python taxonomy. */
const FAILURE_TAXONOMY = {
  endpoint_broken:        { description: "endpoint URL or route is broken",
                            candidates: ["update_endpoint_url", "fallback_model_provider"] },
  wrong_endpoint_port:    { description: "configured URL differs from expected URL",
                            candidates: ["update_endpoint_url"] },
  one_time_rate_limit:    { description: "single observed 429",
                            candidates: ["retry_without_config_change"] },
  repeated_rate_limit:    { description: "429 persisted across configured retries",
                            candidates: ["increase_retry_backoff", "fallback_model_provider"] },
  timeout:                { description: "request timed out",
                            candidates: ["increase_timeout", "lower_health_max_tokens", "disable_streaming"] },
  empty_qwen_output:      { description: "Qwen returned no health content",
                            candidates: ["increase_health_max_tokens", "switch_prompt_template"] },
  instruction_drift:      { description: "health output drifted from sentinel",
                            candidates: ["switch_prompt_template", "tighten_expected_health_response"] },
  repetitive_loop:        { description: "health output repeated in a loop",
                            candidates: ["switch_prompt_template", "lower_health_max_tokens"] },
  broken_streaming:       { description: "streaming response was interrupted or malformed",
                            candidates: ["disable_streaming"] },
  bad_template:           { description: "configured prompt template is missing or invalid",
                            candidates: ["switch_prompt_template"] },
  permanent_500:          { description: "provider returned HTTP 5xx after retries",
                            candidates: ["fallback_model_provider", "restart_known_service"] },
  invalid_config:         { description: "config cannot be loaded or validated",
                            candidates: ["restore_last_known_good_config"] },
  context_length_too_large:{description: "max_model_len exceeds safe_max_model_len",
                            candidates: ["lower_max_model_len"] },
  tool_parser_mismatch:   { description: "tool_call parser mismatch — response did not contain a tool call",
                            candidates: ["set_tool_parser", "disable_tool_probe_for_weak_model"] },
  missing_rocm_device_flags:{description: "launch.required_device_flags missing /dev/kfd, /dev/dri",
                            candidates: ["set_rocm_device_flags"] },
  weak_model_overanswer:  { description: "expected_health_response too permissive — sentinel ambiguous",
                            candidates: ["tighten_expected_health_response", "switch_prompt_template", "lower_health_max_tokens"] },
};

/* Top-level injectable failures the operator can pick on the Loop page.
   `expectedRecipe` is the first taxonomy candidate; the loop derives this dynamically. */
const FAILURES = Object.entries(FAILURE_TAXONOMY).map(([id, t]) => ({
  id,
  label: id.replace(/_/g, " "),
  description: t.description,
  candidates: t.candidates,
  expectedRecipe: t.candidates[0],
}));

const INCIDENTS = [
  { id: "INC-2026-04-12-002",  ts: "2026-04-12 14:08:31 UTC", provider: "fake-openai",
    failure: "wrong_endpoint_port", recipe: "update_endpoint_url", attempts: 1, durationMs: 312, outcome: "healed", learned: true },
  { id: "INC-2026-04-12-001",  ts: "2026-04-12 09:51:04 UTC", provider: "ollama-qwen3-0-6b",
    failure: "weak_model_overanswer", recipe: "tighten_expected_health_response", attempts: 2, durationMs: 1820, outcome: "healed", learned: true },
  { id: "INC-2026-04-11-004",  ts: "2026-04-11 22:14:55 UTC", provider: "ollama-smollm2-135m",
    failure: "weak_model_overanswer", recipe: "switch_prompt_template", attempts: 3, durationMs: 4108, outcome: "rolled-back", learned: false },
  { id: "INC-2026-04-11-003",  ts: "2026-04-11 18:02:11 UTC", provider: "fake-openai",
    failure: "context_length_too_large", recipe: "lower_max_model_len", attempts: 1, durationMs: 244, outcome: "healed", learned: true },
  { id: "INC-2026-04-11-002",  ts: "2026-04-11 12:33:20 UTC", provider: "fake-openai",
    failure: "tool_parser_mismatch", recipe: "set_tool_parser", attempts: 1, durationMs: 198, outcome: "healed", learned: true },
  { id: "INC-2026-04-10-007",  ts: "2026-04-10 23:48:02 UTC", provider: "ollama-tinyllama-1-1b",
    failure: "weak_model_overanswer", recipe: "tighten_expected_health_response", attempts: 2, durationMs: 2240, outcome: "healed", learned: true },
  { id: "INC-2026-04-10-006",  ts: "2026-04-10 19:17:44 UTC", provider: "fake-openai",
    failure: "transient_rate_limit", recipe: "retry_without_config_change", attempts: 1, durationMs: 88, outcome: "healed", learned: false },
];

/* Sparkline data for "successful heals over the last 24h". */
const HEAL_TIMESERIES = [3, 4, 2, 5, 6, 4, 7, 8, 6, 9, 7, 10, 8, 11, 9, 12, 10, 11, 13, 11, 14, 12, 13, 15];

/* Derive a healing-loop script for any (failureId, providerId) from the taxonomy
   + recipe registry. This is what makes the loop dynamic — adding a recipe or
   failure entry above flows through automatically. */
function buildHealScript(failureId, providerId) {
  const tax = FAILURE_TAXONOMY[failureId];
  if (!tax) return null;
  const provider = PROVIDERS.find(p => p.id === providerId) || PROVIDERS[0];

  // Candidate ordering = taxonomy order, intersected with the recipes the
  // active provider declares as safe (mirrors healing_policy filter logic).
  // If the provider doesn't expose a safeRecipes allowlist, fall back to the
  // raw taxonomy candidates.
  const safeAllow = provider.safeRecipes || null;
  let candidates = tax.candidates.filter(rid => RECIPES.some(r => r.id === rid));
  if (safeAllow) candidates = candidates.filter(rid => safeAllow.includes(rid));
  if (candidates.length === 0) candidates = tax.candidates.slice(0);

  const chosenId = candidates[0];
  const chosen = RECIPES.find(r => r.id === chosenId);

  return {
    diagnosis: failureId,
    diagnosisDescription: tax.description,
    candidates,
    chosen: chosenId,
    edit: chosen && chosen.editPath ? chosen.editPath.replace("{p}", provider.id) : null,
    edit_from: chosen ? chosen.editFrom : null,
    edit_to:   chosen ? chosen.editTo   : null,
    verify: chosen ? chosen.verifies : ["full check sequence"],
    probeFailure: PROBE_FAILURE_MSGS[failureId] || "unknown failure detected",
  };
}


/* Sample YAML for the Config page (mimics demo/rocm-doctor.yaml) */
const SAMPLE_YAML = `version: 1
workspace: .
reports_dir: reports
state_file: .rocm-doctor-state.json

hardware:
  backend: local
  accelerator: none
  runtime: fake-openai-compatible
  deployment_target: developer-laptop
  amd:
    rocm_required: false
    device_flags: ["/dev/kfd", "/dev/dri"]
    benchmark_profile: local

launch:
  device_flags: ["/dev/kfd", "/dev/dri"]
  required_device_flags: ["/dev/kfd", "/dev/dri"]

service:
  name: fake-vllm
  restart_count: 0
  restart_mode: dry-run

self_healing:
  max_attempts: 3
  fallback_model_provider: ""
  developer_repair_mode: false

active_model_provider: fake-openai
model_providers:
  fake-openai:
    adapter: openai-compatible
    runtime_type: fake
    endpoint_protocol: openai-compatible
    model:
      id: fake-qwen3
      endpoint:
        base_url: http://127.0.0.1:8000/v1
        expected_base_url: http://127.0.0.1:8000/v1
      context:
        max_tokens: 2048
        safe_max_tokens: 4096
      tool_calling:
        enabled: true
        parser: qwen3
        expected_parser: qwen3
    capabilities:
      models: true
      chat_completions: true
      tool_calls: true
      context_length: true
      rocm_device_flags: true
      restart: true
    request:
      timeout_seconds: 1.5
      stream: false
      retry:
        max_attempts: 2
        backoff_seconds: 0.05
    health:
      probes:
        - endpoint_models
        - chat_completion
        - context_length
        - rocm_device_flags
        - tool_call_parser
    repair:
      safe_recipes:
        - noop
        - retry_without_config_change
        - update_endpoint_url
        - lower_max_model_len
        - set_tool_parser
        - set_rocm_device_flags
    validation:
      max_health_response_chars: 120
      health_max_tokens: 32
      expected_health_response: ROCM_DOCTOR_OK

diagnosis:
  active_provider: rules
`;

Object.assign(window, {
  PROVIDERS, RECIPES, FAILURES, FAILURE_TAXONOMY, PROBE_FAILURE_MSGS,
  INCIDENTS, HEAL_TIMESERIES, SAMPLE_YAML,
  buildHealScript, RISK_ORDER,
});

/* ───────────────────────────────────────────────────────────────────────
 * Live API bridge — populated when the static console is served by
 * `python -m rocm_doctor dashboard`. Falls back silently to the static
 * fixtures above if /api/* is unreachable (e.g. opening index.html via
 * file://).
 * ─────────────────────────────────────────────────────────────────────── */

window.API_AVAILABLE = false;

async function _apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const text = await res.text();
  let body;
  try { body = text ? JSON.parse(text) : {}; }
  catch (_) { body = { error: text || res.statusText }; }
  if (!res.ok) {
    const err = new Error(body.error || `HTTP ${res.status}`);
    err.payload = body;
    throw err;
  }
  return body;
}

async function loadDashboardData() {
  try {
    const data = await _apiFetch("/api/snapshot");
    window.PROVIDERS    = data.providers || [];
    window.RECIPES      = data.recipes   || [];
    window.FAILURES     = data.failures  || [];
    window.SCENARIOS    = data.scenarios || [];
    window.INCIDENTS    = data.incidents || [];
    window.SAMPLE_YAML  = data.config_yaml || SAMPLE_YAML;
    window.STATE_JSON   = data.state_json || {};
    window.ACTIVE_PROVIDER = data.active_provider || (data.providers[0] && data.providers[0].id);
    window.WORKING_CONFIG  = data.config_path;
    window.TEMPLATE_CONFIG = data.template_path;
    window.DIAGNOSIS_PROVIDERS = data.diagnosis_providers || ["rules"];
    if (!window.SELECTED_DIAGNOSIS_PROVIDER) {
      window.SELECTED_DIAGNOSIS_PROVIDER = data.diagnosis_provider
        || window.DIAGNOSIS_PROVIDERS[0]
        || "rules";
    }
    window.FAILURE_TAXONOMY = Object.fromEntries(
      (data.failures || []).map(f => [f.id, { description: f.description, candidates: f.candidates }])
    );
    window.API_AVAILABLE = true;
    return { ok: true, data };
  } catch (err) {
    window.API_AVAILABLE = false;
    if (!window.DIAGNOSIS_PROVIDERS) window.DIAGNOSIS_PROVIDERS = ["rules"];
    if (!window.SELECTED_DIAGNOSIS_PROVIDER) window.SELECTED_DIAGNOSIS_PROVIDER = "rules";
    return { ok: false, error: err };
  }
}

async function apiCheck()        { return _apiFetch("/api/check", { method: "POST", body: "{}" }); }
async function apiReset()        { return _apiFetch("/api/reset", { method: "POST", body: "{}" }); }
async function apiSetActive(id)  { return _apiFetch("/api/active-provider", { method: "POST", body: JSON.stringify({ provider_id: id }) }); }
async function apiRun(scenario, providerName) {
  const body = { scenario: scenario || null };
  const name = providerName || window.SELECTED_DIAGNOSIS_PROVIDER;
  if (name) body.provider_name = name;
  return _apiFetch("/api/run", { method: "POST", body: JSON.stringify(body) });
}
async function apiIncident(id)   { return _apiFetch(`/api/incident?id=${encodeURIComponent(id)}`); }

Object.assign(window, {
  loadDashboardData, apiCheck, apiReset, apiSetActive, apiRun, apiIncident,
});
