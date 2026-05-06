import { useState } from "react";
import { useApp } from "../state/AppContext";
import { RiskPill } from "../components/common/Pill";

export function RecipesPage() {
  const { snapshot } = useApp();
  const [filter, setFilter] = useState<"all" | "none" | "low" | "med" | "high">("all");
  const [query, setQuery] = useState("");
  if (!snapshot) return null;
  const recipes = snapshot.recipes;
  const filtered = recipes.filter((r) => {
    if (filter !== "all" && r.risk !== filter) return false;
    if (query && !(r.id.includes(query) || r.desc.toLowerCase().includes(query.toLowerCase()))) return false;
    return true;
  });
  const counts = {
    all: recipes.length,
    none: recipes.filter((r) => r.risk === "none").length,
    low: recipes.filter((r) => r.risk === "low").length,
    med: recipes.filter((r) => r.risk === "med").length,
    high: recipes.filter((r) => r.risk === "high").length,
  };
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Recipes</h1>
          <p className="page-sub">
            {recipes.length} deterministic, safety-gated repair recipes.
          </p>
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter…"
          style={{
            background: "var(--bg-2)",
            border: "1px solid var(--line)",
            color: "var(--text-0)",
            borderRadius: "var(--r)",
            padding: "5px 10px",
            fontSize: 12,
            width: 220,
            fontFamily: "var(--mono)",
          }}
        />
      </div>
      <div className="tabs" style={{ flexShrink: 0 }}>
        {(["all", "none", "low", "med", "high"] as const).map((k) => (
          <div key={k} className={"tab" + (filter === k ? " active" : "")} onClick={() => setFilter(k)}>
            {k === "all" ? "All" : k === "none" ? "No-risk" : k === "low" ? "Low" : k === "med" ? "Medium" : "High"}
            <span className="tab-count">{counts[k]}</span>
          </div>
        ))}
      </div>
      <div className="page-body">
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="grid recipes-grid">
            {filtered.map((r) => (
              <div className="recipe" key={r.id}>
                <div className="recipe-head">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="recipe-id">{r.id}</div>
                    <div className="recipe-desc">{r.desc}</div>
                  </div>
                  <RiskPill risk={r.risk} />
                </div>
                <div className="recipe-tags">
                  {r.classes.slice(0, 3).map((c) => (
                    <span key={c} className="pill muted mono">
                      {c}
                    </span>
                  ))}
                  {r.classes.length > 3 && <span className="pill muted mono">+{r.classes.length - 3}</span>}
                </div>
                {r.editPath && (
                  <div className="diff" style={{ marginTop: "auto" }}>
                    <div className="diff-path">{r.editPath}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
