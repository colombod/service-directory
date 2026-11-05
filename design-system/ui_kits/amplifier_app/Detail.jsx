/* The work surface. One primary action, everything else is a link.
   Content lives in a well (--amp-content), chrome frames it. */
function Detail({ item, onResolve, onToast }) {
  const [tab, setTab] = React.useState("output");
  const attn = item.attention > 0;
  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: "var(--space-lg) var(--space-xl)", borderBottom: "1px solid var(--amp-line)",
        display: "flex", alignItems: "flex-start", gap: "var(--space-lg)", flexShrink: 0 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1 style={{ margin: 0, fontSize: "var(--text-xl)", fontWeight: 600, letterSpacing: "-.01em" }}>
            {item.name}
          </h1>
          <p style={{ margin: "var(--space-sm) 0 0", fontSize: "var(--text-md)",
            color: "var(--amp-ink-muted)", lineHeight: 1.5, maxWidth: 620 }}>{item.summary}</p>
          <div style={{ display: "flex", gap: "var(--space-lg)", marginTop: "var(--space-md)",
            fontSize: "var(--text-xs)" }}>
            <span style={toneStyle(item.status)}>{item.status}</span>
            <span style={{ color: "var(--amp-ink-dim)" }}>{item.owner}</span>
            <span style={{ color: "var(--amp-ink-dim)" }}>{item.meta}</span>
            <span style={{ color: "var(--amp-ink-dim)", fontFamily: "var(--font-mono)" }}>{item.id}</span>
          </div>
        </div>
        {attn ? (
          <button onClick={() => { onResolve(item); onToast("Promoted " + item.id); }}
            style={{ flexShrink: 0, background: "var(--amp-interactive)", border: "none",
              borderRadius: "var(--radius-sm)", color: "var(--amp-ink-on-accent)",
              fontSize: "var(--text-md)", fontWeight: 600, padding: "9px 18px", cursor: "pointer",
              minHeight: 36 }}>Promote</button>
        ) : null}
      </div>
      <div style={{ display: "flex", gap: "var(--space-md)", padding: "var(--space-md) var(--space-xl) 0", flexShrink: 0 }}>
        {["output", "blocks", "config"].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            style={{ background: "transparent", border: "none", borderBottom: "2px solid " +
              (tab === t ? "var(--amp-interactive)" : "transparent"),
              color: tab === t ? "var(--amp-ink)" : "var(--amp-ink-muted)", fontSize: "var(--text-md)",
              padding: "var(--space-sm) var(--space-2xs)", cursor: "pointer" }}>{t}</button>
        ))}
      </div>
      <div style={{ flex: 1, margin: "var(--space-md) var(--space-xl) var(--space-xl)",
        border: "1px solid var(--amp-line)", borderRadius: "var(--radius-sm)",
        background: "var(--amp-content)", position: "relative", overflow: "hidden" }}>
        {tab === "output" ? (
          <pre style={{ position: "absolute", inset: 0, margin: 0, padding: "var(--space-lg)",
            fontFamily: "var(--font-mono)", fontSize: "var(--text-lg)", lineHeight: 1.4,
            color: "var(--terminal-fg)", whiteSpace: "pre-wrap", overflow: "auto" }}>
            {item.preview + (attn ? "\n█" : "")}
          </pre>
        ) : tab === "blocks" ? (
          <div style={{ position: "absolute", inset: 0, overflow: "auto", padding: "var(--space-lg)" }}>
            {[["core", "ok"], ["federation", "ok"], ["self-management", item.status]].map(([n, s]) => (
              <div key={n} style={{ display: "flex", alignItems: "center", gap: "var(--space-md)",
                padding: "var(--space-md) 0", borderBottom: "1px solid var(--amp-line-subtle)" }}>
                <span style={{ flex: 1, fontSize: "var(--text-md)" }}>{n}</span>
                <span style={{ fontSize: "var(--text-xs)", ...toneStyle(s) }}>{s}</span>
              </div>
            ))}
          </div>
        ) : (
          <pre style={{ position: "absolute", inset: 0, margin: 0, padding: "var(--space-lg)",
            fontFamily: "var(--font-mono)", fontSize: "var(--text-md)", lineHeight: 1.5,
            color: "var(--amp-ink-muted)", whiteSpace: "pre-wrap", overflow: "auto" }}>
{`owner: ${item.owner}
unit:  ${item.id}
hermetic: true
promote_on_green: false`}
          </pre>
        )}
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
