import type { JSX } from "react";

export function YamlView({ yaml }: { yaml: string }) {
  const lines: JSX.Element[] = [];
  yaml.split("\n").forEach((rawLine, i) => {
    if (/^\s*#/.test(rawLine)) {
      lines.push(
        <div key={i}>
          <span className="yc">{rawLine}</span>
        </div>,
      );
      return;
    }
    const m = rawLine.match(/^(\s*-?\s*)([\w\-.]+)(\s*:)(.*)$/);
    if (m) {
      const [, indent, key, colon, rest] = m;
      const trimmed = rest.trim();
      let val: JSX.Element | null = null;
      if (trimmed === "") val = null;
      else if (/^[0-9]+(\.[0-9]+)?$/.test(trimmed)) val = <span className="yn">{rest}</span>;
      else if (/^(true|false|null)$/i.test(trimmed)) val = <span className="yh">{rest}</span>;
      else val = <span className="yv">{rest}</span>;
      lines.push(
        <div key={i}>
          {indent}
          <span className="yk">{key}</span>
          <span>{colon}</span>
          {val}
        </div>,
      );
      return;
    }
    const li = rawLine.match(/^(\s*-\s*)(.*)$/);
    if (li) {
      const [, indent, val] = li;
      lines.push(
        <div key={i}>
          {indent}
          <span className="ys">{val}</span>
        </div>,
      );
      return;
    }
    lines.push(<div key={i}>{rawLine || " "}</div>);
  });
  return <>{lines}</>;
}
