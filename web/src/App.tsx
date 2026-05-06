import { useCallback, useState } from "react";
import { AppProvider, useApp } from "./state/AppContext";
import { Sidebar } from "./components/layout/Sidebar";
import { Topbar } from "./components/layout/Topbar";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { ROUTES, useRoute } from "./router";
import type { Route } from "./router";
import { OverviewPage } from "./pages/Overview";
import { LoopPage } from "./pages/Loop";
import { ProvidersPage } from "./pages/Providers";
import { RecipesPage } from "./pages/Recipes";
import { FailuresPage } from "./pages/Failures";
import { IncidentsPage } from "./pages/Incidents";
import { ConfigPage } from "./pages/Config";
import { api } from "./api/client";

function Shell() {
  const { snapshot, bootStatus, bootError, refresh } = useApp();
  const [route, setRoute] = useRoute();
  const [loopPreset, setLoopPreset] = useState<{ failureId: string; runKey: number } | null>(null);

  const goToLoop = useCallback(
    (failureId: string) => {
      setLoopPreset({ failureId, runKey: Date.now() });
      setRoute("loop");
    },
    [setRoute],
  );

  const onCheck = useCallback(async () => {
    try {
      await api.check();
      await refresh();
    } catch {
      /* surfaced inline on relevant pages */
    }
  }, [refresh]);

  const onHeal = useCallback(() => {
    const first = snapshot?.failures.find((f) => f.scenario) ?? snapshot?.failures[0];
    if (first) goToLoop(first.id);
  }, [snapshot, goToLoop]);

  const onReset = useCallback(async () => {
    try {
      await api.reset();
      await refresh();
    } catch {
      /* same */
    }
  }, [refresh]);

  if (bootStatus === "loading" && !snapshot) {
    return (
      <div
        style={{
          height: "100vh",
          display: "grid",
          placeItems: "center",
          background: "var(--bg-0)",
          color: "var(--text-2)",
          fontFamily: "var(--mono)",
          fontSize: 12,
        }}
      >
        loading dashboard…
      </div>
    );
  }

  let page = null;
  if (!snapshot && bootStatus === "error") {
    page = (
      <div
        style={{
          padding: "16px 24px",
          background: "var(--err-soft, var(--bg-2))",
          color: "var(--err)",
          fontFamily: "var(--mono)",
          fontSize: 12,
        }}
      >
        backend unreachable: {bootError ?? "unknown error"}
      </div>
    );
  } else if (snapshot) {
    if (route === "overview") page = <OverviewPage onOpenLoop={() => setRoute("loop")} />;
    else if (route === "loop")
      page = (
        <LoopPage
          presetFailureId={loopPreset?.failureId ?? null}
          presetRunKey={loopPreset?.runKey ?? 0}
        />
      );
    else if (route === "providers") page = <ProvidersPage />;
    else if (route === "recipes") page = <RecipesPage />;
    else if (route === "failures") page = <FailuresPage onRun={goToLoop} />;
    else if (route === "incidents") page = <IncidentsPage />;
    else if (route === "config") page = <ConfigPage />;
  }

  return (
    <div className="app">
      <Sidebar
        route={route}
        setRoute={(r: Route) => {
          if (ROUTES.includes(r)) setRoute(r);
        }}
        providerCount={snapshot?.providers.length ?? 0}
        recipeCount={snapshot?.recipes.length ?? 0}
        incidentCount={snapshot?.incidents.length ?? 0}
      />
      <Topbar route={route} onCheck={onCheck} onHeal={onHeal} onReset={onReset} />
      <main className="main">
        {bootStatus === "error" && snapshot && (
          <div
            style={{
              padding: "8px 14px",
              background: "var(--warn-soft)",
              color: "var(--warn)",
              borderBottom: "1px solid var(--line)",
              fontFamily: "var(--mono)",
              fontSize: 11.5,
            }}
          >
            backend connection lost{bootError ? ` (${bootError})` : ""}
          </div>
        )}
        {page}
      </main>
    </div>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <AppProvider>
        <Shell />
      </AppProvider>
    </ErrorBoundary>
  );
}
