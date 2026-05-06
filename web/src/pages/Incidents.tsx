import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type {
  IncidentDTO,
  IntentClassification,
  SupervisorCycleEntry,
} from "../api/types";
import { useApp } from "../state/AppContext";
import { Panel } from "../components/common/Panel";
import { StatusPill } from "../components/common/Pill";

function intentBadge(intent: IntentClassification): { label: string; tone: string } {
  if (intent.recommend_action === "heal") {
    return { label: `${intent.intent} → healed`, tone: "var(--ok)" };
  }
  if (intent.recommend_action === "record_only") {
    return { label: `${intent.intent} → recorded`, tone: "var(--warn)" };
  }
  return { label: `${intent.intent} → human`, tone: "var(--text-2)" };
}

function cycleOutcomeTone(outcome: SupervisorCycleEntry["outcome"]): string {
  if (outcome === "healthy") return "var(--ok)";
  if (outcome === "skipped") return "var(--warn)";
  if (outcome === "error") return "var(--bad)";
  return "var(--bad)";
}

export function IncidentsPage() {
  const { snapshot, refreshKey } = useApp();
  const incidents = useMemo<IncidentDTO[]>(() => snapshot?.incidents ?? [], [snapshot]);
  const latestIntent = useMemo<IntentClassification | null>(() => {
    const raw = (snapshot?.state_json as { intent?: unknown } | undefined)?.intent;
    if (!raw || typeof raw !== "object") return null;
    const intent = raw as Partial<IntentClassification>;
    if (!intent.intent || !intent.recommend_action) return null;
    return {
      intent: intent.intent,
      confidence: Number(intent.confidence ?? 0),
      reasoning: String(intent.reasoning ?? ""),
      recommend_action: intent.recommend_action,
      baseline_kind: String(intent.baseline_kind ?? ""),
      diff_path_count: Number(intent.diff_path_count ?? 0),
      provider: String(intent.provider ?? ""),
    };
  }, [snapshot]);
  const cycles = useMemo<SupervisorCycleEntry[]>(() => {
    const raw = snapshot?.state_json?.supervisor_cycles;
    if (!Array.isArray(raw)) return [];
    return [...(raw as SupervisorCycleEntry[])].reverse();
  }, [snapshot]);
  const [selected, setSelected] = useState<IncidentDTO | null>(incidents[0] ?? null);
  const [reportBody, setReportBody] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected || !incidents.find((i) => i.id === selected.id)) {
      setSelected(incidents[0] ?? null);
    }
  }, [incidents, selected, refreshKey]);

  useEffect(() => {
    if (!selected) {
      setReportBody(null);
      return;
    }
    setReportBody(null);
    setError(null);
    api
      .incident(selected.id)
      .then((r) => setReportBody(r.body))
      .catch((e) => setError(e instanceof Error ? e.message : "failed"));
  }, [selected, refreshKey]);

  if (!snapshot) return null;

  const cyclesPanel = cycles.length > 0 ? <SupervisorCyclesPanel cycles={cycles} /> : null;

  if (incidents.length === 0 || !selected) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Incidents</h1>
            <p className="page-sub">
              Auto-generated reports. 0 entries — run a heal to generate one.
              {cycles.length > 0 ? ` ${cycles.length} supervisor cycle(s) recorded.` : ""}
            </p>
          </div>
        </div>
        <div className="page-body">
          {cyclesPanel}
          <Panel flush>
            <div className="empty">No incident reports yet. Run a heal from the Healing Loop page.</div>
          </Panel>
        </div>
      </div>
    );
  }

  const outcomeStatus =
    selected.outcome === "healed" ? "healthy" : selected.outcome === "rolled-back" ? "failing" : "degraded";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Incidents</h1>
          <p className="page-sub">
            Auto-generated reports. {incidents.length} entries.
            {cycles.length > 0 ? ` ${cycles.length} supervisor cycle(s) recorded.` : ""}
          </p>
        </div>
      </div>
      <div className="page-body">
        {cyclesPanel}
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Reports" sub={`${incidents.length} entries`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>provider</th>
                    <th>intent</th>
                    <th className="right">outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((i, idx) => {
                    const showIntent = idx === 0 && latestIntent;
                    const badge = showIntent ? intentBadge(latestIntent!) : null;
                    return (
                      <tr
                        key={i.id}
                        className="row-hover"
                        style={{
                          cursor: "pointer",
                          background: i.id === selected.id ? "var(--bg-3)" : undefined,
                        }}
                        onClick={() => setSelected(i)}
                      >
                        <td className="mono">{i.id}</td>
                        <td className="mono dim" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: 120 }}>
                          {i.provider || "—"}
                        </td>
                        <td className="mono" style={{ fontSize: 11 }}>
                          {badge ? (
                            <span style={{ color: badge.tone }}>{badge.label}</span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="right">
                          <StatusPill
                            status={
                              i.outcome === "healed"
                                ? "healthy"
                                : i.outcome === "rolled-back"
                                  ? "failing"
                                  : "degraded"
                            }
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid" style={{ gridTemplateRows: "auto 1fr", gap: 12, minHeight: 0 }}>
            <div className="incident-meta">
              <div>
                <div className="lbl">incident</div>
                <div className="val">{selected.id}</div>
              </div>
              <div>
                <div className="lbl">provider</div>
                <div className="val">{selected.provider || "—"}</div>
              </div>
              <div>
                <div className="lbl">recipe</div>
                <div className="val">{selected.recipe || "—"}</div>
              </div>
              <div>
                <div className="lbl">outcome</div>
                <div className="val">
                  <StatusPill status={outcomeStatus} />
                </div>
              </div>
            </div>
            {latestIntent && (
              <Panel
                title="Last intent"
                sub={`${latestIntent.provider} · ${latestIntent.baseline_kind} baseline · ${latestIntent.diff_path_count} path(s)`}
                flush
              >
                <div style={{ padding: "10px 14px", fontSize: 12 }}>
                  <span style={{ color: intentBadge(latestIntent).tone }}>
                    {intentBadge(latestIntent).label}
                  </span>{" "}
                  <span className="muted">· confidence {(latestIntent.confidence * 100).toFixed(0)}%</span>
                  <div className="muted mono" style={{ marginTop: 4, fontSize: 11 }}>
                    {latestIntent.reasoning}
                  </div>
                </div>
              </Panel>
            )}
            <Panel title="Report" sub={selected.path || `reports/${selected.id}.md`} flush>
              <pre
                className="code"
                style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}
              >
                {error ? `error: ${error}` : reportBody == null ? "loading…" : reportBody}
              </pre>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}

function SupervisorCyclesPanel({ cycles }: { cycles: SupervisorCycleEntry[] }) {
  const summary = useMemo(() => {
    const tally = { healthy: 0, unhealthy: 0, skipped: 0, error: 0 };
    for (const c of cycles) tally[c.outcome] = (tally[c.outcome] ?? 0) + 1;
    return tally;
  }, [cycles]);
  return (
    <Panel
      title="Supervisor cycles"
      sub={`${cycles.length} recorded · ${summary.healthy} healthy · ${summary.unhealthy} unhealthy · ${summary.skipped} skipped${
        summary.error ? ` · ${summary.error} error` : ""
      }`}
      flush
    >
      <div style={{ overflow: "auto", maxHeight: 220 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>iter</th>
              <th>ts</th>
              <th>intent</th>
              <th>diagnosis</th>
              <th className="right">outcome</th>
            </tr>
          </thead>
          <tbody>
            {cycles.map((entry) => {
              const intent = entry.intent ?? null;
              const badge = intent ? intentBadge(intent) : null;
              const failureClass = entry.diagnosis?.failure_class ?? "";
              return (
                <tr key={`${entry.iteration}-${entry.ts}`}>
                  <td className="mono">#{entry.iteration}</td>
                  <td className="mono dim" style={{ fontSize: 11 }}>{entry.ts}</td>
                  <td className="mono" style={{ fontSize: 11 }}>
                    {badge ? (
                      <span style={{ color: badge.tone }}>{badge.label}</span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="mono dim" style={{ fontSize: 11 }}>
                    {failureClass || "—"}
                    {entry.recovered ? <span style={{ color: "var(--ok)" }}> · recovered</span> : null}
                  </td>
                  <td className="right">
                    <span style={{ color: cycleOutcomeTone(entry.outcome), fontSize: 11 }}>
                      {entry.outcome}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
