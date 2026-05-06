import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { BaselineState } from "../../api/types";
import { Panel } from "../common/Panel";
import { Icon } from "../common/Icon";

interface BaselineStripProps {
  refreshKey: number;
  onChange?: () => void;
}

export function BaselineStrip({ refreshKey, onChange }: BaselineStripProps) {
  const [state, setState] = useState<BaselineState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);

  const reload = useCallback(async () => {
    try {
      const next = await api.baselineDiff();
      setState(next);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "diff failed");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, refreshKey]);

  const totalChanges = useMemo(() => {
    if (!state) return 0;
    return state.diff.changed.length + state.diff.added.length + state.diff.removed.length;
  }, [state]);

  const pinned = state?.pinned ?? false;
  const kindLabel = state?.baseline_kind === "pinned"
    ? `pinned ${formatRelative(state?.pinned_at)}`
    : state?.baseline_kind === "last_known_good"
      ? "no pin · using last-known-good"
      : "not pinned";

  const onPin = async () => {
    setBusy(true);
    try {
      await api.baselinePin();
      await reload();
      onChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "pin failed");
    } finally {
      setBusy(false);
    }
  };

  const onUnpin = async () => {
    setBusy(true);
    try {
      await api.baselineUnpin();
      await reload();
      onChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "unpin failed");
    } finally {
      setBusy(false);
    }
  };

  const onRestore = async () => {
    setBusy(true);
    try {
      await api.baselineRestore();
      await reload();
      onChange?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "restore failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Baseline"
      sub={kindLabel}
      flush
    >
      <div style={{ padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <span className={"pill " + (pinned ? "ok" : "")} style={{ marginRight: 4 }}>
            <span className="dot" />
            {pinned ? "baseline pinned" : "baseline not pinned"}
          </span>
          <span className="muted mono" style={{ fontSize: 12 }}>
            diff: {totalChanges} {totalChanges === 1 ? "path" : "paths"}
          </span>
          <span style={{ flex: 1 }} />
          {!pinned && (
            <button className="btn primary" disabled={busy} onClick={onPin}>
              <Icon name="bolt" size={12} /> pin current
            </button>
          )}
          {pinned && (
            <button className="btn" disabled={busy} onClick={onRestore}>
              <Icon name="refresh" size={12} /> restore
            </button>
          )}
          {pinned && (
            <button className="btn" disabled={busy} onClick={onUnpin}>
              <Icon name="x" size={12} /> unpin
            </button>
          )}
          {totalChanges > 0 && (
            <button className="btn" onClick={() => setShowDiff((s) => !s)}>
              <Icon name="file" size={12} /> {showDiff ? "hide diff" : "view diff"}
            </button>
          )}
        </div>
        {error && (
          <div style={{ color: "var(--err)", fontSize: 12, fontFamily: "var(--mono)" }}>{error}</div>
        )}
        {showDiff && state && (
          <div className="code" style={{ maxHeight: 220, overflow: "auto", fontSize: 11 }}>
            {state.diff.changed.length === 0 &&
              state.diff.added.length === 0 &&
              state.diff.removed.length === 0 && <div className="muted">no diff</div>}
            {state.diff.changed.map((entry) => (
              <div key={`c:${entry.path}`}>
                <span style={{ color: "var(--accent)" }}>~</span> {entry.path}: {format(entry.before)} →{" "}
                {format(entry.after)}
              </div>
            ))}
            {state.diff.added.map((entry) => (
              <div key={`a:${entry.path}`}>
                <span style={{ color: "var(--ok)" }}>+</span> {entry.path}: {format(entry.after)}
              </div>
            ))}
            {state.diff.removed.map((entry) => (
              <div key={`r:${entry.path}`}>
                <span style={{ color: "var(--err)" }}>-</span> {entry.path}: {format(entry.before)}
              </div>
            ))}
          </div>
        )}
      </div>
    </Panel>
  );
}

function format(value: unknown): string {
  if (value === null) return "null";
  if (value === undefined) return "—";
  if (typeof value === "string") return JSON.stringify(value);
  return String(value);
}

function formatRelative(ts: string | null | undefined): string {
  if (!ts) return "—";
  const t = Date.parse(ts);
  if (Number.isNaN(t)) return ts;
  const delta = Date.now() - t;
  if (delta < 60_000) return "just now";
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`;
  return `${Math.round(delta / 86_400_000)}d ago`;
}
