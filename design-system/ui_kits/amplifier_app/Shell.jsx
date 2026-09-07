/* Header, filter, tile overview and the focused rail. Chrome recedes:
   controls are words in azure, not glyph buttons. */
const AMP_MARK = "../../assets/amplifier/amplifier-icon-32.png";

function toneStyle(status) {
  const t = window.STATUS_TONE[status] || "dim";
  if (t === "ok") return { color: "var(--amp-ok)" };
  if (t === "err") return { color: "var(--amp-err)" };
  if (t === "accent") return { color: "var(--amp-azure)" };
  if (t === "attention") return { color: "var(--amp-violet)" };
  return { color: "var(--amp-ink-dim)" };
}

function edgeColour(item, selected, hot) {
  if (item.attention > 0) return "var(--amp-violet)";
  if (selected || hot) return "var(--amp-azure)";
  return "var(--amp-line)";
}

function Link({ children, onClick, expanded, style }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button onClick={onClick} aria-expanded={expanded === undefined ? undefined : String(expanded)}
      onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ display: "inline-flex", alignItems: "center", gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)", background: "transparent", border: "none",
        borderRadius: "var(--radius-sm)", color: hot || expanded ? "var(--amp-azure-hover)" : "var(--amp-azure)",
        fontSize: "var(--text-md)", cursor: "pointer", transition: "color var(--t-fast)", ...style }}>
      {children}
    </button>
  );
}

function Filter({ value, onChange, wide }) {
  const [hot, setHot] = React.useState(false);
  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center", flex: wide ? 1 : undefined }}>
      <input value={value} placeholder="Filter" onChange={(e) => onChange(e.target.value)}
        onFocus={() => setHot(true)} onBlur={() => setHot(false)}
        style={{ fontSize: "var(--text-md)", fontFamily: "var(--font-ui)", color: "var(--amp-ink)",
          background: "var(--amp-hover)", border: "1px solid " + (hot ? "var(--amp-azure)" : "var(--amp-line)"),
          borderRadius: "var(--radius-sm)", padding: "4px 24px 4px 10px",
          width: wide ? "100%" : 150, outline: hot ? "2px solid var(--amp-azure)" : "none", outlineOffset: 1 }} />
      {value ? (
        <button onClick={() => onChange("")} aria-label="Clear filter"
          style={{ position: "absolute", right: 6, width: 16, height: 16, padding: 0, display: "flex",
            alignItems: "center", justifyContent: "center", background: "transparent", border: "none",
            borderRadius: 3, color: "var(--amp-ink-muted)", fontSize: 15, lineHeight: 1, cursor: "pointer" }}>×</button>
      ) : null}
    </div>
  );
}

function AttentionBadge({ count, small }) {
  return (
    <span style={{ minWidth: small ? 15 : 16, height: small ? 15 : 16, padding: "0 4px",
      borderRadius: 999, background: "var(--amp-violet)", color: "#fff", fontSize: 9, fontWeight: 700,
      lineHeight: 1, display: "inline-flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0, animation: "amp-pulse 1.4s ease-in-out infinite" }}>{count}</span>
  );
}

function Header({ filter, setFilter, sort, cycleSort, focused, onBack, onAgent, agentOpen, attention }) {
  return (
    <header style={{ height: "var(--header-height)", padding: "0 var(--grid-padding)",
      background: "var(--amp-page)", borderBottom: "1px solid var(--amp-line)",
      display: "flex", alignItems: "center", gap: "var(--space-md)", flexShrink: 0 }}>
      <img src={AMP_MARK} alt="Amplifier" width="16" height="16" />
      <span style={{ fontSize: "var(--text-md)", fontWeight: 600, letterSpacing: ".01em" }}>{window.APP_NAME}</span>
      <div style={{ display: "flex", alignItems: "center", marginLeft: "var(--space-lg)" }}>
        {focused ? <Link onClick={onBack}>← All runs</Link> : null}
        <Link onClick={cycleSort}>{sort} ▾</Link>
        <div style={{ marginLeft: "var(--space-md)" }}><Filter value={filter} onChange={setFilter} /></div>
      </div>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
        {attention ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-sm)",
            fontSize: "var(--text-xs)", color: "var(--amp-violet)" }}>
            <AttentionBadge count={attention} small />{attention === 1 ? "run needs you" : "runs need you"}
          </span>
        ) : null}
        <AgentButton onClick={onAgent} open={agentOpen} />
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
        fontSize: "var(--text-md)", cursor: "pointer",
        transition: "border-color var(--t-fast), color var(--t-fast)" }}>
      <img src={AMP_MARK} alt="" width="16" height="16" />Agent
    </button>
  );
}

/* Overview tile: equal weight, fixed height, flat, left edge bar always present. */
function Tile({ item, onOpen }) {
  const [hot, setHot] = React.useState(false);
  const attn = item.attention > 0;
  return (
    <div onClick={() => onOpen(item)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ height: "var(--tile-height)", background: "var(--amp-raised)",
        border: "1px solid " + (attn ? "var(--amp-violet-edge)" : hot ? "var(--amp-azure)" : "var(--amp-line)"),
        borderLeft: "3px solid " + edgeColour(item, false, hot),
        borderRadius: "var(--radius-sm)",
        boxShadow: attn ? "0 0 0 1px var(--amp-violet-edge), inset 0 0 12px var(--amp-violet-soft)" : "none",
        display: "flex", flexDirection: "column", cursor: "pointer", overflow: "hidden", position: "relative",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ height: "var(--tile-header-height)", padding: "0 10px", background: "var(--amp-page)",
        borderBottom: "1px solid var(--amp-line-subtle)", display: "flex", alignItems: "center",
        gap: "var(--space-sm)", flexShrink: 0 }}>
        {attn ? <AttentionBadge count={item.attention} /> : null}
        <span style={{ fontSize: "var(--text-md)", fontWeight: 500, flex: 1, whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis" }}>{item.name}</span>
        <span style={{ fontSize: "var(--text-xs)", whiteSpace: "nowrap", ...toneStyle(item.status) }}>{item.status}</span>
      </div>
      <div style={{ padding: "var(--space-md) 10px", borderBottom: "1px solid var(--amp-line-subtle)" }}>
        <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--amp-ink-muted)", lineHeight: 1.45 }}>
          {item.summary}
        </p>
      </div>
      <div style={{ flex: 1, position: "relative", overflow: "hidden", background: "var(--amp-content)" }}>
        <pre style={{ position: "absolute", bottom: 0, left: 0, right: 0, margin: 0, padding: "6px 8px",
          fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", lineHeight: 1.15,
          color: "var(--terminal-fg)", whiteSpace: "pre", overflow: "hidden" }}>{item.preview}</pre>
        <span style={{ position: "absolute", right: 6, bottom: 4, maxWidth: "45%", padding: "1px 5px",
          border: "1px solid var(--amp-line-subtle)", borderRadius: 3, background: "var(--amp-page)",
          color: "var(--amp-ink-muted)", fontFamily: "var(--font-ui)", fontSize: "var(--text-2xs)",
          lineHeight: "var(--leading-ui)", whiteSpace: "nowrap", overflow: "hidden",
          textOverflow: "ellipsis", pointerEvents: "none" }}>{item.owner}</span>
      </div>
    </div>
  );
}

function Overview({ items, onOpen }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "var(--grid-padding)" }}>
      {items.length ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(var(--tile-min-width), 1fr))",
          gap: "var(--grid-gap)", alignContent: "start" }}>
          {items.map((it) => <Tile key={it.id} item={it} onOpen={onOpen} />)}
        </div>
      ) : (
        <p style={{ color: "var(--amp-ink-muted)" }}>No runs match this filter.</p>
      )}
    </div>
  );
}

/* Focused rail: the same list, condensed. Selection keeps the azure edge. */
function RailRow({ item, selected, onOpen }) {
  const [hot, setHot] = React.useState(false);
  const attn = item.attention > 0;
  return (
    <div onClick={() => onOpen(item)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ background: selected ? "var(--amp-hover)" : "var(--amp-raised)", cursor: "pointer",
        border: "1px solid " + (attn ? "var(--amp-violet-edge)" : selected || hot ? "var(--amp-azure)" : "var(--amp-line)"),
        borderLeft: "3px solid " + edgeColour(item, selected, hot),
        borderRadius: "var(--radius-sm)", padding: "var(--space-md)", display: "flex",
        flexDirection: "column", gap: "var(--space-2xs)",
        boxShadow: attn ? "0 0 0 1px var(--amp-violet-edge), inset 0 0 12px var(--amp-violet-soft)" : "none",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
        {attn ? <AttentionBadge count={item.attention} small /> : null}
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, flex: 1, minWidth: 0,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{item.name}</span>
      </div>
      <div style={{ display: "flex", gap: "var(--space-sm)", fontSize: "var(--text-xs)" }}>
        <span style={toneStyle(item.status)}>{item.status}</span>
        <span style={{ color: "var(--amp-ink-dim)" }}>{item.meta}</span>
      </div>
    </div>
  );
}

function Rail({ items, selectedId, onOpen, filter, setFilter }) {
  return (
    <nav style={{ width: 240, minWidth: 240, flexShrink: 0, background: "var(--amp-raised)",
      borderRight: "1px solid var(--amp-line-subtle)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "var(--space-md) var(--space-lg)", borderBottom: "1px solid var(--amp-line-subtle)", flexShrink: 0 }}>
        <Filter value={filter} onChange={setFilter} wide />
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-md)", display: "flex",
        flexDirection: "column", gap: "var(--space-md)" }}>
        {items.map((it) => (
          <RailRow key={it.id} item={it} selected={it.id === selectedId} onOpen={onOpen} />
        ))}
        {items.length === 0 ? (
          <p style={{ color: "var(--amp-ink-muted)", fontSize: "var(--text-sm)", padding: "var(--space-md)" }}>
            No runs match this filter.
          </p>
        ) : null}
      </div>
    </nav>
  );
}
