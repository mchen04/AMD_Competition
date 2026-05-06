import { Icon } from "../common/Icon";
import type { Route } from "../../router";

interface SidebarProps {
  route: Route;
  setRoute: (r: Route) => void;
  providerCount: number;
  recipeCount: number;
  incidentCount: number;
}

interface NavEntry {
  icon: string;
  label: string;
  route: Route;
  count?: number;
  group: "Operate" | "Library" | "System";
}

export function Sidebar({ route, setRoute, providerCount, recipeCount, incidentCount }: SidebarProps) {
  const items: NavEntry[] = [
    { icon: "grid", label: "Overview", route: "overview", group: "Operate" },
    { icon: "activity", label: "Pipeline", route: "pipeline", group: "Operate" },
    { icon: "server", label: "Providers", route: "providers", count: providerCount, group: "Operate" },
    { icon: "wrench", label: "Recipes", route: "recipes", count: recipeCount, group: "Library" },
    { icon: "flask", label: "Failures", route: "failures", group: "Library" },
    { icon: "file", label: "Incidents", route: "incidents", count: incidentCount, group: "Library" },
    { icon: "settings", label: "Config", route: "config", group: "System" },
  ];
  const groups: SidebarProps["route"] extends never ? never : Array<NavEntry["group"]> = [
    "Operate",
    "Library",
    "System",
  ];
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">RD</div>
        <div className="brand-name">
          ROCm Doctor<span className="dim">CI/CD</span>
        </div>
      </div>
      {groups.map((group) => (
        <div key={group} className="nav-section">
          <div className="nav-section-label">{group}</div>
          {items
            .filter((it) => it.group === group)
            .map((it) => (
              <div
                key={it.route}
                className={"nav-item" + (route === it.route ? " active" : "")}
                onClick={() => setRoute(it.route)}
              >
                <span className="ico">
                  <Icon name={it.icon} size={15} />
                </span>
                <span>{it.label}</span>
                {it.count != null && <span className="count">{it.count}</span>}
              </div>
            ))}
        </div>
      ))}
      <div className="sidebar-foot">
        <span className="pulse" />
        <span>monitor running</span>
      </div>
    </aside>
  );
}
