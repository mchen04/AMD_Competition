import { Panel } from "../../components/common/Panel";
import type { FailureDTO, RecipeDTO } from "../../api/types";

interface Props {
  failure: FailureDTO | null;
  recipe: RecipeDTO | null;
}

export function RecipePlan({ failure, recipe }: Props) {
  return (
    <Panel
      title="Recipe plan"
      sub={failure ? `${failure.candidates.length} candidate${failure.candidates.length === 1 ? "" : "s"}` : "—"}
      flush
    >
      <div
        className="panel-body"
        style={{ display: "flex", flexDirection: "column", gap: 8, overflow: "auto" }}
      >
        {failure ? (
          <>
            <div>
              <div className="kv-label">diagnosis</div>
              <div className="kv-val mono">
                {failure.id} <span className="muted">— {failure.description}</span>
              </div>
            </div>
            <div>
              <div className="kv-label">candidates (ordered)</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                {failure.candidates.map((rid, idx) => (
                  <span key={rid} className={"pill " + (idx === 0 ? "info" : "muted")}>
                    {idx === 0 && <span className="dot" />}
                    {rid}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="kv-label">chosen</div>
              <div className="kv-val mono" style={{ color: "var(--accent)" }}>
                {failure.expectedRecipe ?? "—"}
              </div>
            </div>
            {recipe?.editPath && (
              <div>
                <div className="kv-label">config edit preview</div>
                <div className="diff">
                  <div className="diff-path">{recipe.editPath}</div>
                  <div className="diff-line del">- {String(recipe.editFrom ?? "")}</div>
                  <div className="diff-line add">+ {String(recipe.editTo ?? "")}</div>
                </div>
              </div>
            )}
            {recipe && (
              <div>
                <div className="kv-label">verify</div>
                <div className="mono" style={{ fontSize: 11.5, color: "var(--text-1)" }}>
                  {recipe.verifies.join(", ")}
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="muted">— select a failure to see the recipe plan —</div>
        )}
      </div>
    </Panel>
  );
}
