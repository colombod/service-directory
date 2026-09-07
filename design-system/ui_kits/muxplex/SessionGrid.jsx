/* The grid is the product: density first. Tiles are fixed-height, flat, and
   the bell state is carried by border + glow + badge together. */
function SessionTile({ s, onOpen }) {
  const [hot, setHot] = React.useState(false);
  const bell = s.bell > 0;
  return (
    <div onClick={() => onOpen(s)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ height: "var(--tile-height)", background: "var(--bg-tile)",
        border: "1px solid " + (bell ? "var(--bell-border)" : hot ? "var(--accent)" : "var(--border)"),
        borderLeft: "3px solid " + (bell ? "var(--bell)" : hot ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)", boxShadow: bell ? "var(--glow-bell)" : "none",
        display: "flex", flexDirection: "column", cursor: "pointer", overflow: "hidden",
        position: "relative", transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ height: "var(--tile-header-height)", padding: "0 10px", background: "var(--bg-header)",
        borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", gap: "var(--space-xs)", flexShrink: 0 }}>
        {bell ? <span style={{ minWidth: 16, height: 16, padding: "0 3px", borderRadius: 8,
          background: "var(--bell)", color: "#0D1117", fontSize: 9, fontWeight: 700, lineHeight: 1,
          display: "inline-flex", alignItems: "center", justifyContent: "center", marginRight: "var(--space-sm)",
          animation: "bell-pulse 1.4s ease-in-out infinite" }}>{s.bell}</span> : null}
        <span style={{ fontSize: "var(--text-md)", fontWeight: 500, color: "var(--text)", flex: 1,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)", whiteSpace: "nowrap",
          marginLeft: "var(--space-md)", opacity: hot ? 0 : 1, transition: "opacity var(--t-fast)" }}>{s.meta}</span>
      </div>
      <div style={{ flex: 1, overflow: "hidden", position: "relative", background: "var(--terminal-bg)" }}>
        <pre style={{ position: "absolute", bottom: 0, left: 0, right: 0, margin: 0, padding: "6px 8px",
          fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", lineHeight: 1,
          color: "var(--terminal-fg)", whiteSpace: "pre", overflow: "hidden" }}>{s.preview}</pre>
        <span style={{ position: "absolute", right: 6, bottom: 4, zIndex: "var(--z-raised)", maxWidth: "45%",
          padding: "1px 5px", border: "1px solid var(--border-subtle)", borderRadius: 3,
          background: "var(--bg-header)", color: "var(--text-muted)", fontFamily: "var(--font-ui)",
          fontSize: "var(--text-2xs)", lineHeight: "var(--leading-ui)", whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis", pointerEvents: "none" }}>{s.device}</span>
      </div>
    </div>
  );
}

function FilterPill({ active, children, onClick }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ fontSize: "var(--text-sm)", borderRadius: 14,
        border: "1px solid " + (active || hot ? "var(--accent)" : "var(--border)"),
        background: active ? "var(--accent-dim)" : "transparent",
        color: active || hot ? "var(--accent)" : "var(--text-muted)", fontWeight: active ? 700 : 400,
        padding: "3px 10px", cursor: "pointer", lineHeight: "var(--leading-ui)",
        transition: "border-color var(--t-fast), color var(--t-fast)" }}>{children}</button>
  );
}

function SessionGrid({ sessions, tier, setTier, onOpen }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--grid-padding)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-sm)", padding: "0 0 var(--space-lg)" }}>
        {["all", "bell", "active", "idle"].map((t) => (
          <FilterPill key={t} active={tier === t} onClick={() => setTier(t)}>{t}</FilterPill>
        ))}
      </div>
      {sessions.length ? (
        <div style={{ display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(var(--tile-min-width), 1fr))",
          gap: "var(--grid-gap)", alignContent: "start" }}>
          {sessions.map((s) => <SessionTile key={s.id} s={s} onOpen={onOpen} />)}
        </div>
      ) : (
        <p style={{ color: "var(--text-muted)", fontSize: "var(--text-md)" }}>
          No sessions match this filter.
        </p>
      )}
    </div>
  );
}

/* One session, full view. The interface is chrome around a terminal. */
function SessionView({ s, onBack }) {
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ height: "var(--tile-header-height)", padding: "0 var(--space-lg)",
        background: "var(--bg-header)", borderBottom: "1px solid var(--border)",
        display: "flex", alignItems: "center", gap: "var(--space-md)", flexShrink: 0 }}>
        <QuickLink onClick={onBack}>← All sessions</QuickLink>
        <span style={{ fontSize: "var(--text-md)", fontWeight: 500 }}>{s.name}</span>
        <span style={{ fontSize: "var(--text-xs)", color: "var(--text-muted)" }}>{s.meta}</span>
        <span style={{ marginLeft: "auto", fontSize: "var(--text-xs)", color: "var(--accent)",
          background: "var(--accent-dim)", border: "1px solid var(--accent)", borderRadius: "var(--radius-sm)",
          padding: "3px 6px", lineHeight: "var(--leading-ui)" }}>{s.device}</span>
      </div>
      <div style={{ flex: 1, background: "var(--terminal-bg)", position: "relative", overflow: "hidden" }}>
        <pre style={{ position: "absolute", inset: 0, margin: 0, padding: "var(--space-lg)",
          fontFamily: "var(--font-mono)", fontSize: "var(--text-lg)", lineHeight: 1.35,
          color: "var(--terminal-fg)", whiteSpace: "pre-wrap" }}>{s.preview + "\n█"}</pre>
      </div>
    </div>
  );
}
