import { useState } from "react";
import { useApp } from "../state/AppContext";
import { Panel } from "../components/common/Panel";
import { YamlView } from "../components/common/YamlView";

export function ConfigPage() {
  const { snapshot } = useApp();
  const [tab, setTab] = useState<"active" | "snapshots" | "state">("active");
  if (!snapshot) return null;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Config</h1>
          <p className="page-sub">Workspace YAML + persistent state.</p>
        </div>
      </div>
      <div className="tabs" style={{ flexShrink: 0 }}>
        {(
          [
            ["active", "rocm-doctor.yaml"],
            ["snapshots", "Snapshots"],
            ["state", "state.json"],
          ] as const
        ).map(([k, l]) => (
          <div key={k} className={"tab" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>
            {l}
          </div>
        ))}
      </div>
      <div className="page-body">
        <Panel className="fill" flush>
          {tab === "active" && (
            <pre
              className="code"
              style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}
            >
              <YamlView yaml={snapshot.config_yaml} />
            </pre>
          )}
          {tab === "snapshots" && (
            <div style={{ flex: 1, overflow: "auto" }}>
              {snapshot.incidents.length > 0 ? (
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>incident</th>
                      <th>recipe</th>
                      <th>outcome</th>
                      <th className="right">report bytes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.incidents.map((i) => (
                      <tr key={i.id}>
                        <td className="mono">{i.id}</td>
                        <td className="mono">
                          {i.recipe ? (
                            <span style={{ color: "var(--accent)" }}>{i.recipe}</span>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td className="mono dim">{i.outcome}</td>
                        <td className="right mono dim">
                          {typeof i.size === "number" ? i.size.toLocaleString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty" style={{ padding: 24 }}>
                  No incident reports yet — run a heal from the Healing Loop page.
                </div>
              )}
            </div>
          )}
          {tab === "state" && (
            <pre
              className="code"
              style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}
            >
              {Object.keys(snapshot.state_json).length > 0
                ? JSON.stringify(snapshot.state_json, null, 2)
                : "// state.json is empty — run a heal to populate learned_fixes, last-known-good snapshots, etc."}
            </pre>
          )}
        </Panel>
      </div>
    </div>
  );
}
