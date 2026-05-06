import { useEffect, useRef } from "react";
import type { SSEEvent } from "../../api/types";

interface Props {
  events: SSEEvent[];
  error: string | null;
}

export function LogViewer({ events, error }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events]);
  const lines = renderLines(events, error);
  return (
    <div ref={ref} className="logstream">
      {lines.length === 0 && <div className="muted">— hit "run" to execute the heal loop —</div>}
      {lines.map((l, i) => (
        <div key={i} className="log-line">
          <span className="log-time">{l.time}</span>
          <span className={"log-tag " + l.tag}>{l.tag}</span>
          <span className="log-msg">{l.message}</span>
        </div>
      ))}
    </div>
  );
}

interface Line {
  time: string;
  tag: string;
  message: string;
}

function renderLines(events: SSEEvent[], error: string | null): Line[] {
  const out: Line[] = [];
  for (const ev of events) {
    const time = ev.ts ? ev.ts.slice(11, 23) : "";
    switch (ev.event) {
      case "run.queued":
        out.push({
          time,
          tag: "cmd",
          message: `POST /api/run scenario=${(ev.data.scenario as string) ?? "(none)"}`,
        });
        break;
      case "inject.applied": {
        const scenario = (ev.data as { scenario?: string }).scenario ?? "(unknown)";
        out.push({ time, tag: "info", message: `injected scenario=${scenario}` });
        break;
      }
      case "check.started":
        out.push({ time, tag: "info", message: "→ check: probes running" });
        break;
      case "diagnosis.started":
        out.push({
          time,
          tag: "info",
          message: `→ diagnose: provider=${(ev.data as { provider?: string }).provider ?? ""}`,
        });
        break;
      case "diagnosis.completed":
        out.push({ time, tag: "warn", message: "diagnosis complete" });
        break;
      case "repair.applied": {
        const repair = (ev.data as { repair?: { recipe_id?: string; changed_paths?: string[]; reason?: string } })
          .repair;
        out.push({
          time,
          tag: "info",
          message: `→ heal: ${repair?.recipe_id ?? "—"}${repair?.changed_paths?.length ? ` · ${repair.changed_paths.join(", ")}` : ""}`,
        });
        if (repair?.reason) out.push({ time, tag: "info", message: repair.reason });
        break;
      }
      case "repair.rejected": {
        const repair = (ev.data as { repair?: { recipe_id?: string; reason?: string } }).repair;
        out.push({ time, tag: "err", message: `× rejected ${repair?.recipe_id ?? "—"}: ${repair?.reason ?? ""}` });
        break;
      }
      case "verification.completed": {
        const healthy = Boolean((ev.data as { healthy?: boolean }).healthy);
        out.push({
          time,
          tag: healthy ? "ok" : "err",
          message: healthy ? "✓ verification healthy" : "× verification failed",
        });
        break;
      }
      case "report.written": {
        const path = (ev.data as { path?: string }).path ?? "";
        out.push({ time, tag: "ok", message: `✓ wrote ${path}` });
        break;
      }
      case "done":
        out.push({ time, tag: "ok", message: "loop complete" });
        break;
      case "error":
        out.push({
          time,
          tag: "err",
          message: `× ${(ev.data as { error?: string }).error ?? "error"}`,
        });
        break;
      default:
        break;
    }
  }
  if (error) out.push({ time: "", tag: "err", message: `× ${error}` });
  return out;
}
