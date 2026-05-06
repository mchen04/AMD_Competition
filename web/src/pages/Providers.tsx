import { useState } from "react";
import { useApp } from "../state/AppContext";
import { Panel } from "../components/common/Panel";
import { StatusPill } from "../components/common/Pill";
import { ListRow } from "../components/common/ListRow";
import { Icon } from "../components/common/Icon";

export function ProvidersPage() {
  const { snapshot, activeProviderId, setActiveProviderId } = useApp();
  const [selectedId, setSelectedId] = useState<string>(activeProviderId);
  if (!snapshot) return null;
  const p = snapshot.providers.find((x) => x.id === selectedId) ?? snapshot.providers[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Providers</h1>
          <p className="page-sub">
            Adapters defined under <span className="mono">model_providers.*</span>
          </p>
        </div>
      </div>

      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Configured" sub={`${snapshot.providers.length} entries`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              {snapshot.providers.map((prov) => (
                <ListRow
                  key={prov.id}
                  iconName="server"
                  primary={prov.id}
                  secondary={`${prov.runtime} · ${prov.accelerator}`}
                  trailing={<StatusPill status={prov.status} />}
                  selected={prov.id === selectedId}
                  onClick={() => {
                    setSelectedId(prov.id);
                    void setActiveProviderId(prov.id);
                  }}
                />
              ))}
            </div>
          </Panel>

          <div className="grid" style={{ gridTemplateRows: "auto 1fr", gap: 12, minHeight: 0 }}>
            {p && (
              <>
                <Panel
                  title={p.id}
                  sub={`${p.adapter} · ${p.runtime}`}
                  actions={<StatusPill status={p.status} />}
                >
                  <dl className="kv">
                    <dt>model</dt>
                    <dd>{p.model}</dd>
                    <dt>endpoint</dt>
                    <dd>{p.baseUrl}</dd>
                    <dt>backend</dt>
                    <dd>{p.backend}</dd>
                    <dt>accelerator</dt>
                    <dd>{p.accelerator}</dd>
                    <dt>rocm</dt>
                    <dd>{p.rocm ? "yes" : "no"}</dd>
                    <dt>tool_calls</dt>
                    <dd>{p.toolCalls ? `enabled · ${p.toolParser ?? ""}` : "disabled"}</dd>
                    <dt>context.max</dt>
                    <dd>
                      {p.contextMax} <span className="muted">(safe ≤ {p.safeContextMax})</span>
                    </dd>
                    <dt>timeout</dt>
                    <dd>{p.timeout}s</dd>
                  </dl>
                </Panel>

                <Panel title="Probes & safe recipes" flush>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", flex: 1, minHeight: 0 }}>
                    <div style={{ borderRight: "1px solid var(--line-soft)", overflow: "auto" }}>
                      <div className="kv-label" style={{ padding: "8px 12px 4px" }}>
                        probes ({p.probes.length})
                      </div>
                      {p.probes.map((pr) => (
                        <div className="probe-row" key={pr}>
                          <Icon name="check" size={12} color="var(--ok)" />
                          <span className="probe-name">{pr}</span>
                        </div>
                      ))}
                    </div>
                    <div style={{ overflow: "auto" }}>
                      <div className="kv-label" style={{ padding: "8px 12px 4px" }}>
                        safe recipes ({p.safeRecipes.length})
                      </div>
                      <div style={{ padding: "0 12px 12px", display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {p.safeRecipes.map((r) => (
                          <span key={r} className="pill muted">
                            {r}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </Panel>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
