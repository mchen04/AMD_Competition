import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { IncidentDTO } from "../api/types";
import { useApp } from "../state/AppContext";
import { Panel } from "../components/common/Panel";
import { StatusPill } from "../components/common/Pill";

export function IncidentsPage() {
  const { snapshot, refreshKey } = useApp();
  const incidents = useMemo<IncidentDTO[]>(() => snapshot?.incidents ?? [], [snapshot]);
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
  if (incidents.length === 0 || !selected) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Incidents</h1>
            <p className="page-sub">Auto-generated reports. 0 entries — run a heal to generate one.</p>
          </div>
        </div>
        <div className="page-body">
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
          <p className="page-sub">Auto-generated reports. {incidents.length} entries.</p>
        </div>
      </div>
      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Reports" sub={`${incidents.length} entries`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th>id</th>
                    <th>provider</th>
                    <th className="right">outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((i) => (
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
                      <td className="mono dim" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: 140 }}>
                        {i.provider || "—"}
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
