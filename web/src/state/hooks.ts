import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import { subscribeRun } from "../api/sse";
import type { RunResultResponse, SSEEvent } from "../api/types";
import { useApp } from "./AppContext";

export interface RunController {
  runId: string | null;
  events: SSEEvent[];
  result: RunResultResponse | null;
  running: boolean;
  error: string | null;
  start: (scenario: string | null) => Promise<void>;
  reset: () => void;
}

export function useRun(): RunController {
  const { diagnosisProvider, refresh } = useApp();
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [result, setResult] = useState<RunResultResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => () => cleanupRef.current?.(), []);

  const reset = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    setRunId(null);
    setEvents([]);
    setResult(null);
    setRunning(false);
    setError(null);
  }, []);

  const start = useCallback(
    async (scenario: string | null) => {
      reset();
      setRunning(true);
      try {
        const started = await api.startRun(scenario, diagnosisProvider || null);
        setRunId(started.run_id);

        const cleanup = subscribeRun(started.run_id, (event) => {
          setEvents((prev) => [...prev, event]);
          if (event.event === "done" || event.event === "error") {
            cleanup();
            cleanupRef.current = null;
            void api
              .runResult(started.run_id)
              .then((res) => setResult(res))
              .catch((err) => setError(err instanceof Error ? err.message : "fetch result failed"))
              .finally(() => {
                setRunning(false);
                void refresh();
              });
          }
        });
        cleanupRef.current = cleanup;
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "run failed";
        setError(msg);
        setRunning(false);
      }
    },
    [diagnosisProvider, refresh, reset],
  );

  return useMemo(
    () => ({ runId, events, result, running, error, start, reset }),
    [runId, events, result, running, error, start, reset],
  );
}
