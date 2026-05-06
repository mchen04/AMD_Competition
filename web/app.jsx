/* ROCm Doctor Console — App shell */

const { useState: useAppState, useEffect: useAppEffect } = React;

const App = () => {
  const [route, setRoute] = useAppState("overview");
  const [providerId, setProviderId] = useAppState(window.PROVIDERS[0].id);
  const [bootStatus, setBootStatus] = useAppState("loading"); // "loading" | "live" | "static"
  const [bootError, setBootError] = useAppState(null);
  const [refreshKey, setRefreshKey] = useAppState(0);

  const [presetFailure, setPresetFailure] = useAppState(null);
  const [presetRunKey, setPresetRunKey] = useAppState(0);

  const refreshSnapshot = async () => {
    const r = await window.loadDashboardData();
    if (r.ok) {
      setProviderId(window.ACTIVE_PROVIDER || window.PROVIDERS[0].id);
      setBootStatus("live");
      setRefreshKey(k => k + 1);
    }
    return r;
  };

  useAppEffect(() => {
    (async () => {
      const r = await window.loadDashboardData();
      if (r.ok) {
        setProviderId(window.ACTIVE_PROVIDER || window.PROVIDERS[0].id);
        setBootStatus("live");
      } else {
        setBootStatus("static");
        setBootError(r.error && r.error.message);
      }
    })();
  }, []);

  const goToLoop = (failureId) => {
    setPresetFailure(failureId);
    setPresetRunKey(k => k + 1);
    setRoute("loop");
  };

  const openHealRun = (incident) => {
    const fid = incident.failure || (window.FAILURES[0] && window.FAILURES[0].id);
    goToLoop(fid);
  };

  useAppEffect(() => {
    const fromHash = window.location.hash.replace("#", "");
    if (fromHash) setRoute(fromHash);
    const onHash = () => {
      const r = window.location.hash.replace("#", "");
      if (r) setRoute(r);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useAppEffect(() => {
    if (window.location.hash !== "#" + route) {
      window.history.replaceState(null, "", "#" + route);
    }
  }, [route]);

  const onTopbarCheck = async () => {
    if (window.API_AVAILABLE) {
      try {
        await window.apiCheck();
        await refreshSnapshot();
      } catch (_) { /* surface via banner if it persists */ }
    }
    const first = (window.FAILURES.find(f => f.scenario) || window.FAILURES[0]);
    goToLoop(first ? first.id : "wrong_endpoint_port");
  };
  const onTopbarSelfHeal = () => {
    const first = (window.FAILURES.find(f => f.scenario) || window.FAILURES[0]);
    goToLoop(first ? first.id : "wrong_endpoint_port");
  };
  const onTopbarReset = async () => {
    if (!window.API_AVAILABLE) return;
    try { await window.apiReset(); } catch (_) {}
    await refreshSnapshot();
  };
  const onProviderSwitch = async (pid) => {
    setProviderId(pid);
    if (!window.API_AVAILABLE) return;
    try {
      await window.apiSetActive(pid);
      await refreshSnapshot();
    } catch (_) { /* keep local UI state */ }
  };

  if (bootStatus === "loading") {
    return (
      <div style={{
        height: "100vh", display: "grid", placeItems: "center",
        background: "var(--bg-0)", color: "var(--text-2)",
        fontFamily: "var(--mono)", fontSize: 12,
      }}>
        loading dashboard…
      </div>
    );
  }

  let page = null;
  if (route === "overview")       page = <OverviewPage  providerId={providerId} setRoute={setRoute} openHealRun={openHealRun} refreshKey={refreshKey} />;
  else if (route === "loop")      page = <LoopPage      providerId={providerId} presetFailure={presetFailure} presetRunKey={presetRunKey} onComplete={refreshSnapshot} />;
  else if (route === "providers") page = <ProvidersPage providerId={providerId} setProviderId={onProviderSwitch} refreshKey={refreshKey} />;
  else if (route === "recipes")   page = <RecipesPage   refreshKey={refreshKey} />;
  else if (route === "failures")  page = <FailuresPage  goToLoop={goToLoop} refreshKey={refreshKey} />;
  else if (route === "incidents") page = <IncidentsPage openHealRun={openHealRun} refreshKey={refreshKey} />;
  else if (route === "config")    page = <ConfigPage    refreshKey={refreshKey} />;
  else page = <OverviewPage providerId={providerId} setRoute={setRoute} openHealRun={openHealRun} refreshKey={refreshKey} />;

  return (
    <div className="app">
      <Sidebar
        route={route}
        setRoute={setRoute}
        providerCount={window.PROVIDERS.length}
        incidentCount={window.INCIDENTS.length}
        recipeCount={window.RECIPES.length}
      />
      <Topbar
        route={route}
        providerId={providerId}
        setProviderId={onProviderSwitch}
        onCheck={onTopbarCheck}
        onSelfHeal={onTopbarSelfHeal}
        onReset={onTopbarReset}
        bootStatus={bootStatus}
      />
      <main className="main">
        {bootStatus === "static" && (
          <div style={{
            padding: "8px 14px",
            background: "var(--warn-soft)",
            color: "var(--warn)",
            borderBottom: "1px solid var(--line)",
            fontFamily: "var(--mono)",
            fontSize: 11.5,
          }}>
            backend unreachable — running in static-prototype mode{bootError ? ` (${bootError})` : ""}
          </div>
        )}
        {page}
      </main>
    </div>
  );
};

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
