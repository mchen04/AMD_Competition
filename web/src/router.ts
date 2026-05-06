import { useEffect, useState } from "react";

export type Route =
  | "overview"
  | "pipeline"
  | "providers"
  | "recipes"
  | "failures"
  | "incidents"
  | "config";

export const ROUTES: Route[] = [
  "overview",
  "pipeline",
  "providers",
  "recipes",
  "failures",
  "incidents",
  "config",
];

const LEGACY_ROUTES: Record<string, Route> = {
  loop: "pipeline",
};

function readHash(): Route {
  const fromHash = window.location.hash.replace("#", "");
  if ((ROUTES as string[]).includes(fromHash)) return fromHash as Route;
  if (fromHash in LEGACY_ROUTES) return LEGACY_ROUTES[fromHash];
  return "overview";
}

export function useRoute(): [Route, (r: Route) => void] {
  const [route, setRouteState] = useState<Route>(readHash());

  useEffect(() => {
    const onHash = () => setRouteState(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (window.location.hash !== "#" + route) {
      window.history.replaceState(null, "", "#" + route);
    }
  }, [route]);

  return [route, setRouteState];
}
