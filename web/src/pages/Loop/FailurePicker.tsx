import { Panel } from "../../components/common/Panel";
import type { FailureDTO } from "../../api/types";

interface Props {
  failures: FailureDTO[];
  selected: string;
  disabled: boolean;
  onSelect: (id: string) => void;
}

export function FailurePicker({ failures, selected, disabled, onSelect }: Props) {
  return (
    <Panel
      title="Inject failure"
      sub={`${failures.length} classes`}
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
        <div className="failure-grid">
          {failures.map((f) => (
            <button
              key={f.id}
              className={"chip" + (selected === f.id ? " active" : "")}
              onClick={() => !disabled && onSelect(f.id)}
              disabled={disabled}
              title={f.description}
            >
              {f.id}
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}
