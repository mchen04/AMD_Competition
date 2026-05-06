import { Panel } from "../../components/common/Panel";
import type { FailureDTO, FailureKind } from "../../api/types";

interface Props {
  failures: FailureDTO[];
  selected: string;
  disabled: boolean;
  onSelect: (id: string) => void;
}

interface Section {
  kind: FailureKind;
  title: string;
  hint: string;
}

const SECTIONS: Section[] = [
  {
    kind: "heal",
    title: "Heal demo",
    hint: "Mutates the working YAML so a real probe fails. A deterministic recipe heals it.",
  },
  {
    kind: "safety",
    title: "Safety probe",
    hint: "Steers the fake brain into a malicious output mode. Pair with diagnose: fake to see the executor reject it.",
  },
  {
    kind: "external",
    title: "Adversarial proxy only",
    hint: "Taxonomy-only failure class. Not injectable from this UI — drive it through scripts/chaos_qwen.sh against a real backend.",
  },
];

export function FailurePicker({ failures, selected, disabled, onSelect }: Props) {
  const grouped: Record<FailureKind, FailureDTO[]> = {
    heal: [],
    safety: [],
    external: [],
  };
  for (const failure of failures) {
    grouped[failure.kind].push(failure);
  }
  const totalInjectable = grouped.heal.length + grouped.safety.length;

  return (
    <Panel
      title="Inject failure"
      sub={`${totalInjectable} injectable · ${grouped.external.length} reference`}
      actions={
        disabled && (
          <span className="pill info">
            <span className="dot" />
            running
          </span>
        )
      }
      flush
    >
      <div className="panel-body" style={{ overflow: "auto" }}>
        {SECTIONS.map((section) => {
          const items = grouped[section.kind];
          if (items.length === 0) return null;
          const externalSection = section.kind === "external";
          return (
            <div key={section.kind} className={`failure-section failure-section--${section.kind}`}>
              <div className="failure-section-head">
                <span className="failure-section-title">{section.title}</span>
                <span className="failure-section-count">{items.length}</span>
              </div>
              <p className="failure-section-hint">{section.hint}</p>
              <div className="failure-grid">
                {items.map((f) => {
                  const isExternal = externalSection;
                  const tooltip = isExternal
                    ? `${f.description} — not injectable from the dashboard.`
                    : f.description;
                  return (
                    <button
                      key={f.id}
                      className={
                        "chip" +
                        (selected === f.id ? " active" : "") +
                        ` chip--${section.kind}`
                      }
                      onClick={() => !disabled && !isExternal && onSelect(f.id)}
                      disabled={disabled || isExternal}
                      title={tooltip}
                    >
                      {f.id}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}
