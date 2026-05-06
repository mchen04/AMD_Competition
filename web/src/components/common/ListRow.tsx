import type { ReactNode } from "react";
import { Icon } from "./Icon";

interface ListRowProps {
  iconName?: string;
  primary: ReactNode;
  secondary?: ReactNode;
  trailing?: ReactNode;
  selected?: boolean;
  onClick?: () => void;
}

export function ListRow({ iconName, primary, secondary, trailing, selected, onClick }: ListRowProps) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 12px",
        borderBottom: "1px solid var(--line-soft)",
        cursor: onClick ? "pointer" : "default",
        background: selected ? "var(--bg-3)" : "transparent",
        boxShadow: selected ? "inset 2px 0 0 var(--accent)" : "none",
      }}
    >
      {iconName && <Icon name={iconName} size={13} color={selected ? "var(--accent)" : "var(--text-2)"} />}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="mono" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {primary}
        </div>
        {secondary && (
          <div className="mono" style={{ fontSize: 10.5, color: "var(--text-2)" }}>
            {secondary}
          </div>
        )}
      </div>
      {trailing}
    </div>
  );
}
