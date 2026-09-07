/* The work surface: service detail, then the in-app viewer. Opening in-app is
   the DEFAULT action; external links are always an explicit new-tab option. */
function Meta({ label, children }) {
  return (
    <div style={{ display: "flex", gap: "var(--space-md)", fontSize: "var(--text-md)",
      marginBottom: "var(--space-sm)" }}>
      <span style={{ width: 108, flexShrink: 0, fontSize: "var(--text-xs)", fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "var(--tracking-caps)", color: "var(--amp-ink-dim)",
        paddingTop: 2 }}>{label}</span>
      <span style={{ minWidth: 0 }}>{children}</span>
    </div>
  );
}

function ExtLink({ label, url }) {
  return (
    <a href={url} target="_blank" rel="noopener" title="Open externally in a new tab"
      style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", padding: "3px 8px",
        borderRadius: "var(--radius-sm)", border: "1px solid var(--amp-line-strong)",
        marginRight: "var(--space-sm)", display: "inline-block", whiteSpace: "nowrap", color: "var(--amp-azure)" }}>{label} ↗</a>
  );
}

function JsonNode({ k, value, depth }) {
  const isObj = value && typeof value === "object";
  const key = k === undefined ? null
    : <span style={{ color: "var(--amp-azure)", fontWeight: 600 }}>{k}: </span>;
  if (!isObj) {
    let node;
    if (value === null) node = <span style={{ color: "var(--amp-ink-dim)", fontStyle: "italic" }}>null</span>;
    else if (typeof value === "string") node = <span style={{ color: "var(--amp-ok)" }}>"{value}"</span>;
    else if (typeof value === "number") node = <span style={{ color: "var(--amp-warn)" }}>{String(value)}</span>;
    else node = <span style={{ color: "var(--amp-violet)" }}>{String(value)}</span>;
    return <li>{key}{node}</li>;
  }
  const entries = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  return (
    <li>
      <details open={depth < 2}>
        <summary style={{ cursor: "pointer" }}>{key}
          <span style={{ color: "var(--amp-ink-dim)" }}>{Array.isArray(value) ? "[…]" : "{…}"}</span>
        </summary>
        <ul style={{ listStyle: "none", margin: "0 0 0 18px", padding: 0 }}>
          {entries.map(([ck, cv]) => <JsonNode key={String(ck)} k={ck} value={cv} depth={depth + 1} />)}
        </ul>
      </details>
    </li>
  );
}

function ViewerToolbar({ svc, mode, actions, onBack }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)",
      padding: "var(--space-md) var(--space-xl)", background: "var(--amp-raised)",
      borderBottom: "1px solid var(--amp-line)", flexShrink: 0 }}>
      <span style={{ fontSize: "var(--text-md)", fontWeight: 600, flex: 1, whiteSpace: "nowrap" }}>{svc.name}</span>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--amp-ink-muted)",
        fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>{mode}</span>
      {actions}
      <a href={svc.links[0].url} target="_blank" rel="noopener"
        style={{ fontSize: "var(--text-xs)" }}>open in new tab ↗</a>
      <Link onClick={onBack} style={{ color: "var(--amp-ink-muted)" }}>Close</Link>
    </div>
  );
}

function Pane({ svc, mode, setMode, onRemove, onToast }) {
  const [ago, setAgo] = React.useState(0);
  const [auto, setAuto] = React.useState(true);
  React.useEffect(() => {
    if (mode !== "json" || !auto) return;
    setAgo(0);
    const t = setInterval(() => setAgo((a) => a + 1), 1000);
    return () => clearInterval(t);
  }, [mode, auto, svc]);

  if (mode === "detail") {
    return (
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-xl) var(--space-2xl)" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-lg)" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ margin: 0, fontSize: "var(--text-xl)", fontWeight: 600, letterSpacing: "-.01em" }}>
              {svc.icon ? <span style={{ marginRight: "var(--space-sm)" }}>{svc.icon}</span> : null}{svc.name}
            </h1>
            <p style={{ margin: "var(--space-sm) 0 var(--space-lg)", fontSize: "var(--text-md)",
              color: "var(--amp-ink-muted)", lineHeight: 1.5, maxWidth: 620 }}>{svc.description}</p>
          </div>
          <button onClick={() => setMode(svc.view_kind === "json" ? "json"
              : svc.name === "grafana" ? "fallback" : "iframe")}
            style={{ flexShrink: 0, background: "var(--amp-azure)", border: "none",
              borderRadius: "var(--radius-sm)", color: "var(--amp-ink-on-accent)", fontWeight: 600,
              fontSize: "var(--text-md)", padding: "9px 18px", cursor: "pointer", minHeight: 36 }}>
            Open here
          </button>
        </div>
        <Meta label="Origin">{svc.origin}</Meta>
        <Meta label="Health"><HealthDot health={svc.health} /></Meta>
        <Meta label="View kind">
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)" }}>{svc.view_kind || "auto"}</span>
          {svc.view_refresh_seconds ? (
            <span style={{ color: "var(--amp-ink-dim)", fontSize: "var(--text-sm)" }}>
              {" "}· auto-refresh {svc.view_refresh_seconds}s
            </span>
          ) : null}
        </Meta>
        <Meta label="Source">
          <span>{svc.source}</span>
          {svc.source === "dynamic" ? (
            <span style={{ color: "var(--amp-ink-dim)" }}> · ttl {svc.ttl}s</span>
          ) : null}
        </Meta>
        {svc.category ? <Meta label="Category">{svc.category}</Meta> : null}
        {svc.tags ? <Meta label="Tags">{svc.tags.map((t) => "#" + t).join("  ")}</Meta> : null}
        {svc.docs_url ? (
          <Meta label="Docs"><a href={svc.docs_url} target="_blank" rel="noopener">Documentation ↗</a></Meta>
        ) : null}
        <Meta label="Addresses">
          {svc.links.map((l) => <ExtLink key={l.label} label={l.label} url={l.url} />)}
        </Meta>
        {svc.attention > 0 ? (
          <div style={{ marginTop: "var(--space-xl)", border: "1px solid var(--amp-violet-edge)",
            background: "var(--amp-violet-dim)", borderRadius: "var(--radius-sm)",
            padding: "var(--space-lg)", display: "flex", alignItems: "center", gap: "var(--space-lg)" }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontSize: "var(--text-md)", fontWeight: 600 }}>Heartbeat overdue</p>
              <p style={{ margin: "var(--space-2xs) 0 0", fontSize: "var(--text-sm)",
                color: "var(--amp-ink-muted)" }}>
                This dynamic entry has not sent a heartbeat within its {svc.ttl}s TTL. Deregister it, or
                let it expire.
              </p>
            </div>
            <button onClick={() => { onRemove(svc); onToast("Deregistered " + svc.name); }}
              style={{ flexShrink: 0, background: "transparent", border: "1px solid var(--amp-err)",
                borderRadius: "var(--radius-sm)", color: "var(--amp-err)", fontSize: "var(--text-md)",
                padding: "8px 14px", cursor: "pointer", minHeight: 36 }}>Deregister</button>
          </div>
        ) : null}
      </div>
    );
  }

  if (mode === "json") {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <ViewerToolbar svc={svc} mode="json · /api/view-proxy" onBack={() => setMode("detail")}
          actions={<React.Fragment>
            <Link onClick={() => setAgo(0)} style={{ fontSize: "var(--text-xs)" }}>Refresh</Link>
            <Link onClick={() => setAuto(!auto)} style={{ fontSize: "var(--text-xs)" }}>
              Auto-refresh: {auto ? "on" : "off"}
            </Link>
            <span style={{ fontSize: "var(--text-2xs)", color: "var(--amp-ink-dim)" }}>updated {ago}s ago</span>
          </React.Fragment>} />
        <div style={{ flex: 1, overflow: "auto", margin: "var(--space-lg) var(--space-xl) var(--space-xl)",
          background: "var(--amp-content)", border: "1px solid var(--amp-line)",
          borderRadius: "var(--radius-sm)", padding: "var(--space-lg)",
          fontFamily: "var(--font-mono)", fontSize: "var(--text-md)" }}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <JsonNode value={window.STATUS_JSON} depth={0} />
          </ul>
        </div>
      </div>
    );
  }

  if (mode === "fallback") {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <ViewerToolbar svc={svc} mode="auto · probe" onBack={() => setMode("detail")} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", padding: "var(--space-2xl)", textAlign: "center" }}>
          <p style={{ margin: "0 0 var(--space-sm)", fontSize: "var(--text-lg)", fontWeight: 600 }}>{svc.name}</p>
          <p style={{ margin: "0 0 var(--space-xl)", fontSize: "var(--text-md)",
            color: "var(--amp-ink-muted)", maxWidth: 460 }}>
            This service cannot be embedded (X-Frame-Options or CSP frame-ancestors).
          </p>
          <a href={svc.links[0].url} target="_blank" rel="noopener"
            style={{ fontSize: "var(--text-md)", fontWeight: 600, border: "1px solid var(--amp-azure)",
              borderRadius: "var(--radius-sm)", padding: "9px 18px" }}>
            Open {svc.name} in a new tab ↗
          </a>
        </div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <ViewerToolbar svc={svc} mode="iframe" onBack={() => setMode("detail")}
        actions={<Link style={{ fontSize: "var(--text-xs)" }}>Reload</Link>} />
      <div style={{ flex: 1, margin: "var(--space-lg) var(--space-xl) var(--space-xl)",
        border: "1px solid var(--amp-line)", borderRadius: "var(--radius-sm)",
        background: "var(--amp-content)", display: "flex", alignItems: "center",
        justifyContent: "center", color: "var(--amp-ink-dim)", fontFamily: "var(--font-mono)",
        fontSize: "var(--text-sm)" }}>
        embedded &lt;iframe&gt; — {svc.links[0].url}
      </div>
    </div>
  );
}

function Toast({ children }) {
  return (
    <div style={{ position: "absolute", bottom: 72, left: "50%", transform: "translateX(-50%)",
      background: "var(--amp-raised)", border: "1px solid var(--amp-line)",
      borderRadius: "var(--radius-sm)", padding: "var(--space-md) var(--space-xl)",
      fontSize: "var(--text-md)", color: "var(--amp-ink-muted)", zIndex: "var(--z-popover)",
      pointerEvents: "none", animation: "amp-toast var(--t-fast)" }}>{children}</div>
  );
}
