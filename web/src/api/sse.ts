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

const SUPERVISOR_EVENTS: SSEEventName[] = [
  "supervisor.started",
  "supervisor.stopped",
  "cycle.started",
  "cycle.healthy",
  "cycle.skipped",
  "cycle.unhealthy",
  "cycle.completed",
  "cycle.error",
];

export type SSEHandler = (event: SSEEvent) => void;

function attach(source: EventSource, names: SSEEventName[], onEvent: SSEHandler): void {
  for (const name of names) {
    source.addEventListener(name, (raw) => {
      try {
        const data = JSON.parse((raw as MessageEvent).data) as SSEEvent;
        onEvent(data);
      } catch {
        /* ignore malformed events */
      }
    });
  }
}

export function subscribeRun(runId: string, onEvent: SSEHandler): () => void {
  const url = `/api/run/${encodeURIComponent(runId)}/events`;
  const source = new EventSource(url);
  attach(source, TRACKED_EVENTS, onEvent);
  return () => source.close();
}

export function subscribeSupervisor(runId: string, onEvent: SSEHandler): () => void {
  const url = `/api/supervise/${encodeURIComponent(runId)}/events`;
  const source = new EventSource(url);
  attach(source, SUPERVISOR_EVENTS, onEvent);
  return () => source.close();
}
