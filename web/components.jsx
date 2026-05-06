/* Reusable presentational components for ROCm Doctor Console. */

const { useState, useEffect, useRef, useMemo } = React;

/* ── Icons ──────────────────────────────────────────────────────────── */
const Icon = ({ name, size = 16, color = "currentColor", strokeWidth = 1.6 }) => {
  const paths = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></>,
    activity: <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>,
    cpu: <><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></>,
    book: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></>,
    list: <><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    play: <polygon points="5 3 19 12 5 21 5 3"/>,
    refresh: <><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></>,
    chev: <polyline points="6 9 12 15 18 9"/>,
    dot: <circle cx="12" cy="12" r="5"/>,
    check: <polyline points="20 6 9 17 4 12"/>,
    x: <><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></>,
    bolt: <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>,
    plug: <><path d="M12 22v-5"/><path d="M9 8V2"/><path d="M15 8V2"/><path d="M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8z"/></>,
    server: <><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></>,
    wrench: <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>,
    flask: <><path d="M9 2v6L4 18a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-10V2"/><line x1="8" y1="2" x2="16" y2="2"/></>,
    eye: <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></>,
    download: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {paths[name] || null}
    </svg>
  );
};

/* ── Sidebar ────────────────────────────────────────────────────────── */
const NavItem = ({ icon, label, route, active, count, onClick }) => (
  <div className={"nav-item" + (active ? " active" : "")} onClick={() => onClick(route)}>
    <span className="ico"><Icon name={icon} size={15} /></span>
    <span>{label}</span>
    {count != null && <span className="count">{count}</span>}
  </div>
);

const Sidebar = ({ route, setRoute, providerCount, incidentCount, recipeCount }) => (
  <aside className="sidebar">
    <div className="brand">
      <div className="brand-mark">RD</div>
      <div className="brand-name">ROCm Doctor<span className="dim">v0.4</span></div>
    </div>

    <div className="nav-section">
      <div className="nav-section-label">Operate</div>
      <NavItem icon="grid"     label="Overview"      route="overview"  active={route==="overview"}  onClick={setRoute} />
      <NavItem icon="activity" label="Healing Loop"  route="loop"      active={route==="loop"}      onClick={setRoute} />
      <NavItem icon="server"   label="Providers"     route="providers" active={route==="providers"} onClick={setRoute} count={providerCount}/>
    </div>
    <div className="nav-section">
      <div className="nav-section-label">Library</div>
      <NavItem icon="wrench"   label="Recipes"   route="recipes"   active={route==="recipes"}   onClick={setRoute} count={recipeCount} />
      <NavItem icon="flask"    label="Failures"  route="failures"  active={route==="failures"}  onClick={setRoute} />
      <NavItem icon="file"     label="Incidents" route="incidents" active={route==="incidents"} onClick={setRoute} count={incidentCount}/>
    </div>
    <div className="nav-section">
      <div className="nav-section-label">System</div>
      <NavItem icon="settings" label="Config"   route="config"   active={route==="config"}   onClick={setRoute} />
    </div>

    <div className="sidebar-foot">
      <span className="pulse"/>
      <span>monitor running · 4.2s</span>
    </div>
  </aside>
);

/* ── Topbar ─────────────────────────────────────────────────────────── */
const Topbar = ({ route, providerId, setProviderId, onCheck, onSelfHeal, onReset, bootStatus }) => {
  const [open, setOpen] = useState(false);
  const ddRef = useRef(null);
  useEffect(() => {
    const onDoc = (e) => { if (ddRef.current && !ddRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const labels = {
    overview: "Overview", loop: "Healing Loop", providers: "Providers",
    recipes: "Recipes", failures: "Failures", incidents: "Incidents", config: "Config",
  };

  return (
    <header className="topbar">
      <div className="crumbs">
        <span>RocmDoctor</span>
        <span className="sep">/</span>
        <span className="now">{labels[route]}</span>
      </div>
      <div className="topbar-spacer" />

      <div ref={ddRef} style={{ position: "relative" }}>
        <button className="provider-pill" onClick={() => setOpen(o => !o)} title={providerId}>
          <Icon name="server" size={11} />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{providerId}</span>
          <span className="caret"><Icon name="chev" size={11}/></span>
        </button>
        {open && (
          <div className="dd-menu">
            {window.PROVIDERS.map(p => (
              <div key={p.id}
                   className={"dd-item" + (p.id === providerId ? " is-current" : "")}
                   onClick={() => { setProviderId(p.id); setOpen(false); }}>
                <span><Icon name="server" size={13} /></span>
                <span>{p.id}</span>
                <span className="meta">{p.runtime}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {bootStatus === "live" && (
        <span className="pill ok" title="connected to /api/*" style={{ marginRight: 4 }}>
          <span className="dot"/>live
        </span>
      )}
      <button className="topbar-btn" onClick={onCheck}>
        <Icon name="refresh" size={12} /> check
      </button>
      <button className="topbar-btn primary" onClick={onSelfHeal}>
        <Icon name="bolt" size={12} /> heal
      </button>
      {onReset && (
        <button className="topbar-btn" onClick={onReset} title="restore working config from template">
          <Icon name="x" size={12} /> reset
        </button>
      )}
    </header>
  );
};

/* ── Status pill ────────────────────────────────────────────────────── */
const StatusPill = ({ status }) => {
  const map = {
    healthy:  { c: "ok",   t: "healthy" },
    degraded: { c: "warn", t: "degraded" },
    failing:  { c: "err",  t: "failing" },
    healing:  { c: "info", t: "healing" },
    offline:  { c: "muted",t: "offline" },
  };
  const s = map[status] || { c: "muted", t: status };
  return <span className={"pill " + s.c}><span className="dot"/>{s.t}</span>;
};

const RiskPill = ({ risk }) => {
  const c = risk === "none" ? "muted" : risk === "low" ? "ok" : risk === "med" ? "warn" : "err";
  return <span className={"pill " + c}>{risk}</span>;
};

/* ── Stat card ──────────────────────────────────────────────────────── */
const Stat = ({ label, value, foot, footTone, mono }) => (
  <div className="stat">
    <div className="stat-label">{label}</div>
    <div className={"stat-value" + (mono ? " mono" : "")}>{value}</div>
    {foot && <div className={"stat-foot " + (footTone || "")}>{foot}</div>}
  </div>
);

/* ── Sparkline ──────────────────────────────────────────────────────── */
const Spark = ({ data, w = 240, h = 40 }) => {
  const max = Math.max(...data);
  const min = Math.min(...data);
  const span = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((d, i) => [i * step, h - 4 - ((d - min) / span) * (h - 8)]);
  const line = pts.map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`)).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <path className="area" d={area} />
      <path className="line" d={line} />
    </svg>
  );
};

/* ── Panel wrapper ──────────────────────────────────────────────────── */
const Panel = ({ title, sub, actions, children, flush }) => (
  <div className="panel">
    {(title || sub || actions) && (
      <div className="panel-head">
        {title && <div className="panel-title">{title}</div>}
        {sub && <div className="panel-sub">{sub}</div>}
        {actions && <div className="panel-actions">{actions}</div>}
      </div>
    )}
    <div className={"panel-body" + (flush ? " flush" : "")}>{children}</div>
  </div>
);

/* ── YAML highlighter (very small / token-based) ────────────────────── */
const renderYaml = (yaml) => {
  return yaml.split("\n").map((rawLine, i) => {
    const line = rawLine;
    if (/^\s*#/.test(line)) return <div key={i}><span className="yc">{line}</span></div>;
    const m = line.match(/^(\s*-?\s*)([\w\-.]+)(\s*:)(.*)$/);
    if (m) {
      const [, indent, key, colon, rest] = m;
      let valSpan = null;
      const trimmed = rest.trim();
      if (trimmed === "") valSpan = null;
      else if (/^[0-9]+(\.[0-9]+)?$/.test(trimmed)) valSpan = <span className="yn">{rest}</span>;
      else if (/^(true|false|null)$/i.test(trimmed)) valSpan = <span className="yh">{rest}</span>;
      else valSpan = <span className="yv">{rest}</span>;
      return <div key={i}>{indent}<span className="yk">{key}</span><span>{colon}</span>{valSpan}</div>;
    }
    const li = line.match(/^(\s*-\s*)(.*)$/);
    if (li) {
      const [, indent, val] = li;
      return <div key={i}>{indent}<span className="ys">{val}</span></div>;
    }
    return <div key={i}>{line || "\u00A0"}</div>;
  });
};

Object.assign(window, {
  Icon, Sidebar, Topbar, StatusPill, RiskPill, Stat, Spark, Panel, renderYaml,
});
