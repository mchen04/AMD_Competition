import type { RunResultResponse, SSEEvent } from "../../api/types";
import { Icon } from "../../components/common/Icon";

type StepState = "pending" | "active" | "done" | "fail";
interface Step {
  name: string;
  state: StepState;
  detail: string;
}

interface Props {
  events: SSEEvent[];
  result: RunResultResponse | null;
  running: boolean;
}

export function Pipeline({ events, result, running }: Props) {
  const steps = computeSteps(events, result, running);
  return (
    <div className="loop">
      {steps.map((s, i) => {
        const cls =
          s.state === "done"
            ? "is-done"
            : s.state === "active"
              ? "is-active"
              : s.state === "fail"
                ? "is-fail"
                : "is-pending";
        return (
          <div key={s.name} className={"loop-step " + cls}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <div className="step-marker">
                {s.state === "done" ? (
                  <Icon name="check" size={11} />
                ) : s.state === "fail" ? (
                  <Icon name="x" size={11} />
                ) : (
                  i + 1
                )}
              </div>
              <div>
                <div className="step-idx">step {i + 1}</div>
                <div className="step-name">{s.name}</div>
              </div>
            </div>
            <div className="step-detail">{s.detail}</div>
          </div>
        );
      })}
    </div>
  );
}

function computeSteps(events: SSEEvent[], result: RunResultResponse | null, running: boolean): Step[] {
  const base: Step[] = [
    { name: "check", state: "pending", detail: "—" },
    { name: "diagnose", state: "pending", detail: "—" },
    { name: "heal", state: "pending", detail: "—" },
    { name: "verify", state: "pending", detail: "—" },
    { name: "report", state: "pending", detail: "—" },
  ];

  const has = (name: string) => events.find((e) => e.event === name);

  if (has("check.started") || has("inject.applied")) {
    base[0].state = "fail"; // health probe always fails before diagnosis runs
    const inject = has("inject.applied");
    if (inject) base[0].detail = String(inject.data.scenario ?? "scenario applied");
  }
  if (has("diagnosis.started")) {
    base[1].state = "active";
    base[1].detail = "diagnosing";
  }
  if (has("diagnosis.completed") || has("repair.applied") || has("repair.rejected")) {
    base[1].state = "done";
    const diag = result?.diagnosis;
    if (diag) base[1].detail = diag.failure_class;
  }
  const lastRepair = [...events].reverse().find((e) => e.event === "repair.applied" || e.event === "repair.rejected");
  if (lastRepair) {
    const repair = (lastRepair.data as { repair?: { recipe_id?: string; rejected?: boolean; rolled_back?: boolean } })
      .repair;
    base[2].state = repair?.rejected ? "fail" : repair?.rolled_back ? "fail" : "done";
    base[2].detail = repair?.rolled_back ? "rolled back" : repair?.recipe_id ?? "—";
  } else if (running && has("diagnosis.completed")) {
    base[2].state = "active";
    base[2].detail = "applying recipe";
  }
  const verification = has("verification.completed");
  if (verification) {
    const healthy = Boolean((verification.data as { healthy?: boolean }).healthy);
    base[3].state = healthy ? "done" : "fail";
    base[3].detail = healthy ? "all probes ok" : "verification failed";
  }
  const report = has("report.written");
  if (report) {
    base[4].state = "done";
    base[4].detail = String((report.data as { incident_id?: string }).incident_id ?? "");
  }
  if (has("error")) {
    for (const step of base) {
      if (step.state === "active" || step.state === "pending") {
        step.state = "fail";
        step.detail = "errored";
        break;
      }
    }
  }

  return base;
}
