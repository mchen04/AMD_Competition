import type { SSEEvent, SSEEventName } from "./types";

const TRACKED_EVENTS: SSEEventName[] = [
  "run.queued",
  "check.started",
  "check.failed",
  "inject.applied",
  "diagnosis.started",
  "diagnosis.completed",
  "repair.applied",
  "repair.rejected",
  "verification.completed",
  "report.written",
  "done",
  "error",
];

export type SSEHandler = (event: SSEEvent) => void;

export function subscribeRun(runId: string, onEvent: SSEHandler): () => void {
  const url = `/api/run/${encodeURIComponent(runId)}/events`;
  const source = new EventSource(url);
  for (const name of TRACKED_EVENTS) {
    source.addEventListener(name, (raw) => {
      try {
        const data = JSON.parse((raw as MessageEvent).data) as SSEEvent;
        onEvent(data);
      } catch {
        /* ignore malformed events */
      }
    });
  }
  return () => source.close();
}
