import { useApp } from "../state/AppContext";
import { Icon } from "../components/common/Icon";

interface Props {
  onRun: (failureId: string) => void;
}

export function FailuresPage({ onRun }: Props) {
  const { snapshot } = useApp();
  if (!snapshot) return null;
  const failures = snapshot.failures;
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Failures</h1>
          <p className="page-sub">{failures.length} failure classes from the failure taxonomy.</p>
        </div>
      </div>
      <div className="page-body">
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="grid recipes-grid">
            {failures.map((f) => (
              <div className="recipe" key={f.id}>
                <div className="recipe-head">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="recipe-id">{f.id}</div>
                    <div className="recipe-desc">{f.description}</div>
                  </div>
                  <Icon name="flask" size={14} color="var(--accent)" />
                </div>
                <div className="recipe-tags">
                  {f.candidates.length > 0 ? (
                    <>
                      <span className="pill muted">→</span>
                      {f.candidates.map((c) => (
                        <span key={c} className="pill info mono">
                          {c}
                        </span>
                      ))}
                    </>
                  ) : (
                    <span className="pill muted">injection-only · no candidate recipes</span>
                  )}
                </div>
                <div style={{ marginTop: "auto", display: "flex", justifyContent: "flex-end" }}>
                  <button
                    className="btn primary"
                    style={{ padding: "3px 10px", fontSize: 11.5 }}
                    onClick={() => onRun(f.id)}
                  >
                    <Icon name="play" size={11} /> run
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
