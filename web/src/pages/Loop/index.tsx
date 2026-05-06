import { useEffect, useMemo, useState } from "react";
import { useApp } from "../../state/AppContext";
import { useRun } from "../../state/hooks";
import { Panel } from "../../components/common/Panel";
import { Icon } from "../../components/common/Icon";
import { FailurePicker } from "./FailurePicker";
import { RecipePlan } from "./RecipePlan";
import { Pipeline } from "./Pipeline";
import { LogViewer } from "./LogViewer";

interface LoopPageProps {
  presetFailureId: string | null;
  presetRunKey: number;
}

export function LoopPage({ presetFailureId, presetRunKey }: LoopPageProps) {
  const { snapshot, diagnosisProvider, setDiagnosisProvider } = useApp();
  const failures = snapshot?.failures ?? [];
  const counts = useMemo(() => {
    const heal = failures.filter((f) => f.kind === "heal").length;
    const safety = failures.filter((f) => f.kind === "safety").length;
    const external = failures.filter((f) => f.kind === "external").length;
    return { heal, safety, external };
  }, [failures]);
  const initialFailure = useMemo(() => {
    if (presetFailureId) return presetFailureId;
    return (
      failures.find((f) => f.kind === "heal")?.id ??
      failures.find((f) => f.scenario)?.id ??
      failures[0]?.id ??
      "wrong_endpoint_port"
    );
  }, [presetFailureId, failures]);

  const [failureId, setFailureId] = useState<string>(initialFailure);
  const run = useRun();

  // When the user picks a safety probe, default the brain to `fake` so the
  // executor's safety gates actually fire. Heal scenarios leave the brain
  // alone so the user keeps whatever (rules / codex-cli / anthropic) they had.
  const selectFailure = (id: string) => {
    setFailureId(id);
    const failure = failures.find((f) => f.id === id);
    if (
      failure?.kind === "safety" &&
      diagnosisProvider !== "fake" &&
      snapshot?.diagnosis_providers.includes("fake")
    ) {
      setDiagnosisProvider("fake");
    }
  };

  useEffect(() => {
    if (!presetRunKey) return;
    const target = presetFailureId ?? initialFailure;
    setFailureId(target);
    const failure = failures.find((f) => f.id === target);
    void run.start(failure?.scenario ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetRunKey]);

  const failure = failures.find((f) => f.id === failureId) ?? null;
  const recipe = useMemo(() => {
    if (!snapshot || !failure) return null;
    const recipeId = failure.candidates[0];
    if (!recipeId) return null;
    return snapshot.recipes.find((r) => r.id === recipeId) ?? null;
  }, [snapshot, failure]);

  const onRun = () => {
    if (run.running) return;
    void run.start(failure?.scenario ?? null);
  };

  const subText =
    `${counts.heal} heal · ${counts.safety} safety · ${counts.external} reference. ` +
    `check → diagnose → candidate recipes → apply → verify → report.`;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Healing Loop</h1>
          <p className="page-sub">{subText}</p>
        </div>
        <div className="page-actions">
          <button className="btn" disabled={run.running} onClick={() => run.reset()}>
            <Icon name="x" size={12} /> reset
          </button>
          <button className="btn primary" disabled={run.running} onClick={onRun}>
            <Icon name="play" size={12} /> {run.running ? "running…" : "run"}
          </button>
        </div>
      </div>

      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <div className="grid" style={{ gridTemplateRows: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12, minHeight: 0 }}>
            <FailurePicker
              failures={failures}
              selected={failureId}
              disabled={run.running}
              onSelect={selectFailure}
            />
            <RecipePlan failure={failure} recipe={recipe} />
          </div>
          <Panel title="Pipeline" sub={run.running ? "executing" : "idle"} flush className="fill">
            <Pipeline events={run.events} result={run.result} running={run.running} />
            <LogViewer events={run.events} error={run.error} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
