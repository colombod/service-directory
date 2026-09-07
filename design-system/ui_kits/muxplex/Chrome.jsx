/* Header + session rail. Chrome recedes: quick controls read as links, the
   only bordered buttons are Settings and the Agent action. */
const AMP = "../../assets/amplifier/amplifier-icon-32.png";

function QuickLink({ children, expanded, onClick, caption, style }) {
  const [hot, setHot] = React.useState(false);
  const btn = (
    <button
      onClick={onClick}
      aria-expanded={expanded === undefined ? undefined : String(expanded)}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ display: "flex", alignItems: "center", gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)", background: "transparent",
        border: "none", borderRadius: "var(--radius-sm)",
        color: hot || expanded ? "var(--accent-hover)" : "var(--accent)",
        fontSize: "var(--text-md)", cursor: "pointer", transition: "color var(--t-fast)", ...style }}>
      {children}
    </button>
  );
  if (!caption) return btn;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", minWidth: 0 }}>
      <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, textTransform: "uppercase",
        letterSpacing: "var(--tracking-caps)", color: "var(--text-muted)", flexShrink: 0 }}>{caption}</span>
      {btn}
    </div>
  );
}

function HeaderButton({ children, icon, agent, onClick, title }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button onClick={onClick} title={title}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)", background: "transparent",
        border: "1px solid " + (hot ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)", color: hot ? "var(--accent)" : "var(--text-muted)",
        fontSize: "var(--text-md)", cursor: "pointer",
        transition: "border-color var(--t-fast), color var(--t-fast)" }}>
      {agent ? <img src={AMP} alt="" width="16" height="16" /> : icon}
      {children}
    </button>
  );
}

function FilterInput({ value, onChange, caption }) {
  const [hot, setHot] = React.useState(false);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", minWidth: 0, flex: caption ? 1 : undefined }}>
      {caption ? <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, textTransform: "uppercase",
        letterSpacing: "var(--tracking-caps)", color: "var(--text-muted)", flexShrink: 0 }}>{caption}</span> : null}
      <div style={{ position: "relative", display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
        <input value={value} placeholder="Filter" onChange={(e) => onChange(e.target.value)}
          onFocus={() => setHot(true)} onBlur={() => setHot(false)}
          style={{ fontSize: "var(--text-md)", fontFamily: "var(--font-ui)", color: "var(--text)",
            background: "var(--bg-surface)", border: "1px solid " + (hot ? "var(--accent)" : "var(--border)"),
            borderRadius: "var(--radius-sm)", padding: "4px 24px 4px 10px",
            maxWidth: caption ? "none" : "140px", flex: caption ? 1 : undefined, minWidth: 0,
            outline: hot ? "var(--focus-ring)" : "none", outlineOffset: "1px" }} />
        {value ? (
          <button onClick={() => onChange("")} aria-label="Clear filter"
            style={{ position: "absolute", right: 6, width: 16, height: 16, padding: 0, display: "flex",
              alignItems: "center", justifyContent: "center", background: "transparent", border: "none",
              borderRadius: 3, color: "var(--text-muted)", fontSize: 15, lineHeight: 1, cursor: "pointer" }}>×</button>
        ) : null}
      </div>
    </div>
  );
}

function Header({ view, setView, sort, cycleSort, filter, setFilter, onToggleRail, onSettings, onAgent }) {
  return (
    <header style={{ height: "var(--header-height)", padding: "0 var(--grid-padding)",
      background: "var(--bg-header)", borderBottom: "1px solid var(--border)",
      display: "flex", alignItems: "center", flexShrink: 0 }}>
      <QuickLink onClick={onToggleRail} style={{ marginLeft: -6, color: "var(--text-muted)" }}>☰</QuickLink>
      <img src="../../assets/branding/svg/wordmark/wordmark-on-dark.svg" alt="muxplex" style={{ height: 18, marginLeft: 4 }} />
      <div style={{ display: "flex", alignItems: "center", marginLeft: "var(--space-xl)" }}>
        <QuickLink onClick={() => setView(view === "Grid" ? "List" : "Grid")}>{view} ▾</QuickLink>
        <QuickLink onClick={cycleSort} style={{ marginLeft: "var(--space-md)" }}>{sort} ▾</QuickLink>
        <div style={{ marginLeft: "var(--space-md)" }}>
          <FilterInput value={filter} onChange={setFilter} />
        </div>
      </div>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
        <HeaderButton agent onClick={onAgent} title="Muxplex Agent -- powered by Amplifier Agent">Agent</HeaderButton>
        <HeaderButton onClick={onSettings} icon="⚙">Settings</HeaderButton>
      </div>
    </header>
  );
}

function SidebarItem({ s, active, onClick }) {
  const [hot, setHot] = React.useState(false);
  const bell = s.bell > 0;
  return (
    <div onClick={onClick} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ height: "var(--sidebar-item-height)", flexShrink: 0,
        background: active ? "var(--bg-surface)" : "var(--bg-secondary)", cursor: "pointer",
        overflow: "hidden", display: "flex", flexDirection: "column", position: "relative",
        border: "1px solid " + (bell ? "var(--bell-border)" : active || hot ? "var(--accent)" : "var(--border)"),
        borderLeft: "3px solid " + (bell ? "var(--bell)" : active || hot ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)", boxShadow: bell ? "var(--glow-bell)" : "none",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "8px 8px 4px", height: "var(--tile-header-height)", gap: "var(--space-xs)", flexShrink: 0 }}>
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: "var(--text)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1, minWidth: 0 }}>{s.name}</span>
        {bell ? <span style={{ minWidth: 16, height: 16, padding: "0 3px", borderRadius: 8,
          background: "var(--bell)", color: "#0D1117", fontSize: 9, fontWeight: 700, display: "inline-flex",
          alignItems: "center", justifyContent: "center", animation: "bell-pulse 1.4s ease-in-out infinite" }}>{s.bell}</span> : null}
      </div>
      <div style={{ flex: 1, position: "relative", overflow: "hidden", background: "var(--terminal-bg)" }}>
        <pre style={{ position: "absolute", bottom: 0, left: 0, right: 0, margin: 0, padding: "6px 8px",
          fontFamily: "var(--font-mono)", fontSize: "var(--text-2xs)", lineHeight: 1,
          color: "var(--terminal-fg)", whiteSpace: "pre", overflow: "hidden" }}>{s.preview}</pre>
      </div>
    </div>
  );
}

function Rail({ collapsed, sessions, activeId, onOpen, sort, cycleSort, filter, setFilter }) {
  return (
    <nav style={{ width: collapsed ? 0 : "var(--sidebar-width)", minWidth: collapsed ? 0 : "var(--sidebar-width)",
      background: "var(--bg-secondary)", borderRight: collapsed ? "none" : "1px solid var(--border-subtle)",
      display: "flex", flexDirection: "column", overflow: "hidden", flexShrink: 0,
      transition: "width .25s ease, min-width .25s ease" }}>
      <div style={{ padding: "var(--space-md) var(--space-lg)", borderBottom: "1px solid var(--border-subtle)",
        flexShrink: 0, display: "flex", flexDirection: "column", gap: "var(--space-xs)" }}>
        <QuickLink caption="Sort" onClick={cycleSort}>{sort}</QuickLink>
        <FilterInput caption="Filter" value={filter} onChange={setFilter} />
      </div>
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column",
        gap: "var(--sidebar-gap)", padding: "var(--space-md)" }}>
        {window.DEVICES.map((d) => {
          const rows = sessions.filter((s) => s.device === d);
          if (!rows.length) return null;
          return (
            <React.Fragment key={d}>
              <h4 style={{ fontSize: "var(--text-2xs)", textTransform: "uppercase",
                letterSpacing: "var(--tracking-caps-wide)", color: "var(--text-dim)",
                padding: "0 var(--space-xs)", margin: 0, fontWeight: 600 }}>{d}</h4>
              {rows.map((s) => (
                <SidebarItem key={s.id} s={s} active={s.id === activeId} onClick={() => onOpen(s)} />
              ))}
            </React.Fragment>
          );
        })}
        {sessions.length === 0 ? (
          <p style={{ padding: "var(--space-xl) var(--space-lg)", color: "var(--text-muted)", fontSize: "var(--text-sm)", margin: 0 }}>
            No sessions match this filter.
          </p>
        ) : null}
      </div>
      <div style={{ padding: "var(--space-md)", borderTop: "1px solid var(--border-subtle)" }}>
        <QuickLink style={{ width: "100%", justifyContent: "center" }}>+ New session</QuickLink>
      </div>
    </nav>
  );
}
