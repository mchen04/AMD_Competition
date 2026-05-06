/* Page-level views for ROCm Doctor Console — fixed viewport, no page scroll. */

const { useState: usePageState, useEffect: usePageEffect, useRef: usePageRef, useMemo: usePageMemo } = React;

/* ───────────────────────────────────────────────────────────────────── */
/*  Overview                                                              */
/* ───────────────────────────────────────────────────────────────────── */
const OverviewPage = ({ providerId, setRoute, openHealRun, refreshKey }) => {
  const provider = window.PROVIDERS.find(p => p.id === providerId) || window.PROVIDERS[0] || { id: "—", status: "—", runtime: "—" };
  const incidents = window.INCIDENTS || [];
  const healed = incidents.filter(i => i.outcome === "healed").length;
  const learnedFixes = window.STATE_JSON && window.STATE_JSON.learned_fixes ? Object.keys(window.STATE_JSON.learned_fixes).length : incidents.filter(i => i.learned).length;
  const durations = incidents.filter(i => typeof i.durationMs === "number");
  const meanMs = durations.length > 0 ? Math.round(durations.reduce((s, i) => s + i.durationMs, 0) / durations.length) : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-sub">Self-healing harness for OpenAI-compatible model runtimes.</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => setRoute("incidents")}><Icon name="file" size={12}/> incidents</button>
          <button className="btn primary" onClick={() => setRoute("loop")}><Icon name="activity" size={12}/> open loop</button>
        </div>
      </div>

      <div className="grid cols-4" style={{ flexShrink: 0 }}>
        <Stat label="Active provider" value={provider.id} mono
              foot={<><span className="pill ok"><span className="dot"/>{provider.status}</span><span className="muted"> · {provider.runtime}</span></>} />
        <Stat label="Healed runs" value={`${healed}`} foot={incidents.length > 0 ? `of ${incidents.length} incidents` : "no incidents yet"} footTone={healed > 0 ? "ok" : ""} />
        <Stat label="Mean recovery" value={meanMs > 0 ? `${meanMs} ms` : "—"} mono foot={durations.length > 0 ? `across ${durations.length} incidents` : "no timing data"} />
        <Stat label="Learned fixes" value={`${learnedFixes}`} foot="cached in state.json" />
      </div>

      <div className="page-body">
        <div className="grid cols-2-1" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Healing loop · last run"
                 sub="check → diagnose → heal → verify → report"
                 actions={<button className="btn ghost" onClick={() => setRoute("loop")}>open</button>}
                 flush>
            {(() => {
              const last = incidents[0];
              if (!last) {
                return <div className="empty">No runs yet — open the Loop page and inject a failure.</div>;
              }
              const failed = last.outcome === "rolled-back";
              return (
                <>
                  <LoopMini run={{
                    steps: [
                      { name: "check",    state: "done", detail: last.failure || "—" },
                      { name: "diagnose", state: "done", detail: `rules · ${last.failure || "—"}` },
                      { name: "heal",     state: failed ? "fail" : "done", detail: last.recipe || "—" },
                      { name: "verify",   state: failed ? "fail" : "done", detail: failed ? "rolling back" : "all probes ok" },
                      { name: "report",   state: "done", detail: last.id },
                    ],
                  }}/>
                  <div style={{ padding: "8px 14px", borderTop: "1px solid var(--line-soft)", display: "flex", gap: 18, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--text-2)" }}>
                    <span>provider <span style={{ color: "var(--text-0)" }}>{last.provider || "—"}</span></span>
                    <span>recipe <span style={{ color: "var(--accent)" }}>{last.recipe || "—"}</span></span>
                    <span>incident <span style={{ color: "var(--text-0)" }}>{last.id}</span></span>
                    <span>outcome <StatusPill status={last.outcome === "healed" ? "healthy" : last.outcome === "rolled-back" ? "failing" : "degraded"}/></span>
                  </div>
                </>
              );
            })()}
            <div style={{ flex: 1, padding: 12, overflow: "auto" }}>
              <table className="tbl" style={{ background: "transparent" }}>
                <thead><tr><th>id</th><th>provider</th><th>recipe</th><th className="right">outcome</th></tr></thead>
                <tbody>
                  {incidents.slice(0, 5).map(i => (
                    <tr key={i.id} className="row-hover" style={{ cursor: "pointer" }} onClick={() => openHealRun(i)}>
                      <td className="mono">{i.id}</td>
                      <td className="mono dim">{i.provider}</td>
                      <td className="mono"><span style={{ color: "var(--accent)" }}>{i.recipe}</span></td>
                      <td className="right"><StatusPill status={i.outcome === "healed" ? "healthy" : i.outcome === "rolled-back" ? "failing" : "degraded"}/></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Provider fleet" sub={`${window.PROVIDERS.length} configured`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              {window.PROVIDERS.map(p => (
                <div key={p.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderBottom: "1px solid var(--line-soft)" }}>
                  <Icon name="server" size={13} color="var(--text-2)" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 11.5, color: "var(--text-0)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.id}</div>
                    <div className="mono" style={{ fontSize: 10.5, color: "var(--text-2)" }}>{p.runtime} · {p.model}</div>
                  </div>
                  <StatusPill status={p.status} />
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
};

const LoopMini = ({ run }) => (
  <div className="loop">
    {run.steps.map((s, i) => {
      const cls = s.state === "done" ? "is-done" : s.state === "active" ? "is-active" : s.state === "fail" ? "is-fail" : "is-pending";
      return (
        <div key={s.name} className={"loop-step " + cls}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <div className="step-marker">{s.state === "done" ? <Icon name="check" size={11}/> : s.state === "fail" ? <Icon name="x" size={11}/> : i + 1}</div>
            <div>
              <div className="step-idx">step {i + 1}</div>
              <div className="step-name">{s.name}</div>
            </div>
          </div>
          <div className="step-detail">{s.detail}</div>
        </div>
      );
    })}
  </div>
);

/* ───────────────────────────────────────────────────────────────────── */
/*  Healing Loop                                                          */
/* ───────────────────────────────────────────────────────────────────── */
const LoopPage = ({ providerId, presetFailure, presetRunKey, onComplete }) => {
  const initialFailure = (() => {
    if (presetFailure) return presetFailure;
    const firstScenario = (window.FAILURES || []).find(f => f.scenario);
    if (firstScenario) return firstScenario.id;
    return (window.FAILURES && window.FAILURES[0] && window.FAILURES[0].id) || "wrong_endpoint_port";
  })();
  const [failure, setFailure] = usePageState(initialFailure);
  const [steps, setSteps] = usePageState(buildPendingSteps());
  const [logs, setLogs] = usePageState([]);
  const [running, setRunning] = usePageState(false);
  const logEndRef = usePageRef(null);

  function buildPendingSteps() {
    return [
      { name: "check",    state: "pending", detail: "—" },
      { name: "diagnose", state: "pending", detail: "—" },
      { name: "heal",     state: "pending", detail: "—" },
      { name: "verify",   state: "pending", detail: "—" },
      { name: "report",   state: "pending", detail: "—" },
    ];
  }

  usePageEffect(() => {
    if (presetRunKey) runHeal(presetFailure || failure);
  }, [presetRunKey]);

  usePageEffect(() => {
    if (logEndRef.current) logEndRef.current.scrollTop = logEndRef.current.scrollHeight;
  }, [logs]);

  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const tsNow = () => {
    const d = new Date();
    return d.toTimeString().slice(0, 8) + "." + String(d.getMilliseconds()).padStart(3, "0");
  };
  const pushLog = (tag, msg) => setLogs(l => [...l, { ts: tsNow(), tag, msg }]);

  const script = window.buildHealScript(failure, providerId);
  const failureMeta = window.FAILURES.find(f => f.id === failure);

  const setStep = (i, patch) => setSteps(st => st.map((x, idx) => idx === i ? { ...x, ...patch } : x));

  const runHeal = async (failureId) => {
    if (running) return;
    if (window.API_AVAILABLE) {
      return runHealLive(failureId);
    }
    return runHealMock(failureId);
  };

  const runHealLive = async (failureId) => {
    setRunning(true);
    setSteps(buildPendingSteps());
    setLogs([]);

    const failureMeta = (window.FAILURES || []).find(f => f.id === failureId);
    const scenario = failureMeta && failureMeta.scenario;
    pushLog("cmd", `POST /api/run scenario=${scenario || "(none)"}`);
    pushLog("info", `active_model_provider = ${providerId}`);

    setStep(0, { state: "active", detail: "POST /api/run" });
    if (!scenario) {
      pushLog("warn", `failure '${failureId}' is not directly injectable — running self-heal on current state`);
    }

    let data;
    try {
      data = await window.apiRun(scenario);
    } catch (err) {
      pushLog("err", `× /api/run failed: ${err.message}`);
      setSteps(st => st.map(x => ({ ...x, state: "fail", detail: "api error" })));
      setRunning(false);
      return;
    }

    const sh = (data && data.self_heal) || {};
    const repairs = sh.repairs || [];
    const lastRepair = repairs[repairs.length - 1] || null;
    const diag = data && data.diagnosis;
    const beforeEvi = (data && data.before_evidence) || {};
    const probeErrors = collectProbeErrors(beforeEvi);
    const probeFailMsg = probeErrors[0] || (diag && diag.evidence && diag.evidence[0]) || "probe failed";
    const failureClass = (diag && diag.failure_class) || (lastRepair && lastRepair.failure_class) || failureId;

    if (data.inject) {
      pushLog("info", `injected scenario=${data.inject.scenario}`);
      const before = data.inject.before || {};
      const after  = data.inject.after  || {};
      Object.keys(after).forEach(k => {
        if (JSON.stringify(before[k]) !== JSON.stringify(after[k])) {
          pushLog("info", `   ${k}: ${JSON.stringify(before[k])} → ${JSON.stringify(after[k])}`);
        }
      });
    }

    await sleep(140);
    setStep(0, { state: "fail", detail: probeFailMsg.slice(0, 48) });
    pushLog("err", `× ${probeFailMsg}`);

    await sleep(160);
    setStep(1, { state: "active", detail: "rules provider" });
    pushLog("info", "→ diagnose: provider=rules");
    await sleep(180);
    setStep(1, { state: "done", detail: failureClass });
    pushLog("warn", `diagnosis: ${failureClass}${diag && diag.suspected_cause ? ` — ${diag.suspected_cause}` : ""}`);
    if (diag && diag.recommended_recipe_ids && diag.recommended_recipe_ids.length) {
      pushLog("info", `recommended: [${diag.recommended_recipe_ids.join(", ")}]`);
    }

    await sleep(140);
    if (lastRepair) {
      setStep(2, { state: "active", detail: `applying ${lastRepair.recipe_id}` });
      pushLog("info", `→ heal: applying recipe ${lastRepair.recipe_id}`);
      await sleep(180);
      if (lastRepair.changed_paths && lastRepair.changed_paths.length) {
        pushLog("info", `changed paths: ${lastRepair.changed_paths.join(", ")}`);
      }
      const healState = lastRepair.rolled_back ? "fail" : (lastRepair.applied ? "done" : "fail");
      const healDetail = lastRepair.rolled_back ? "rolled back" : lastRepair.recipe_id;
      setStep(2, { state: healState, detail: healDetail });
      if (lastRepair.reason) pushLog(healState === "done" ? "info" : "err", `${healState === "done" ? "" : "× "}${lastRepair.reason}`);
    } else {
      setStep(2, { state: "fail", detail: "no recipe applied" });
      pushLog("err", "× no candidate recipes were applied");
    }

    await sleep(160);
    setStep(3, { state: "active", detail: "re-running probes" });
    await sleep(180);
    if (sh.healthy) {
      setStep(3, { state: "done", detail: "all probes ok" });
      pushLog("ok", `✓ verification healthy`);
    } else {
      setStep(3, { state: "fail", detail: (sh.reason || "verification failed").slice(0, 48) });
      pushLog("err", `× verification failed${sh.reason ? `: ${sh.reason}` : ""}`);
    }

    await sleep(140);
    setStep(4, { state: "active", detail: "writing incident" });
    await sleep(160);
    if (data.report_path) {
      const incId = data.report_path.split("/").pop().replace(/\.md$/, "");
      setStep(4, { state: "done", detail: incId });
      pushLog("ok", `✓ wrote ${data.report_path}`);
    } else {
      setStep(4, { state: sh.healthy ? "done" : "fail", detail: sh.healthy ? "ok" : "no report" });
    }
    const durTxt = typeof data.duration_ms === "number" ? ` · ${data.duration_ms} ms` : "";
    pushLog(sh.healthy ? "ok" : "err",
            sh.healthy ? `loop complete · healed in ${sh.attempts} attempt${sh.attempts === 1 ? "" : "s"}${durTxt}`
                       : `loop complete · ${sh.reason || "unrecovered"}${durTxt}`);

    setRunning(false);
    if (typeof onComplete === "function") onComplete();
  };

  const collectProbeErrors = (evidence) => {
    const errs = [];
    const ep = (evidence && evidence.endpoint) || {};
    ["models", "chat", "context_length", "tool_call", "rocm_device_flags"].forEach(p => {
      const probe = ep[p];
      if (probe && probe.error) errs.push(`${p}: ${probe.error}`);
    });
    return errs;
  };

  // Static fallback (used only when the backend is unreachable / file://).
  const runHealMock = async (failureId) => {
    setRunning(true);
    setSteps(buildPendingSteps());
    setLogs([]);

    const s = window.buildHealScript(failureId, providerId);
    pushLog("cmd", `rocm-doctor self-heal --provider rules --failure ${failureId}`);
    pushLog("info", `active_model_provider = ${providerId}`);

    setStep(0, { state: "active", detail: "running probes" });
    pushLog("info", "→ check: probes running");
    await sleep(380);
    pushLog("err", `× ${s.probeFailure}`);
    setStep(0, { state: "fail", detail: s.probeFailure.slice(0, 48) });

    await sleep(200);
    setStep(1, { state: "active", detail: "rules provider" });
    pushLog("info", "→ diagnose: provider=rules");
    await sleep(320);
    pushLog("warn", `diagnosis: ${s.diagnosis} — ${s.diagnosisDescription}`);
    pushLog("info", `candidate recipes: [${s.candidates.join(", ")}]`);
    setStep(1, { state: "done", detail: s.diagnosis });

    await sleep(160);
    setStep(2, { state: "active", detail: `applying ${s.chosen}` });
    pushLog("info", `→ heal: snapshot config → applying recipe ${s.chosen}`);
    await sleep(280);
    if (s.edit) {
      pushLog("info", `edit: ${s.edit}`);
      pushLog("info", `   - ${s.edit_from}`);
      pushLog("info", `   + ${s.edit_to}`);
    } else {
      pushLog("info", "no config edit · retry-only recovery");
    }
    setStep(2, { state: "done", detail: s.chosen });

    await sleep(180);
    setStep(3, { state: "active", detail: "re-running probes" });
    for (const v of s.verify) {
      await sleep(240);
      pushLog("ok", `✓ ${v} 200`);
    }
    setStep(3, { state: "done", detail: `${s.verify.length} probe${s.verify.length > 1 ? "s" : ""} ok` });

    await sleep(140);
    setStep(4, { state: "active", detail: "writing incident" });
    await sleep(220);
    const incId = "INC-MOCK-" + String(Math.floor(Math.random() * 900) + 100);
    pushLog("ok", `✓ wrote reports/${incId}.md`);
    setStep(4, { state: "done", detail: incId });
    pushLog("ok", `loop complete · healed (mock)`);
    setRunning(false);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Healing Loop</h1>
          <p className="page-sub">check → diagnose → candidate recipes → apply → verify → report. {window.FAILURES.length} failure classes wired from healing_policy taxonomy.</p>
        </div>
        <div className="page-actions">
          <button className="btn" disabled={running} onClick={() => { setSteps(buildPendingSteps()); setLogs([]); }}>
            <Icon name="x" size={12}/> reset
          </button>
          <button className="btn primary" disabled={running} onClick={() => runHeal(failure)}>
            <Icon name="play" size={12}/> {running ? "running…" : "run"}
          </button>
        </div>
      </div>

      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          {/* LEFT — failure picker + script preview */}
          <div className="grid" style={{ gridTemplateRows: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12, minHeight: 0 }}>
            <Panel title="Inject failure" sub={`provider · ${providerId}`}
                   actions={running && <span className="pill info"><span className="dot"/>running</span>}
                   flush>
              <div className="panel-body" style={{ overflow: "auto" }}>
                <div className="failure-grid">
                  {window.FAILURES.map(f => (
                    <button key={f.id}
                            className={"chip" + (failure === f.id ? " active" : "")}
                            onClick={() => !running && setFailure(f.id)}
                            disabled={running}
                            title={f.description}>
                      {f.id}
                    </button>
                  ))}
                </div>
              </div>
            </Panel>

            <Panel title="Recipe plan" sub={script ? `${script.candidates.length} candidate${script.candidates.length > 1 ? "s" : ""}` : "—"} flush>
              <div className="panel-body" style={{ display: "flex", flexDirection: "column", gap: 8, overflow: "auto" }}>
                <div>
                  <div className="kv-label">diagnosis</div>
                  <div className="kv-val mono">{script?.diagnosis} <span className="muted">— {script?.diagnosisDescription}</span></div>
                </div>
                <div>
                  <div className="kv-label">candidates (ordered)</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                    {script?.candidates.map((rid, idx) => (
                      <span key={rid} className={"pill " + (idx === 0 ? "info" : "muted")}>
                        {idx === 0 && <span className="dot"/>}{rid}
                      </span>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="kv-label">chosen</div>
                  <div className="kv-val mono" style={{ color: "var(--accent)" }}>{script?.chosen}</div>
                </div>
                {script?.edit && (
                  <div>
                    <div className="kv-label">config edit preview</div>
                    <div className="diff">
                      <div className="diff-path">{script.edit}</div>
                      <div className="diff-line del">- {script.edit_from}</div>
                      <div className="diff-line add">+ {script.edit_to}</div>
                    </div>
                  </div>
                )}
                <div>
                  <div className="kv-label">verify</div>
                  <div className="mono" style={{ fontSize: 11.5, color: "var(--text-1)" }}>{script?.verify.join(", ")}</div>
                </div>
              </div>
            </Panel>
          </div>

          {/* RIGHT — live pipeline + logs */}
          <Panel title="Pipeline" sub={running ? "executing" : "idle"} flush className="fill">
            <LoopMini run={{ steps }} />
            <div ref={logEndRef} className="logstream">
              {logs.length === 0 && <div className="muted">— hit "run" to execute the heal loop —</div>}
              {logs.map((l, i) => (
                <div key={i} className="log-line">
                  <span className="log-time">{l.ts}</span>
                  <span className={"log-tag " + l.tag}>{l.tag}</span>
                  <span className="log-msg">{l.msg}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
};

/* ───────────────────────────────────────────────────────────────────── */
/*  Providers — single-screen list + detail                               */
/* ───────────────────────────────────────────────────────────────────── */
const ProvidersPage = ({ providerId, setProviderId }) => {
  const [selectedId, setSelectedId] = usePageState(providerId);
  usePageEffect(() => setSelectedId(providerId), [providerId]);
  const p = window.PROVIDERS.find(x => x.id === selectedId) || window.PROVIDERS[0];

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Providers</h1>
          <p className="page-sub">Adapters defined under <span className="mono">model_providers.*</span></p>
        </div>
      </div>

      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Configured" sub={`${window.PROVIDERS.length} entries`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              {window.PROVIDERS.map(prov => (
                <div key={prov.id}
                     onClick={() => { setSelectedId(prov.id); setProviderId(prov.id); }}
                     style={{
                       display: "flex", alignItems: "center", gap: 10,
                       padding: "8px 12px",
                       borderBottom: "1px solid var(--line-soft)",
                       cursor: "pointer",
                       background: prov.id === selectedId ? "var(--bg-3)" : "transparent",
                       boxShadow: prov.id === selectedId ? "inset 2px 0 0 var(--accent)" : "none",
                     }}>
                  <Icon name="server" size={13} color={prov.id === selectedId ? "var(--accent)" : "var(--text-2)"} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="mono" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{prov.id}</div>
                    <div className="mono" style={{ fontSize: 10.5, color: "var(--text-2)" }}>{prov.runtime} · {prov.accelerator}</div>
                  </div>
                  <StatusPill status={prov.status} />
                </div>
              ))}
            </div>
          </Panel>

          <div className="grid" style={{ gridTemplateRows: "auto 1fr", gap: 12, minHeight: 0 }}>
            <Panel title={p.id} sub={`${p.adapter} · ${p.runtime}`}
                   actions={<StatusPill status={p.status}/>}>
              <dl className="kv">
                <dt>model</dt><dd>{p.model}</dd>
                <dt>endpoint</dt><dd>{p.baseUrl}</dd>
                <dt>backend</dt><dd>{p.backend}</dd>
                <dt>accelerator</dt><dd>{p.accelerator}</dd>
                <dt>rocm</dt><dd>{p.rocm ? "yes" : "no"}</dd>
                <dt>tool_calls</dt><dd>{p.toolCalls ? `enabled · ${p.toolParser}` : "disabled"}</dd>
                <dt>context.max</dt><dd>{p.contextMax} <span className="muted">(safe ≤ {p.safeContextMax})</span></dd>
                <dt>timeout</dt><dd>{p.timeout}s</dd>
              </dl>
            </Panel>

            <Panel title="Probes & safe recipes" flush>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", flex: 1, minHeight: 0 }}>
                <div style={{ borderRight: "1px solid var(--line-soft)", overflow: "auto" }}>
                  <div className="kv-label" style={{ padding: "8px 12px 4px" }}>probes ({p.probes.length})</div>
                  {p.probes.map((pr, idx) => (
                    <div className="probe-row" key={pr}>
                      <Icon name="check" size={12} color="var(--ok)" />
                      <span className="probe-name">{pr}</span>
                      <span className="probe-time">{(40 + idx * 12)} ms</span>
                    </div>
                  ))}
                </div>
                <div style={{ overflow: "auto" }}>
                  <div className="kv-label" style={{ padding: "8px 12px 4px" }}>safe recipes ({(p.safeRecipes || []).length})</div>
                  <div style={{ padding: "0 12px 12px", display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {(p.safeRecipes || []).map(r => <span key={r} className="pill muted">{r}</span>)}
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ───────────────────────────────────────────────────────────────────── */
/*  Recipes — fixed grid that scrolls inside its panel                    */
/* ───────────────────────────────────────────────────────────────────── */
const RecipesPage = () => {
  const [filter, setFilter] = usePageState("all");
  const [query, setQuery] = usePageState("");

  const filtered = window.RECIPES.filter(r => {
    if (filter !== "all" && r.risk !== filter) return false;
    if (query && !(r.id.includes(query) || r.desc.toLowerCase().includes(query.toLowerCase()))) return false;
    return true;
  });

  const counts = {
    all:  window.RECIPES.length,
    none: window.RECIPES.filter(r => r.risk === "none").length,
    low:  window.RECIPES.filter(r => r.risk === "low").length,
    med:  window.RECIPES.filter(r => r.risk === "med").length,
    high: window.RECIPES.filter(r => r.risk === "high").length,
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Recipes</h1>
          <p className="page-sub">{window.RECIPES.length} deterministic, safety-gated repair recipes.</p>
        </div>
        <input
          value={query} onChange={e => setQuery(e.target.value)}
          placeholder="filter…"
          style={{
            background: "var(--bg-2)", border: "1px solid var(--line)", color: "var(--text-0)",
            borderRadius: "var(--r)", padding: "5px 10px", fontSize: 12, width: 220,
            fontFamily: "var(--mono)",
          }}/>
      </div>

      <div className="tabs" style={{ flexShrink: 0 }}>
        {[["all","All"],["none","No-risk"],["low","Low"],["med","Medium"],["high","High"]].map(([k, l]) => (
          <div key={k} className={"tab" + (filter === k ? " active" : "")} onClick={() => setFilter(k)}>
            {l}<span className="tab-count">{counts[k]}</span>
          </div>
        ))}
      </div>

      <div className="page-body">
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="grid recipes-grid">
            {filtered.map(r => (
              <div className="recipe" key={r.id}>
                <div className="recipe-head">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="recipe-id">{r.id}</div>
                    <div className="recipe-desc">{r.desc}</div>
                  </div>
                  <RiskPill risk={r.risk}/>
                </div>
                <div className="recipe-tags">
                  {r.classes.slice(0, 3).map(c => <span key={c} className="pill muted mono">{c}</span>)}
                  {r.classes.length > 3 && <span className="pill muted mono">+{r.classes.length - 3}</span>}
                </div>
                {r.editPath && (
                  <div className="diff" style={{ marginTop: "auto" }}>
                    <div className="diff-path">{r.editPath}</div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

/* ───────────────────────────────────────────────────────────────────── */
/*  Failures                                                              */
/* ───────────────────────────────────────────────────────────────────── */
const FailuresPage = ({ goToLoop }) => (
  <div className="page">
    <div className="page-head">
      <div>
        <h1 className="page-title">Failures</h1>
        <p className="page-sub">{window.FAILURES.length} failure classes from healing_policy.FAILURE_TAXONOMY.</p>
      </div>
    </div>

    <div className="page-body">
      <div style={{ flex: 1, overflow: "auto" }}>
        <div className="grid recipes-grid">
          {window.FAILURES.map(f => (
            <div className="recipe" key={f.id}>
              <div className="recipe-head">
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="recipe-id">{f.id}</div>
                  <div className="recipe-desc">{f.description}</div>
                </div>
                <Icon name="flask" size={14} color="var(--accent)" />
              </div>
              <div className="recipe-tags">
                <span className="pill muted">→</span>
                {f.candidates.map(c => <span key={c} className="pill info mono">{c}</span>)}
              </div>
              <div style={{ marginTop: "auto", display: "flex", justifyContent: "flex-end" }}>
                <button className="btn primary" style={{ padding: "3px 10px", fontSize: 11.5 }}
                        onClick={() => goToLoop(f.id)}>
                  <Icon name="play" size={11}/> run
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

/* ───────────────────────────────────────────────────────────────────── */
/*  Incidents                                                             */
/* ───────────────────────────────────────────────────────────────────── */
const IncidentsPage = ({ openHealRun, refreshKey }) => {
  const incidents = window.INCIDENTS || [];
  const [selected, setSelected] = usePageState(incidents[0] || null);
  const [reportBody, setReportBody] = usePageState(null);
  const [reportError, setReportError] = usePageState(null);

  usePageEffect(() => {
    if (!selected) {
      const next = (window.INCIDENTS || [])[0] || null;
      if (next) setSelected(next);
    }
  }, [refreshKey]);

  usePageEffect(() => {
    if (!selected) { setReportBody(null); return; }
    if (window.API_AVAILABLE && window.apiIncident) {
      setReportBody(null);
      setReportError(null);
      window.apiIncident(selected.id)
        .then(r => setReportBody(r.body))
        .catch(e => setReportError(e.message));
    } else {
      setReportBody(generateReportText(selected));
    }
  }, [selected && selected.id, refreshKey]);

  if (!selected) {
    return (
      <div className="page">
        <div className="page-head">
          <div>
            <h1 className="page-title">Incidents</h1>
            <p className="page-sub">Auto-generated reports. 0 entries — run a heal to generate one.</p>
          </div>
        </div>
        <div className="page-body">
          <Panel flush><div className="empty">No incident reports yet. Run /api/run from the Healing Loop page.</div></Panel>
        </div>
      </div>
    );
  }

  const outcomeStatus = selected.outcome === "healed" ? "healthy" :
                       selected.outcome === "rolled-back" ? "failing" : "degraded";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Incidents</h1>
          <p className="page-sub">Auto-generated reports. {incidents.length} entries.</p>
        </div>
      </div>

      <div className="page-body">
        <div className="grid cols-1-2" style={{ flex: 1, minHeight: 0 }}>
          <Panel title="Reports" sub={`${incidents.length} entries`} flush>
            <div style={{ overflow: "auto", flex: 1 }}>
              <table className="tbl">
                <thead><tr><th>id</th><th>provider</th><th className="right">outcome</th></tr></thead>
                <tbody>
                  {incidents.map(i => (
                    <tr key={i.id} className="row-hover" style={{ cursor: "pointer", background: i.id === selected.id ? "var(--bg-3)" : undefined }}
                        onClick={() => setSelected(i)}>
                      <td className="mono">{i.id}</td>
                      <td className="mono dim" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: 140 }}>{i.provider || "—"}</td>
                      <td className="right">
                        <StatusPill status={i.outcome === "healed" ? "healthy" : i.outcome === "rolled-back" ? "failing" : "degraded"}/>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <div className="grid" style={{ gridTemplateRows: "auto auto 1fr", gap: 12, minHeight: 0 }}>
            <div className="incident-meta">
              <div><div className="lbl">incident</div><div className="val">{selected.id}</div></div>
              <div><div className="lbl">provider</div><div className="val">{selected.provider || "—"}</div></div>
              <div><div className="lbl">recipe</div><div className="val">{selected.recipe || "—"}</div></div>
              <div><div className="lbl">outcome</div><div className="val">
                <StatusPill status={outcomeStatus}/>
              </div></div>
            </div>
            <Panel title="Timeline" sub={selected.ts || "—"} flush>
              <LoopMini run={{
                steps: [
                  { name: "check",    state: "done", detail: selected.failure || "—" },
                  { name: "diagnose", state: "done", detail: `rules · ${selected.failure || "—"}` },
                  { name: "heal",     state: selected.outcome === "rolled-back" ? "fail" : "done", detail: selected.recipe || "—" },
                  { name: "verify",   state: selected.outcome === "rolled-back" ? "fail" : "done",
                                      detail: selected.outcome === "rolled-back" ? "rolling back" : "all probes ok" },
                  { name: "report",   state: "done", detail: selected.id },
                ],
              }}/>
            </Panel>
            <Panel title="Report" sub={selected.path || `reports/${selected.id}.md`} flush>
              <pre className="code" style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}>
                {reportError ? `error: ${reportError}` : (reportBody == null ? "loading…" : reportBody)}
              </pre>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
};

const generateReportText = (i) => {
  const isHealed = i.outcome === "healed";
  return `# ROCm Doctor Incident · ${i.id}

  ts            ${i.ts}
  provider      ${i.provider}
  failure_class ${i.failure}
  recipe        ${i.recipe}
  attempts      ${i.attempts}
  duration_ms   ${i.durationMs}
  outcome       ${i.outcome}
  learned_fix   ${i.learned}

## Verification
- GET  /v1/models                 → ${isHealed ? "200" : "FAIL"}
- POST /v1/chat/completions       → ${isHealed ? "200" : "FAIL"}

## Outcome
${isHealed ? `Healed in ${i.attempts} attempt(s).` : `Verification failed. Snapshot restored.`}
`;
};

/* ───────────────────────────────────────────────────────────────────── */
/*  Config                                                                */
/* ───────────────────────────────────────────────────────────────────── */
const ConfigPage = () => {
  const [tab, setTab] = usePageState("active");
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Config</h1>
          <p className="page-sub">Workspace YAML + persistent state.</p>
        </div>
      </div>
      <div className="tabs" style={{ flexShrink: 0 }}>
        {[["active","rocm-doctor.yaml"],["snapshots","Snapshots"],["state","state.json"]].map(([k, l]) => (
          <div key={k} className={"tab" + (tab === k ? " active" : "")} onClick={() => setTab(k)}>{l}</div>
        ))}
      </div>
      <div className="page-body">
        <Panel className="fill" flush>
          {tab === "active" && (
            <pre className="code" style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}>
              {window.renderYaml(window.SAMPLE_YAML)}
            </pre>
          )}
          {tab === "snapshots" && (
            <div style={{ flex: 1, overflow: "auto" }}>
              <table className="tbl">
                <thead><tr><th>file</th><th>incident</th><th>recipe</th><th className="right">size</th></tr></thead>
                <tbody>
                  {window.INCIDENTS.slice(0, 5).map(i => (
                    <tr key={i.id}>
                      <td className="mono">{i.id}.snap.yaml</td>
                      <td className="mono dim">{i.id}</td>
                      <td className="mono"><span style={{ color: "var(--accent)" }}>{i.recipe}</span></td>
                      <td className="right mono dim">{(3.4 + Math.random() * 0.5).toFixed(1)} KB</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {tab === "state" && (
            <pre className="code" style={{ borderRadius: 0, border: "none", margin: 0, flex: 1, overflow: "auto" }}>{`{
  "version": 1,
  "learned_fixes": {
    "fake-openai/wrong_endpoint_port":      "update_endpoint_url",
    "fake-openai/context_length_too_large": "lower_max_model_len",
    "fake-openai/tool_parser_mismatch":     "set_tool_parser",
    "ollama-qwen3-0-6b/weak_model_overanswer": "tighten_expected_health_response"
  },
  "service_restart_counters": { "fake-vllm": 0, "ollama": 0 },
  "last_known_good": {
    "fake-openai": "state/snapshots/INC-2026-04-12-002.snap.yaml"
  }
}`}</pre>
          )}
        </Panel>
      </div>
    </div>
  );
};

/* Panel needs to accept className for fill */
const PanelOriginal = window.Panel;
const PatchedPanel = ({ title, sub, actions, children, flush, className }) => (
  <div className={"panel" + (className ? " " + className : "")}>
    {(title || sub || actions) && (
      <div className="panel-head">
        {title && <div className="panel-title">{title}</div>}
        {sub && <div className="panel-sub">{sub}</div>}
        {actions && <div className="panel-actions">{actions}</div>}
      </div>
    )}
    {flush ? children : <div className="panel-body">{children}</div>}
  </div>
);
window.Panel = PatchedPanel;

Object.assign(window, {
  OverviewPage, LoopPage, ProvidersPage, RecipesPage, FailuresPage, IncidentsPage, ConfigPage,
});
