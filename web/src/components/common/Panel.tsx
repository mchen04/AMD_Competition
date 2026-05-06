import type { ReactNode } from "react";

interface PanelProps {
  title?: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
  className?: string;
}

export function Panel({ title, sub, actions, children, flush, className }: PanelProps) {
  const cls = `panel${className ? " " + className : ""}`;
  return (
    <div className={cls}>
      {(title || sub || actions) && (
        <div className="panel-head">
          {title && <div className="panel-title">{title}</div>}
          {sub && <div className="panel-sub">{sub}</div>}
          {actions && <div className="panel-actions">{actions}</div>}
        </div>
      )}
      {flush ? children : <div className="panel-body">{children}</div>}
    </div>
  );
}
