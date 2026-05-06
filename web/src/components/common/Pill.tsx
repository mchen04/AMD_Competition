interface StatusPillProps {
  status: string;
}

export function StatusPill({ status }: StatusPillProps) {
  const map: Record<string, { c: string; t: string }> = {
    healthy: { c: "ok", t: "healthy" },
    degraded: { c: "warn", t: "degraded" },
    failing: { c: "err", t: "failing" },
    healing: { c: "info", t: "healing" },
    offline: { c: "muted", t: "offline" },
  };
  const s = map[status] ?? { c: "muted", t: status };
  return (
    <span className={"pill " + s.c}>
      <span className="dot" />
      {s.t}
    </span>
  );
}

interface RiskPillProps {
  risk: string;
}

export function RiskPill({ risk }: RiskPillProps) {
  const c = risk === "none" ? "muted" : risk === "low" ? "ok" : risk === "med" ? "warn" : "err";
  return <span className={"pill " + c}>{risk}</span>;
}
