/* The Amplifier Agent panel. Violet edge, text on the page — no chat
   bubbles, no second product header inside the app. */
function AgentPanel({ onClose, onToast }) {
  const [draft, setDraft] = React.useState("");
  const [log, setLog] = React.useState([
    { from: "agent", text: "One run is waiting on you: service-directory · block 3 wants approval to promote 0.1.0." },
  ]);
  const send = () => {
    if (!draft.trim()) return;
    setLog((l) => l.concat([{ from: "you", text: draft }, { from: "agent", text: "Reading the block-3 transcript…" }]));
    setDraft("");
    onToast("Sent to Amplifier Agent");
  };
  return (
    <aside style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 380, maxWidth: "92%",
      zIndex: "var(--z-panel)", background: "var(--amp-raised)",
      borderLeft: "1px solid var(--amp-violet-edge)", boxShadow: "var(--shadow-edge-left)",
      display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)",
        padding: "var(--space-lg)", borderBottom: "1px solid var(--amp-line-subtle)" }}>
        <img src="../../assets/amplifier/amplifier-icon-32.png" alt="" width="16" height="16" />
        <h2 style={{ margin: 0, fontSize: "var(--text-md)", fontWeight: 600, flex: 1 }}>Agent</h2>
        <button onClick={onClose} aria-label="Close panel"
          style={{ background: "transparent", border: "none", color: "var(--amp-ink-muted)",
            fontSize: "var(--text-xl)", lineHeight: 1, cursor: "pointer" }}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-lg)", display: "flex",
        flexDirection: "column", gap: "var(--space-lg)" }}>
        {log.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: "var(--space-2xs)" }}>
            <span style={{ fontSize: "var(--text-xs)", textTransform: "uppercase",
              letterSpacing: "var(--tracking-caps)",
              color: m.from === "agent" ? "var(--amp-violet)" : "var(--amp-ink-dim)" }}>{m.from}</span>
            <p style={{ margin: 0, fontSize: "var(--text-md)", lineHeight: 1.5 }}>{m.text}</p>
          </div>
        ))}
      </div>
      <div style={{ padding: "var(--space-lg)", borderTop: "1px solid var(--amp-line-subtle)",
        display: "flex", gap: "var(--space-sm)" }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="Ask about these runs"
          style={{ flex: 1, minWidth: 0, fontSize: "var(--text-md)", fontFamily: "var(--font-ui)",
            color: "var(--amp-ink)", background: "var(--amp-hover)", border: "1px solid var(--amp-line)",
            borderRadius: "var(--radius-sm)", padding: "var(--control-pad-y) var(--control-pad-x)" }} />
        <button onClick={send}
          style={{ background: "var(--amp-violet-dim)", border: "1px solid var(--amp-violet-edge)",
            borderRadius: "var(--radius-sm)", color: "var(--amp-ink)", fontSize: "var(--text-md)",
            padding: "var(--control-pad-y) var(--control-pad-x)", cursor: "pointer" }}>Send</button>
      </div>
      <p style={{ margin: 0, padding: "0 var(--space-lg) var(--space-lg)", fontSize: "var(--text-xs)",
        color: "var(--amp-ink-dim)" }}>Powered by <a href="#">Amplifier Agent</a></p>
    </aside>
  );
}
