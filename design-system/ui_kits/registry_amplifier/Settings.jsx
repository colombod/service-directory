/* Settings takes over, so it is a modal, not a panel. Read-only until a write
   token is supplied — every mutation needs it (localhost is the server's own
   exception, not the UI's). */
function Settings({ onClose, onToast }) {
  const [token, setToken] = React.useState("");
  const [code, setCode] = React.useState(null);
  const armed = token.trim().length > 0;
  const section = { padding: "var(--space-lg)", borderBottom: "1px solid var(--amp-line-subtle)" };
  const h3 = { margin: "0 0 var(--space-lg)", fontSize: "var(--text-xs)", fontWeight: 700,
    textTransform: "uppercase", letterSpacing: "var(--tracking-caps)", color: "var(--amp-ink-muted)" };
  const input = { width: "100%", fontSize: "var(--text-md)", fontFamily: "var(--font-ui)",
    color: "var(--amp-ink)", background: "var(--amp-hover)", border: "1px solid var(--amp-line)",
    borderRadius: "var(--radius-sm)", padding: "var(--control-pad-y) var(--control-pad-x)", minHeight: 32 };
  const primary = (on) => ({ background: on ? "var(--amp-azure)" : "transparent",
    border: on ? "none" : "1px solid var(--amp-line)", borderRadius: "var(--radius-sm)",
    color: on ? "var(--amp-ink-on-accent)" : "var(--amp-ink-dim)", fontWeight: 600,
    fontSize: "var(--text-md)", padding: "8px 16px", cursor: on ? "pointer" : "default", minHeight: 34 });
  const dt = { fontSize: "var(--text-xs)", fontWeight: 600, textTransform: "uppercase",
    letterSpacing: "var(--tracking-caps)", color: "var(--amp-ink-dim)", paddingTop: 2 };

  return (
    <div style={{ position: "absolute", inset: 0, zIndex: "var(--z-modal-backdrop)" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "var(--amp-scrim)" }} />
      <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)",
        zIndex: "var(--z-modal)", width: 560, maxWidth: "92%", maxHeight: "86%", overflowY: "auto",
        background: "var(--amp-raised)", border: "1px solid var(--amp-line)",
        borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-modal)" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "var(--space-lg)",
          borderBottom: "1px solid var(--amp-line-subtle)" }}>
          <h2 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: 600, flex: 1 }}>Settings</h2>
          <button onClick={onClose} aria-label="Close settings"
            style={{ background: "transparent", border: "none", color: "var(--amp-ink-muted)",
              fontSize: "var(--text-xl)", lineHeight: 1, cursor: "pointer" }}>×</button>
        </div>

        <div style={section}>
          <h3 style={h3}>Write token</h3>
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)}
            placeholder="Bearer write token (optional on localhost)" style={input} />
          <p style={{ margin: "var(--space-sm) 0 0", fontSize: "var(--text-xs)", color: "var(--amp-ink-dim)" }}>
            Held in this session only. Every mutation below sends it as
            <span style={{ fontFamily: "var(--font-mono)" }}> Authorization: Bearer …</span>
          </p>
        </div>

        <div style={section}>
          <h3 style={h3}>Node identity</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "120px 1fr", gap: "var(--space-sm) var(--space-lg)",
            margin: 0, fontSize: "var(--text-md)" }}>
            <dt style={dt}>Name</dt><dd style={{ margin: 0 }}>{window.NODE.name}</dd>
            <dt style={dt}>Role</dt><dd style={{ margin: 0 }}>{window.NODE.role}</dd>
            <dt style={dt}>Version</dt><dd style={{ margin: 0, fontFamily: "var(--font-mono)" }}>{window.NODE.version}</dd>
            <dt style={dt}>Federation</dt>
            <dd style={{ margin: 0, color: "var(--amp-ok)", fontWeight: 600 }}>enabled</dd>
            <dt style={dt}>Base URL</dt>
            <dd style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: "var(--text-sm)",
              wordBreak: "break-all" }}>{window.NODE.base_url}</dd>
          </dl>
        </div>

        <div style={section}>
          <h3 style={h3}>Trusted peers</h3>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--space-md)",
            padding: "var(--space-md) 0" }}>
            <span style={{ fontWeight: 600, flex: 1 }}>node-b</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)",
              color: "var(--amp-ink-muted)" }}>http://100.111.191.8:80</span>
            <span style={{ fontSize: "var(--text-2xs)", color: "var(--amp-ok)",
              border: "1px solid var(--amp-ok)", borderRadius: "var(--radius-pill)", padding: "1px 6px" }}>
              reachable
            </span>
            <button disabled={!armed} onClick={() => onToast("Removed peer node-b")} title="Remove node-b"
              style={{ background: "none", border: "none", color: armed ? "var(--amp-ink-muted)" : "var(--amp-ink-dim)",
                fontSize: 16, lineHeight: 1, cursor: armed ? "pointer" : "default", padding: "0 2px" }}>×</button>
          </div>
        </div>

        <div style={{ padding: "var(--space-lg)" }}>
          <h3 style={h3}>Pairing</h3>
          <p style={{ margin: "0 0 var(--space-md)", fontSize: "var(--text-sm)", color: "var(--amp-ink-muted)" }}>
            Issue a one-time code so another node can pair with this one:
          </p>
          <button style={primary(armed)} disabled={!armed}
            onClick={() => setCode("4KQ2-9XPD")}>Issue pairing code</button>
          {code ? (
            <div style={{ marginTop: "var(--space-md)", background: "var(--amp-hover)",
              border: "1px solid var(--amp-line)", borderRadius: "var(--radius-sm)", padding: "var(--space-lg)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "var(--text-xl)",
                color: "var(--amp-azure)", letterSpacing: ".05em" }}>{code}</span>
              <div style={{ marginTop: "var(--space-xs)", fontSize: "var(--text-xs)",
                color: "var(--amp-ink-dim)" }}>Expires in 600s (one-time use)</div>
            </div>
          ) : null}
          {!armed ? (
            <p style={{ margin: "var(--space-md) 0 0", fontSize: "var(--text-xs)", color: "var(--amp-ink-dim)" }}>
              Enter a write token to enable pairing and peer removal.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function AgentPanel({ onClose, onToast }) {
  const [draft, setDraft] = React.useState("");
  const [log, setLog] = React.useState([
    { from: "agent", text: "muxterm's heartbeat is overdue — it was registered dynamically with a 90s TTL and last reported 4 minutes ago." },
  ]);
  const send = () => {
    if (!draft.trim()) return;
    setLog((l) => l.concat([{ from: "you", text: draft }, { from: "agent", text: "Checking /api/health across both nodes…" }]));
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
          onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="Ask about this host"
          style={{ flex: 1, minWidth: 0, fontSize: "var(--text-md)", fontFamily: "var(--font-ui)",
            color: "var(--amp-ink)", background: "var(--amp-hover)", border: "1px solid var(--amp-line)",
            borderRadius: "var(--radius-sm)", padding: "var(--control-pad-y) var(--control-pad-x)" }} />
        <button onClick={send}
          style={{ background: "var(--amp-violet-dim)", border: "1px solid var(--amp-violet-edge)",
            borderRadius: "var(--radius-sm)", color: "var(--amp-ink)", fontSize: "var(--text-md)",
            padding: "var(--control-pad-y) var(--control-pad-x)", cursor: "pointer" }}>Send</button>
      </div>
    </aside>
  );
}
