/* Header, overview tiles grouped by origin node, and the focused rail.
   A node appears only when it is reachable — an unreachable peer contributes
   no section at all, exactly as the aggregator behaves. */
const AMP_MARK = "../../assets/amplifier/amplifier-icon-32.png";

function healthStyle(h) {
  if (h === "up") return { color: "var(--amp-ok)" };
  if (h === "down") return { color: "var(--amp-err)" };
  return { color: "var(--amp-ink-dim)" };
}

function HealthDot({ health }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: "var(--text-xs)",
      textTransform: "capitalize", ...healthStyle(health) }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />{health}
    </span>
  );
}

function Attention({ count, small }) {
  return (
    <span style={{ minWidth: small ? 15 : 16, height: small ? 15 : 16, padding: "0 4px", borderRadius: 999,
      background: "var(--amp-violet)", color: "#fff", fontSize: 9, fontWeight: 700, lineHeight: 1,
      display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
      animation: "amp-pulse 1.4s ease-in-out infinite" }}>{count}</span>
  );
}

function Chip({ children, tone }) {
  const t = tone === "accent"
    ? { color: "var(--amp-azure)", background: "var(--amp-azure-dim)", border: "1px solid var(--amp-azure-edge)" }
    : { color: "var(--amp-ink-muted)", background: "transparent", border: "1px solid var(--amp-line)" };
  return (
    <span style={{ fontSize: "var(--text-2xs)", padding: "1px 6px", borderRadius: "var(--radius-pill)",
      lineHeight: "var(--leading-ui)", ...t }}>{children}</span>
  );
}

function Link({ children, onClick, style }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)", background: "transparent", border: "none",
        borderRadius: "var(--radius-sm)", color: hot ? "var(--amp-azure-hover)" : "var(--amp-azure)",
        fontSize: "var(--text-md)", cursor: "pointer", transition: "color var(--t-fast)", ...style }}>
      {children}
    </button>
  );
}

function Filter({ value, onChange, wide }) {
  const [hot, setHot] = React.useState(false);
  const MASK = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E\") center/contain no-repeat";
  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center", flex: wide ? 1 : undefined }}>
      <span aria-hidden="true" style={{ position: "absolute", left: 9, width: 12, height: 12,
        background: "var(--amp-ink-dim)", WebkitMask: MASK, mask: MASK, pointerEvents: "none" }} />
      <input value={value} placeholder="Filter services" onChange={(e) => onChange(e.target.value)}
        aria-label="Filter services by name, description, tag, or origin"
        onFocus={() => setHot(true)} onBlur={() => setHot(false)}
        style={{ fontSize: "var(--text-md)", fontFamily: "var(--font-ui)", color: "var(--amp-ink)",
          background: "var(--amp-hover)", border: "1px solid " + (hot ? "var(--amp-azure)" : "var(--amp-line)"),
          borderRadius: "var(--radius-sm)", padding: "4px 24px 4px 27px", width: wide ? "100%" : 190,
          outline: hot ? "2px solid var(--amp-azure)" : "none", outlineOffset: 1 }} />
      {value ? (
        <button onClick={() => onChange("")} aria-label="Clear filter"
          style={{ position: "absolute", right: 6, width: 16, height: 16, padding: 0, display: "flex",
            alignItems: "center", justifyContent: "center", background: "transparent", border: "none",
            borderRadius: 3, color: "var(--amp-ink-muted)", fontSize: 15, lineHeight: 1, cursor: "pointer" }}>×</button>
      ) : null}
    </div>
  );
}

function Header({ filter, setFilter, focused, onBack, onSettings, onAgent, agentOpen, attention }) {
  return (
    <header style={{ height: "var(--header-height)", padding: "0 var(--grid-padding)",
      background: "var(--amp-page)", borderBottom: "1px solid var(--amp-line)", display: "flex",
      alignItems: "center", gap: "var(--space-md)", flexShrink: 0 }}>
      <img src={AMP_MARK} alt="Amplifier" width="16" height="16" />
      <span style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>App Registry</span>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--amp-ink-muted)" }}>
        {window.NODE.name} · <span style={{ color: "var(--amp-azure)" }}>{window.NODE.role}</span>
      </span>
      <div style={{ display: "flex", alignItems: "center", marginLeft: "var(--space-lg)" }}>
        {focused ? <Link onClick={onBack}>← All services</Link> : null}
        <div style={{ marginLeft: focused ? "var(--space-sm)" : 0 }}>
          <Filter value={filter} onChange={setFilter} />
        </div>
      </div>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
        {attention ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-sm)",
            fontSize: "var(--text-xs)", color: "var(--amp-violet)" }}>
            <Attention count={attention} small />needs you
          </span>
        ) : null}
        <AgentButton onClick={onAgent} open={agentOpen} />
        <Link onClick={onSettings} style={{ color: "var(--amp-ink-muted)" }}>Settings</Link>
      </div>
    </header>
  );
}

function AgentButton({ onClick, open }) {
  const [hot, setHot] = React.useState(false);
  const on = hot || open;
  return (
    <button onClick={onClick} title="Ask the Amplifier Agent"
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)",
        background: on ? "var(--amp-violet-dim)" : "transparent",
        border: "1px solid " + (on ? "var(--amp-violet-edge)" : "var(--amp-line)"),
        borderRadius: "var(--radius-sm)", color: on ? "var(--amp-ink)" : "var(--amp-ink-muted)",
        fontSize: "var(--text-md)", cursor: "pointer" }}>
      <img src={AMP_MARK} alt="" width="16" height="16" />Agent
    </button>
  );
}

function edge(svc, selected, hot) {
  if (svc.attention > 0) return "var(--amp-violet)";
  if (selected || hot) return "var(--amp-azure)";
  return "var(--amp-line)";
}

function ServiceTile({ svc, onOpen, onRemove }) {
  const [hot, setHot] = React.useState(false);
  const attn = svc.attention > 0;
  return (
    <div onClick={() => onOpen(svc)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ background: "var(--amp-raised)",
        border: "1px solid " + (attn ? "var(--amp-violet-edge)" : hot ? "var(--amp-azure)" : "var(--amp-line)"),
        borderLeft: "3px solid " + edge(svc, false, hot), borderRadius: "var(--radius-sm)",
        boxShadow: attn ? "0 0 0 1px var(--amp-violet-edge), inset 0 0 12px var(--amp-violet-soft)" : "none",
        display: "flex", flexDirection: "column", cursor: "pointer", overflow: "hidden",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ padding: "var(--space-md) var(--space-lg)", display: "flex", alignItems: "center",
        gap: "var(--space-sm)", borderBottom: "1px solid var(--amp-line-subtle)" }}>
        {attn ? <Attention count={svc.attention} /> : null}
        {svc.icon ? <span aria-hidden="true">{svc.icon}</span> : null}
        <span style={{ fontSize: "var(--text-md)", fontWeight: 600, flex: 1, minWidth: 0,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{svc.name}</span>
        <HealthDot health={svc.health} />
        {svc.source === "dynamic" ? (
          <button onClick={(e) => { e.stopPropagation(); onRemove(svc); }} title={"Remove " + svc.name}
            style={{ border: "none", background: "none", color: "var(--amp-ink-dim)", fontSize: 16,
              lineHeight: 1, padding: "0 2px", cursor: "pointer" }}>×</button>
        ) : null}
      </div>
      <div style={{ padding: "var(--space-md) var(--space-lg)", display: "flex", flexDirection: "column",
        gap: "var(--space-md)", flex: 1 }}>
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--amp-ink-muted)", lineHeight: 1.45 }}>
          {svc.description}
        </p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-sm)", marginTop: "auto" }}>
          {svc.category ? <Chip tone="accent">{svc.category}</Chip> : null}
          <Chip>{svc.view_kind || "auto"}</Chip>
          <Chip>{svc.source}</Chip>
          {(svc.tags || []).map((t) => <Chip key={t}>#{t}</Chip>)}
        </div>
      </div>
      <div style={{ padding: "var(--space-md) var(--space-lg)", background: "var(--amp-page)",
        borderTop: "1px solid var(--amp-line-subtle)", display: "flex", alignItems: "center",
        gap: "var(--space-md)" }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)",
          color: "var(--amp-ink-muted)", flex: 1, overflow: "hidden", whiteSpace: "nowrap",
          textOverflow: "ellipsis" }}>{svc.links[0].url}</span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--amp-azure)" }}>Open here →</span>
      </div>
    </div>
  );
}

function Overview({ services, onOpen, onRemove }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--grid-padding)" }}>
      {window.NODES.map((node) => {
        const rows = services.filter((s) => s.origin === node.name);
        if (!rows.length) return null;
        return (
          <section key={node.name} style={{ marginBottom: "var(--space-2xl)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)",
              padding: "0 0 var(--space-md)" }}>
              <h2 style={{ margin: 0, fontSize: "var(--text-2xs)", fontWeight: 700, textTransform: "uppercase",
                letterSpacing: "var(--tracking-caps-wide)", color: "var(--amp-ink-muted)" }}>{node.name}</h2>
              <span style={{ fontSize: "var(--text-2xs)", color: "var(--amp-ok)", display: "inline-flex",
                alignItems: "center", gap: 4 }}>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "currentColor" }} />reachable
              </span>
              <span style={{ fontSize: "var(--text-xs)", color: "var(--amp-ink-dim)" }}>— {node.description}</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: "var(--grid-gap)", alignItems: "stretch" }}>
              {rows.map((s) => <ServiceTile key={s.name} svc={s} onOpen={onOpen} onRemove={onRemove} />)}
            </div>
          </section>
        );
      })}
      {services.length === 0 ? (
        <div style={{ border: "1px dashed var(--amp-line-strong)", borderRadius: "var(--radius-sm)",
          padding: "var(--space-2xl)", textAlign: "center", color: "var(--amp-ink-muted)" }}>
          <p style={{ margin: "0 0 var(--space-sm)", fontSize: "var(--text-lg)", color: "var(--amp-ink)" }}>
            No services match this filter
          </p>
          <p style={{ margin: 0, fontSize: "var(--text-md)" }}>
            Clear the filter, or register a service with <code>POST /api/services</code>.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function RailRow({ svc, selected, onOpen }) {
  const [hot, setHot] = React.useState(false);
  const attn = svc.attention > 0;
  return (
    <div onClick={() => onOpen(svc)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ background: selected ? "var(--amp-hover)" : "var(--amp-raised)", cursor: "pointer",
        border: "1px solid " + (attn ? "var(--amp-violet-edge)" : selected || hot ? "var(--amp-azure)" : "var(--amp-line)"),
        borderLeft: "3px solid " + edge(svc, selected, hot), borderRadius: "var(--radius-sm)",
        padding: "var(--space-md)", display: "flex", flexDirection: "column", gap: "var(--space-2xs)",
        boxShadow: attn ? "0 0 0 1px var(--amp-violet-edge), inset 0 0 12px var(--amp-violet-soft)" : "none",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
        {attn ? <Attention count={svc.attention} small /> : null}
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, flex: 1, minWidth: 0,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{svc.name}</span>
      </div>
      <div style={{ display: "flex", gap: "var(--space-sm)", alignItems: "center" }}>
        <HealthDot health={svc.health} />
        <span style={{ fontSize: "var(--text-xs)", color: "var(--amp-ink-dim)" }}>{svc.view_kind || "auto"}</span>
      </div>
    </div>
  );
}

function Rail({ services, selectedName, onOpen, filter, setFilter }) {
  return (
    <nav style={{ width: 260, minWidth: 260, flexShrink: 0, background: "var(--amp-raised)",
      borderRight: "1px solid var(--amp-line-subtle)", display: "flex", flexDirection: "column",
      overflow: "hidden" }}>
      <div style={{ padding: "var(--space-md) var(--space-lg)",
        borderBottom: "1px solid var(--amp-line-subtle)", flexShrink: 0 }}>
        <Filter value={filter} onChange={setFilter} wide />
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-md)", display: "flex",
        flexDirection: "column", gap: "var(--space-md)" }}>
        {window.NODES.map((node) => {
          const rows = services.filter((s) => s.origin === node.name);
          if (!rows.length) return null;
          return (
            <React.Fragment key={node.name}>
              <h4 style={{ margin: "var(--space-sm) 0 0", padding: "0 var(--space-xs)",
                fontSize: "var(--text-2xs)", fontWeight: 600, textTransform: "uppercase",
                letterSpacing: "var(--tracking-caps-wide)", color: "var(--amp-ink-dim)" }}>{node.name}</h4>
              {rows.map((s) => (
                <RailRow key={s.name} svc={s} selected={s.name === selectedName} onOpen={onOpen} />
              ))}
            </React.Fragment>
          );
        })}
      </div>
    </nav>
  );
}
