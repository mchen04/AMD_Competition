import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

export interface DropdownItem {
  id: string;
  label: ReactNode;
  meta?: string;
  iconName?: string;
}

interface DropdownProps {
  triggerIcon: string;
  triggerLabel: ReactNode;
  items: DropdownItem[];
  selectedId: string;
  onSelect: (id: string) => void;
}

export function Dropdown({ triggerIcon, triggerLabel, items, selectedId, onSelect }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!ref.current) return;
      if (ref.current.contains(e.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="provider-pill" onClick={() => setOpen((o) => !o)}>
        <Icon name={triggerIcon} size={11} />
        <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{triggerLabel}</span>
        <span className="caret">
          <Icon name="chev" size={11} />
        </span>
      </button>
      {open && (
        <div className="dd-menu">
          {items.map((item) => (
            <div
              key={item.id}
              className={"dd-item" + (item.id === selectedId ? " is-current" : "")}
              onClick={() => {
                onSelect(item.id);
                setOpen(false);
              }}
            >
              <span>
                <Icon name={item.iconName ?? triggerIcon} size={13} />
              </span>
              <span>{item.label}</span>
              {item.meta && <span className="meta">{item.meta}</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
