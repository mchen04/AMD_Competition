import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../../api/client";
import { subscribeSupervisor } from "../../api/sse";
import type { SSEEvent } from "../../api/types";
import { Panel } from "../common/Panel";
import { Icon } from "../common/Icon";

interface SupervisorPanelProps {
  defaultProvider: string;
  onCycle?: () => void;
}

interface RunningRun {
  runId: string;
  startedAt: number;
}

export function SupervisorPanel({ defaultProvider, onCycle }: SupervisorPanelProps) {
  const [interval, setInterval] = useState<number>(30);
  const [untilPass, setUntilPass] = useState<boolean>(false);
  const [run, setRun] = useState<RunningRun | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const closeRef = useRef<(() => void) | null>(null);

  const tearDown = useCallback(() => {
    if (closeRef.current) {
      closeRef.current();
      closeRef.current = null;
    }
  }, []);

  useEffect(() => () => tearDown(), [tearDown]);

  const start = async () => {
    setBusy(true);
    setError(null);
    setEvents([]);
    try {
      const result = await api.superviseStart({
        interval_seconds: interval,
        until_pass: untilPass,
        provider_name: defaultProvider,
      });
      setRun({ runId: result.run_id, startedAt: Date.now() });
      const close = subscribeSupervisor(result.run_id, (event) => {
        setEvents((prior) => [...prior.slice(-99), event]);
        if (event.event === "cycle.completed") onCycle?.();
        if (event.event === "supervisor.stopped") setRun(null);
      });
      closeRef.current = close;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "start failed");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!run) return;
    setBusy(true);
    try {
      await api.superviseStop(run.runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "stop failed");
    } finally {
      setBusy(false);
    }
  };

  const cycleEvents = events.filter((e) => e.event.startsWith("cycle.")).slice(-12);
  const lastCycle = cycleEvents[cycleEvents.length - 1];

  return (
    <Panel title="Supervisor" sub={run ? `running · ${cycleEvents.length} cycles` : "idle"} flush>
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <span className="muted">interval (s)</span>
            <input
              type="number"
              min={1}
              max={3600}
              value={interval}
              disabled={!!run || busy}
              onChange={(e) => setInterval(Math.max(1, Number(e.target.value) || 1))}
              style={{
                width: 70,
                background: "var(--bg-2)",
                color: "var(--text-1)",
                border: "1px solid var(--line)",
                borderRadius: 4,
                padding: "3px 6px",
                fontFamily: "var(--mono)",
                fontSize: 12,
              }}
            />
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
            <input
              type="checkbox"
              checked={untilPass}
              disabled={!!run || busy}
              onChange={(e) => setUntilPass(e.target.checked)}
            />
            <span className="muted">until pass</span>
          </label>
          <span style={{ flex: 1 }} />
          {!run ? (
            <button className="btn primary" onClick={start} disabled={busy}>
              <Icon name="play" size={12} /> start supervisor
            </button>
          ) : (
            <button className="btn" onClick={stop} disabled={busy}>
              <Icon name="x" size={12} /> stop
            </button>
          )}
        </div>
        {error && (
          <div style={{ color: "var(--err)", fontSize: 12, fontFamily: "var(--mono)" }}>{error}</div>
        )}
        {lastCycle && (
          <div className="muted mono" style={{ fontSize: 11 }}>
            last: {lastCycle.event} · {new Date(lastCycle.ts).toLocaleTimeString()}
          </div>
        )}
        <div className="code" style={{ maxHeight: 200, overflow: "auto", fontSize: 11 }}>
          {events.length === 0 && <div className="muted">no events yet</div>}
          {events.slice(-40).map((e) => (
            <div key={`${e.run_id}-${e.seq}`}>
              <span style={{ color: tone(e.event) }}>{e.event}</span>
              {summary(e)}
            </div>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function tone(event: string): string {
  if (event.includes("healthy")) return "var(--ok)";
  if (event.includes("error") || event.includes("unhealthy")) return "var(--err)";
  if (event.includes("skipped")) return "var(--warn)";
  return "var(--accent)";
}

function summary(event: SSEEvent): string {
  const data = (event.data ?? {}) as Record<string, unknown>;
  if (event.event === "cycle.healthy") {
    return ` · iter ${data.iteration ?? "?"} · recovered=${String(data.recovered ?? false)}`;
  }
  if (event.event === "cycle.skipped") {
    const reason = typeof data.reason === "string" ? data.reason.slice(0, 80) : "";
    return ` · iter ${data.iteration ?? "?"} · ${reason}`;
  }
  if (event.event === "cycle.unhealthy") {
    const reason = typeof data.reason === "string" ? data.reason.slice(0, 80) : "";
    return ` · iter ${data.iteration ?? "?"} · ${reason}`;
  }
  if (event.event === "cycle.completed") {
    return ` · iter ${data.iteration ?? "?"} · next in ${Math.round(Number(data.next_check_in_seconds ?? 0))}s`;
  }
  if (event.event === "supervisor.started") {
    return ` · interval=${data.interval_seconds}s until_pass=${String(data.until_pass ?? false)}`;
  }
  return "";
}
