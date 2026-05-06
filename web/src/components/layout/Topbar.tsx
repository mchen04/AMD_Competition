import { useApp } from "../../state/AppContext";
import { ConfigPicker } from "./ConfigPicker";
import { Dropdown } from "../common/Dropdown";
import { Icon } from "../common/Icon";
import type { Route } from "../../router";

interface TopbarProps {
  route: Route;
  onCheck: () => void;
  onHeal: () => void;
  onReset: () => void;
}

const ROUTE_LABEL: Record<Route, string> = {
  overview: "Overview",
  loop: "Healing Loop",
  providers: "Providers",
  recipes: "Recipes",
  failures: "Failures",
  incidents: "Incidents",
  config: "Config",
};

export function Topbar({ route, onCheck, onHeal, onReset }: TopbarProps) {
  const { snapshot, activeProviderId, setActiveProviderId, diagnosisProvider, setDiagnosisProvider, bootStatus } =
    useApp();

  const providers = snapshot?.providers ?? [];
  const diagnosisProviders = snapshot?.diagnosis_providers ?? ["rules"];

  return (
    <header className="topbar">
      <div className="crumbs">
        <span>RocmDoctor</span>
        <span className="sep">/</span>
        <span className="now">{ROUTE_LABEL[route]}</span>
      </div>
      <div className="topbar-spacer" />
      <ConfigPicker />
      <Dropdown
        triggerIcon="flask"
        triggerLabel={`diagnose: ${diagnosisProvider}`}
        selectedId={diagnosisProvider}
        items={diagnosisProviders.map((p) => ({ id: p, label: p }))}
        onSelect={setDiagnosisProvider}
      />
      <Dropdown
        triggerIcon="server"
        triggerLabel={activeProviderId || "—"}
        selectedId={activeProviderId}
        items={providers.map((p) => ({ id: p.id, label: p.id, meta: p.runtime, iconName: "server" }))}
        onSelect={(id) => void setActiveProviderId(id)}
      />
      {bootStatus === "live" && (
        <span className="pill ok" style={{ marginRight: 4 }}>
          <span className="dot" />
          live
        </span>
      )}
      <button className="topbar-btn" onClick={onCheck}>
        <Icon name="refresh" size={12} /> check
      </button>
      <button className="topbar-btn primary" onClick={onHeal}>
        <Icon name="bolt" size={12} /> heal
      </button>
      <button className="topbar-btn" onClick={onReset} title="restore working config from template">
        <Icon name="x" size={12} /> reset
      </button>
    </header>
  );
}
