import { useApp } from "../state/AppContext";
import { Panel } from "../components/common/Panel";
import { Stat } from "../components/common/Stat";
import { StatusPill } from "../components/common/Pill";
import { Icon } from "../components/common/Icon";
import { ListRow } from "../components/common/ListRow";
import { BaselineStrip } from "../components/overview/BaselineStrip";
import { SupervisorPanel } from "../components/overview/SupervisorPanel";

interface OverviewPageProps {
  onOpenPipeline: () => void;
}

export function OverviewPage({ onOpenPipeline }: OverviewPageProps) {
  const { snapshot, activeProviderId, refresh, refreshKey, diagnosisProvider } = useApp();
  if (!snapshot) return null;

  const provider = snapshot.providers.find((p) => p.id === activeProviderId) ?? snapshot.providers[0];
  const incidents = snapshot.incidents;
  const healed = incidents.filter((i) => i.outcome === "healed").length;
  const learnedFixes = (() => {
    const lf = (snapshot.state_json as { learned_fixes?: Record<string, unknown> }).learned_fixes;
    if (lf && typeof lf === "object") return Object.keys(lf).length;
    return 0;
  })();
  const durations = incidents.filter((i) => typeof i.durationMs === "number");
  const meanMs =
    durations.length > 0
      ? Math.round(durations.reduce((s, i) => s + (i.durationMs ?? 0), 0) / durations.length)
      : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Model CI/CD on AMD</h1>
          <p className="page-sub">
            Pin a known-good deployment, supervise it continuously, let an LLM agent decide intent, heal until pass.
          </p>
        </div>
        <div className="page-actions">
          <button className="btn primary" onClick={onOpenPipeline}>
            <Icon name="activity" size={12} /> open pipeline
          </button>
        </div>
      </div>

      <div className="grid cols-4" style={{ flexShrink: 0 }}>
        <Stat
          label="Active provider"
          value={provider?.id ?? "—"}
          mono
          foot={
            <>
              <span className="pill ok">
                <span className="dot" />
                {provider?.status ?? "—"}
              </span>
              <span className="muted"> · {provider?.runtime ?? "—"}</span>
            </>
          }
        />
        <Stat
          label="Healed runs"
          value={`${healed}`}
          foot={incidents.length > 0 ? `of ${incidents.length} incidents` : "no incidents yet"}
          footTone={healed > 0 ? "ok" : ""}
        />
        <Stat
          label="Mean recovery"
          value={meanMs > 0 ? `${meanMs} ms` : "—"}
          mono
          foot={durations.length > 0 ? `across ${durations.length} incidents` : "no timing data"}
        />
        <Stat label="Learned fixes" value={`${learnedFixes}`} foot="cached in state.json" />
      </div>

      <div className="grid cols-2" style={{ flexShrink: 0, gap: 12, marginTop: 8 }}>
        <BaselineStrip refreshKey={refreshKey} onChange={() => void refresh()} />
        <SupervisorPanel defaultProvider={diagnosisProvider} onCycle={() => void refresh()} />
      </div>

      <div className="page-body">
        <div className="grid cols-2-1" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Recent incidents" sub={`${incidents.length} entries`} flush>
            <div style={{ flex: 1, padding: 12, overflow: "auto" }}>
              <table className="tbl" style={{ background: "transparent" }}>
                <thead>
                  <tr>
                    <th>id</th>
                    <th>provider</th>
                    <th>recipe</th>
                    <th className="right">outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.slice(0, 8).map((i) => (
                    <tr key={i.id}>
                      <td className="mono">{i.id}</td>
                      <td className="mono dim">{i.provider}</td>
                      <td className="mono">
                        <span style={{ color: "var(--accent)" }}>{i.recipe}</span>
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
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Provider fleet" sub={`${snapshot.providers.length} configured`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              {snapshot.providers.map((p) => (
                <ListRow
                  key={p.id}
                  iconName="server"
                  primary={p.id}
                  secondary={`${p.runtime} · ${p.model}`}
                  trailing={<StatusPill status={p.status} />}
                />
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
