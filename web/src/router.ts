import { useEffect, useState } from "react";

export type Route =
  | "overview"
  | "loop"
  | "providers"
  | "recipes"
  | "failures"
  | "incidents"
  | "config";

export const ROUTES: Route[] = [
  "overview",
  "loop",
  "providers",
  "recipes",
  "failures",
  "incidents",
  "config",
];

function readHash(): Route {
  const fromHash = window.location.hash.replace("#", "");
  return (ROUTES as string[]).includes(fromHash) ? (fromHash as Route) : "overview";
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
