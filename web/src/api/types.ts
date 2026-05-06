// Hand-mirrored TypeScript shapes for /api/* responses.
// Source of truth: rocm_doctor/api/schemas.py and rocm_doctor/api/schema.json.
// Keep this file aligned with the Python TypedDicts when adding fields.

export interface ProviderDTO {
  id: string;
  label: string;
  runtime: string;
  adapter: string;
  model: string;
  baseUrl: string;
  contextMax: number;
  safeContextMax: number;
  timeout: number;
  accelerator: string;
  backend: string;
  rocm: boolean;
  toolCalls: boolean;
  toolParser: string | null;
  capabilities: string[];
  probes: string[];
  safeRecipes: string[];
  active: boolean;
  status: string;
  health: number;
  lastChecked: string;
  note: string;
}

export interface RecipeDTO {
  id: string;
  desc: string;
  humanLabel: string;
  tags: string[];
  classes: string[];
  risk: string;
  editPath: string | null;
  editFrom: string | number | boolean | null;
  editTo: string | number | boolean | null;
  verifies: string[];
}

export type FailureKind = "heal" | "safety" | "external";

export interface FailureDTO {
  id: string;
  label: string;
  description: string;
  candidates: string[];
  expectedRecipe: string | null;
  scenario: string | null;
  kind: FailureKind;
}

export interface IncidentDTO {
  id: string;
  ts: string;
  provider: string;
  failure: string;
  recipe: string;
  outcome: "healed" | "rolled-back" | "degraded";
  path: string;
  size: number;
  durationMs?: number;
}

export interface SupervisorCycleEntry {
  iteration: number;
  ts: string;
  outcome: "healthy" | "unhealthy" | "skipped" | "error";
  recovered: boolean;
  reason: string;
  elapsed_seconds: number;
  diagnosis?: { failure_class?: string; suspected_cause?: string } | null;
  intent?: IntentClassification | null;
}

export interface SnapshotResponse {
  config_path: string;
  template_path: string;
  workspace: string;
  active_provider: string;
  providers: ProviderDTO[];
  recipes: RecipeDTO[];
  failures: FailureDTO[];
  scenarios: string[];
  incidents: IncidentDTO[];
  state_json: Record<string, unknown> & {
    supervisor_cycles?: SupervisorCycleEntry[];
  };
  config_yaml: string;
  diagnosis_providers: string[];
  diagnosis_provider: string;
}

export interface CheckResponse {
  health: Record<string, unknown>;
  evidence: Record<string, unknown>;
}

export interface RunStartedResponse {
  run_id: string;
  scenario: string | null;
  diagnosis_provider: string;
}

export interface RepairDTO {
  recipe_id: string;
  applied: boolean;
  rejected: boolean;
  rolled_back: boolean;
  reason: string;
  changed_paths: string[];
  failure_class: string;
  verification_message: string;
  learned: boolean;
}

export interface SelfHealDTO {
  healthy: boolean;
  recovered: boolean;
  attempts: number;
  unrecoverable: boolean;
  reason: string;
  repairs: RepairDTO[];
}

export interface DiagnosisDTO {
  failure_class: string;
  confidence: number;
  evidence: string[];
  suspected_cause: string;
  recommended_recipe_ids: string[];
  provider: string;
}

export interface RunResultResponse {
  run_id: string;
  state: "running" | "done";
  scenario: string | null;
  inject?: Record<string, unknown> | null;
  self_heal?: SelfHealDTO | null;
  diagnosis?: DiagnosisDTO | null;
  before_evidence?: Record<string, unknown> | null;
  after_evidence?: Record<string, unknown> | null;
  report_path?: string | null;
  incident_id?: string | null;
  duration_ms?: number;
  diagnosis_provider: string;
  incidents?: IncidentDTO[];
  error: string | null;
}

export interface ResetResponse {
  reset: boolean;
  config_path: string;
}

export interface ActiveProviderResponse {
  active_provider: string;
}

export interface ConfigChoiceDTO {
  id: string;
  label: string;
  path: string;
  source: "bundled" | "user";
  current: boolean;
  valid: boolean;
  error: string | null;
  providers: number;
  provider_ids: string[];
  active: string;
  diagnosis_active: string;
}

export interface ConfigsListResponse {
  bundled: ConfigChoiceDTO[];
  user: ConfigChoiceDTO[];
  current_path: string;
  user_dir: string;
}

export interface ConfigSelectResponse {
  selected: string;
  path: string;
  diagnosis_provider: string;
}

export interface ConfigImportResponse {
  imported: string;
  name: string;
  path: string;
  selected: boolean;
}

export interface IncidentResponse {
  id: string;
  path: string;
  body: string;
}

export type SSEEventName =
  | "run.queued"
  | "check.started"
  | "check.failed"
  | "inject.applied"
  | "diagnosis.started"
  | "diagnosis.completed"
  | "repair.applied"
  | "repair.rejected"
  | "verification.completed"
  | "report.written"
  | "done"
  | "error"
  | "supervisor.started"
  | "supervisor.stopped"
  | "cycle.started"
  | "cycle.healthy"
  | "cycle.skipped"
  | "cycle.unhealthy"
  | "cycle.completed"
  | "cycle.error";

export interface SSEEvent<T = Record<string, unknown>> {
  event: SSEEventName;
  run_id: string;
  seq: number;
  ts: string;
  data: T;
}

// ── Intent classifier (mirrors rocm_doctor/schemas.py::IntentClassification) ──

export type IntentValue = "intentional" | "unintentional" | "uncertain";
export type IntentAction = "heal" | "record_only" | "ask_human";

export interface IntentClassification {
  intent: IntentValue;
  confidence: number;
  reasoning: string;
  recommend_action: IntentAction;
  baseline_kind: string;
  diff_path_count: number;
  provider: string;
}

// ── Baseline (Phase 3) ────────────────────────────────────────────────

export interface BaselineDiffEntry {
  path: string;
  before?: unknown;
  after?: unknown;
}

export interface BaselineDiff {
  changed: BaselineDiffEntry[];
  added: BaselineDiffEntry[];
  removed: BaselineDiffEntry[];
}

export interface BaselineState {
  baseline_kind: "pinned" | "last_known_good" | "none";
  diff: BaselineDiff;
  pinned_at: string | null;
  pinned: boolean;
}

// ── Supervisor (Phase 2) ──────────────────────────────────────────────

export interface SupervisorRun {
  run_id: string;
  state: "running" | "done";
  diagnosis_provider: string;
  error: string | null;
  summary: Record<string, unknown> | null;
  started_at: number;
}

export interface SupervisorEvent extends SSEEvent {
  event:
    | "supervisor.started"
    | "supervisor.stopped"
    | "cycle.started"
    | "cycle.healthy"
    | "cycle.skipped"
    | "cycle.unhealthy"
    | "cycle.completed"
    | "cycle.error";
}
