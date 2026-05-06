import type { ReactNode } from "react";

interface StatProps {
  label: string;
  value: ReactNode;
  foot?: ReactNode;
  footTone?: string;
  mono?: boolean;
}

export function Stat({ label, value, foot, footTone, mono }: StatProps) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={"stat-value" + (mono ? " mono" : "")}>{value}</div>
      {foot && <div className={"stat-foot " + (footTone || "")}>{foot}</div>}
    </div>
  );
}
