/* The right pane. Opening in-app is the default; the fallback always offers
   an explicit new-tab escape so the user is never left with a dead end. */
function ViewerWelcome() {
  const ICON = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Cpath d='M3 9h18M9 21V9'/%3E%3C/svg%3E\") center/22px no-repeat";
  return (
    <div style={{ padding: "56px 32px 40px", textAlign: "center", borderBottom: "1px solid var(--sd-border)" }}>
      <div style={{ width: 44, height: 44, margin: "0 auto 16px", borderRadius: 11,
        background: "var(--sd-accent)", WebkitMask: ICON, mask: ICON }} />
      <h2 style={{ fontSize: 17, fontWeight: 650, margin: "0 0 8px", letterSpacing: "-.01em" }}>
        Select a service to open it here
      </h2>
      <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--sd-text-muted)", margin: "0 auto", maxWidth: 440 }}>
        Pick a service to open it here — without leaving the directory.
      </p>
    </div>
  );
}

function RegisterPanel() {
  const [open, setOpen] = React.useState(false);
  const input = { width: "100%", padding: "9px 12px", fontSize: "13.5px", color: "var(--sd-text)",
    background: "var(--sd-panel)", border: "1px solid var(--sd-border-strong)", borderRadius: 7 };
  return (
    <div style={{ padding: "20px 28px", background: "var(--sd-alt)", borderTop: "1px solid var(--sd-border)" }}>
      <div role="button" tabIndex={0} onClick={() => setOpen(!open)}
        style={{ fontSize: 13, fontWeight: 600, color: "var(--sd-text-muted)", cursor: "pointer",
          display: "flex", alignItems: "center", gap: 7, userSelect: "none", marginBottom: open ? 14 : 0 }}>
        <span style={{ fontSize: 15, lineHeight: 1, color: "var(--sd-accent)" }}>{open ? "−" : "+"}</span>
        Register a service
      </div>
      {open ? (
        <div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16,
            paddingBottom: 16, borderBottom: "1px solid var(--sd-border)" }}>
            <label style={{ fontSize: 12, color: "var(--sd-text-muted)" }}>Write token{" "}
              <span style={{ color: "var(--sd-text-faint)", fontWeight: 400 }}>
                (required for remote/tailnet writes)
              </span>
            </label>
            <input type="password" placeholder="Bearer write token (optional on localhost)" style={input} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 10 }}>
            <input placeholder="Name" style={input} />
            <input placeholder="Port" style={input} />
            <input placeholder="Description" style={input} />
            <input placeholder="Category" style={input} />
            <input placeholder="Health URL (optional)" style={input} />
            <button style={{ padding: "9px 18px", fontSize: 13, fontWeight: 600, color: "#fff",
              background: "var(--sd-accent)", border: "none", borderRadius: 7, cursor: "pointer" }}>
              Add service
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ViewerHeader({ name, url, actions, onClose }) {
  const btn = { border: "1px solid var(--sd-border-strong)", background: "var(--sd-panel)",
    color: "var(--sd-text-muted)", borderRadius: 5, padding: "4px 10px", fontSize: 12, cursor: "pointer" };
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 18px",
      borderBottom: "1px solid var(--sd-border)", background: "var(--sd-alt)", flexShrink: 0 }}>
      <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{name}</span>
      {actions}
      <a href={url} target="_blank" rel="noopener" style={{ fontSize: 12 }}>open in new tab ↗</a>
      <button style={btn} onClick={onClose}>Close</button>
    </div>
  );
}

function JsonTree({ value, k, depth }) {
  const isObj = value && typeof value === "object";
  const key = k === undefined ? null : <span style={{ color: "var(--sd-accent)", fontWeight: 600 }}>{k}: </span>;
  if (!isObj) {
    let node;
    if (value === null) node = <span style={{ color: "var(--sd-text-faint)", fontStyle: "italic" }}>null</span>;
    else if (typeof value === "string") node = <span style={{ color: "var(--sd-up)" }}>"{value}"</span>;
    else if (typeof value === "number") node = <span style={{ color: "var(--sd-json-num)" }}>{String(value)}</span>;
    else node = <span style={{ color: "var(--sd-json-bool)" }}>{String(value)}</span>;
    return <li>{key}{node}</li>;
  }
  const entries = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  return (
    <li>
      <details open={depth < 2}>
        <summary style={{ cursor: "pointer" }}>{key}
          <span style={{ color: "var(--sd-text-faint)" }}>{Array.isArray(value) ? "[…]" : "{…}"}</span>
        </summary>
        <ul style={{ listStyle: "none", margin: "0 0 0 18px", padding: 0 }}>
          {entries.map(([ck, cv]) => <JsonTree key={String(ck)} k={ck} value={cv} depth={depth + 1} />)}
        </ul>
      </details>
    </li>
  );
}

function ServiceDetail({ svc, status, onOpenHere }) {
  const Meta = ({ label, children }) => (
    <div style={{ marginBottom: 10, fontSize: 13 }}>
      <span style={{ color: "var(--sd-text-faint)", fontSize: 11, fontWeight: 600, textTransform: "uppercase",
        letterSpacing: ".05em", marginRight: 8 }}>{label}</span>{children}
    </div>
  );
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 10px", letterSpacing: "-.01em" }}>{svc.name}</h2>
      {svc.description ? (
        <p style={{ color: "var(--sd-text-muted)", fontSize: 14, margin: "0 0 16px", lineHeight: 1.5 }}>
          {svc.description}
        </p>
      ) : null}
      {svc.category ? <Meta label="Category">{svc.category}</Meta> : null}
      {svc.tags ? <Meta label="Tags">{svc.tags.join(", ")}</Meta> : null}
      <Meta label="Health"><span style={{ fontWeight: 600 }}>{status}</span></Meta>
      {svc.docs_url ? (
        <Meta label="Docs">
          <a href={svc.docs_url} target="_blank" rel="noopener" style={{ fontWeight: 600 }}>Documentation ↗</a>
        </Meta>
      ) : null}
      <Meta label="Open externally">
        {svc.links.map((l) => (
          <a key={l.label} href={l.url} target="_blank" rel="noopener"
            style={{ fontSize: 12, border: "1px solid var(--sd-border-strong)", padding: "3px 8px",
              borderRadius: 5, marginRight: 6, display: "inline-block" }}>{l.label}</a>
        ))}
      </Meta>
      <div style={{ marginTop: 20 }}>
        <button onClick={() => onOpenHere(svc)}
          style={{ fontSize: 14, fontWeight: 600, color: "#fff", background: "var(--sd-accent)",
            border: "none", borderRadius: 7, padding: "9px 22px", cursor: "pointer" }}>Open here</button>
      </div>
    </div>
  );
}

function Viewer({ svc, status, mode, onOpenHere, onClose }) {
  const [ago, setAgo] = React.useState(0);
  const [auto, setAuto] = React.useState(true);
  React.useEffect(() => {
    if (mode !== "json") return;
    setAgo(0);
    const t = setInterval(() => setAgo((a) => a + 1), 1000);
    return () => clearInterval(t);
  }, [mode, svc]);

  if (!svc) {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ flex: 1, overflowY: "auto" }}>
          <ViewerWelcome />
          <RegisterPanel />
        </div>
      </div>
    );
  }
  const url = svc.links[0].url;
  if (mode === "detail") {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <ServiceDetail svc={svc} status={status} onOpenHere={onOpenHere} />
      </div>
    );
  }
  const btn = { border: "1px solid var(--sd-border-strong)", background: "var(--sd-panel)",
    color: "var(--sd-text-muted)", borderRadius: 5, padding: "4px 10px", fontSize: 12, cursor: "pointer" };
  if (mode === "json") {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <ViewerHeader name={svc.name} url={url} onClose={onClose}
          actions={<React.Fragment>
            <button style={btn} onClick={() => setAgo(0)}>Refresh</button>
            <button style={btn} onClick={() => setAuto(!auto)}>Auto-refresh: {auto ? "on" : "off"}</button>
            <span style={{ fontSize: 11, color: "var(--sd-text-faint)" }}>updated {ago}s ago</span>
          </React.Fragment>} />
        <div style={{ flex: 1, overflow: "auto", padding: "18px 24px", fontFamily: "var(--sd-mono)", fontSize: 13 }}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <JsonTree value={window.STATUS_JSON} depth={0} />
          </ul>
        </div>
      </div>
    );
  }
  if (mode === "fallback") {
    return (
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <ViewerHeader name={svc.name} url={url} onClose={onClose} />
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", padding: 40, textAlign: "center" }}>
          <p style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px" }}>{svc.name}</p>
          <p style={{ color: "var(--sd-text-muted)", fontSize: 13, margin: "0 0 20px" }}>
            This service cannot be embedded (X-Frame-Options or CSP frame-ancestors).
          </p>
          <a href={url} target="_blank" rel="noopener"
            style={{ fontSize: 14, fontWeight: 600, border: "1px solid var(--sd-accent)",
              padding: "8px 18px", borderRadius: 7 }}>Open {svc.name} in a new tab ↗</a>
        </div>
      </div>
    );
  }
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <ViewerHeader name={svc.name} url={url} onClose={onClose}
        actions={<button style={btn}>Reload</button>} />
      <div style={{ flex: 1, background: "var(--sd-alt)", display: "flex", alignItems: "center",
        justifyContent: "center", padding: 24 }}>
        <div style={{ width: "100%", height: "100%", border: "1px solid var(--sd-border)",
          borderRadius: 7, background: "var(--sd-panel)", display: "flex", alignItems: "center",
          justifyContent: "center", color: "var(--sd-text-faint)", fontFamily: "var(--sd-mono)", fontSize: 12 }}>
          embedded &lt;iframe&gt; — {url}
        </div>
      </div>
    </div>
  );
}
