/* Everything that overlaps live content — and therefore everything with a
   shadow. Layering comes from the measured ladder, never a fresh integer. */
function Modal({ title, onClose, children }) {
  return (
    <div style={{ position: "absolute", inset: 0, zIndex: "var(--z-modal-backdrop)" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "var(--bg-overlay)" }} />
      <div style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)",
        zIndex: "var(--z-modal)", width: 520, maxWidth: "92%", background: "var(--bg-secondary)",
        border: "1px solid var(--border)", borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-modal)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "var(--space-lg)", borderBottom: "1px solid var(--border-subtle)" }}>
          <h2 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: 600 }}>{title}</h2>
          <button onClick={onClose} aria-label="Close" style={{ background: "transparent", border: "none",
            color: "var(--text-muted)", fontSize: "var(--text-xl)", lineHeight: 1, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ padding: "var(--space-lg)" }}>{children}</div>
      </div>
    </div>
  );
}

function SettingsDialog({ onClose, zoom, setZoom, bell, setBell }) {
  const rowStyle = { display: "flex", flexDirection: "column", gap: "var(--space-sm)", marginBottom: "var(--space-lg)" };
  const labelStyle = { fontSize: "var(--text-sm)", color: "var(--text-muted)" };
  return (
    <Modal title="Settings" onClose={onClose}>
      <div style={{ display: "flex", gap: "var(--space-2xl)" }}>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, width: 120, display: "flex",
          flexDirection: "column", gap: "var(--space-sm)" }}>
          {["Display", "Sessions", "Commands", "Multi-device"].map((t, i) => (
            <li key={t} style={{ fontSize: "var(--text-md)", color: i === 0 ? "var(--accent)" : "var(--text-muted)",
              padding: "var(--control-pad-y) var(--control-pad-x)",
              background: i === 0 ? "var(--accent-dim)" : "transparent", borderRadius: "var(--radius-sm)" }}>{t}</li>
          ))}
        </ul>
        <div style={{ flex: 1 }}>
          <div style={rowStyle}>
            <label style={labelStyle}>Preview zoom — {zoom}%</label>
            <input type="range" min="60" max="140" step="10" value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))} style={{ accentColor: "var(--accent)" }} />
            <span style={{ fontSize: "var(--text-xs)", color: "var(--text-dim)" }}>
              Scales tile height and minimum column width together.
            </span>
          </div>
          <div style={rowStyle}>
            <label style={labelStyle}>Bell alerts</label>
            <div style={{ display: "flex", gap: "var(--space-sm)" }}>
              {["glow", "dot", "off"].map((m) => (
                <FilterPill key={m} active={bell === m} onClick={() => setBell(m)}>{m}</FilterPill>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Modal>
  );
}

/* The agent panel: a section header like any other panel, text on the page —
   no filled bubbles, no second product header. */
function AgentPanel({ onClose, onSend }) {
  const [draft, setDraft] = React.useState("");
  const [log, setLog] = React.useState([
    { from: "agent", text: "Two sessions have pending prompts. deploy is waiting on a y/N." },
  ]);
  const send = () => {
    if (!draft.trim()) return;
    setLog((l) => l.concat([{ from: "you", text: draft }, { from: "agent", text: "Reading the deploy transcript…" }]));
    setDraft("");
    onSend();
  };
  return (
    <aside style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 380, maxWidth: "92%",
      zIndex: "var(--z-panel)", background: "var(--bg-secondary)", borderLeft: "1px solid var(--border)",
      boxShadow: "var(--shadow-edge-left)", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)",
        padding: "var(--space-lg)", borderBottom: "1px solid var(--border-subtle)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--text-md)", fontWeight: 600, flex: 1 }}>Agent</h2>
        <button onClick={onClose} aria-label="Close panel" style={{ background: "transparent", border: "none",
          color: "var(--text-muted)", fontSize: "var(--text-xl)", lineHeight: 1, cursor: "pointer" }}>×</button>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "var(--space-lg)", display: "flex",
        flexDirection: "column", gap: "var(--space-lg)" }}>
        {log.map((m, i) => (
          <div key={i} style={{ display: "flex", flexDirection: "column", gap: "var(--space-2xs)" }}>
            <span style={{ fontSize: "var(--text-xs)", textTransform: "uppercase",
              letterSpacing: "var(--tracking-caps)", color: "var(--text-dim)" }}>{m.from}</span>
            <p style={{ margin: 0, fontSize: "var(--text-md)", color: "var(--text)", lineHeight: 1.5 }}>{m.text}</p>
          </div>
        ))}
      </div>
      <div style={{ padding: "var(--space-lg)", borderTop: "1px solid var(--border-subtle)",
        display: "flex", gap: "var(--space-sm)" }}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }} placeholder="Ask about this fleet"
          style={{ flex: 1, minWidth: 0, fontSize: "var(--text-md)", fontFamily: "var(--font-ui)",
            color: "var(--text)", background: "var(--bg-surface)", border: "1px solid var(--border)",
            borderRadius: "var(--radius-sm)", padding: "var(--control-pad-y) var(--control-pad-x)" }} />
        <button onClick={send} style={{ background: "var(--accent-dim)", border: "1px solid var(--accent)",
          borderRadius: "var(--radius-sm)", color: "var(--accent)", fontSize: "var(--text-md)",
          padding: "var(--control-pad-y) var(--control-pad-x)", cursor: "pointer" }}>Send</button>
      </div>
      <p style={{ margin: 0, padding: "0 var(--space-lg) var(--space-lg)", fontSize: "var(--text-xs)",
        color: "var(--text-dim)", display: "flex", alignItems: "center", gap: "var(--space-xs)" }}>
        <img src="../../assets/amplifier/amplifier-icon-32.png" alt="" width="14" height="14" />
        Powered by <a href="#" style={{ color: "var(--accent)" }}>Amplifier Agent</a>
      </p>
    </aside>
  );
}

function Toast({ children }) {
  return (
    <div style={{ position: "absolute", bottom: 80, left: "50%", transform: "translateX(-50%)",
      background: "var(--bg-header)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)",
      padding: "var(--space-md) var(--space-xl)", fontSize: "var(--text-md)", color: "var(--text-muted)",
      zIndex: "var(--z-popover)", pointerEvents: "none", animation: "toast-in var(--t-fast)" }}>{children}</div>
  );
}

function SessionPillFloating({ label, bell, onClick }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button onClick={onClick} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ position: "absolute", bottom: 24, right: 16, zIndex: "var(--z-float)",
        background: "var(--bg-header)", border: "1px solid " + (hot ? "var(--accent)" : "var(--border)"),
        borderRadius: 20, padding: "8px 14px", display: "flex", alignItems: "center", gap: "var(--space-sm)",
        fontSize: "var(--text-md)", color: hot ? "var(--text)" : "var(--text-muted)", cursor: "pointer",
        boxShadow: "0 4px 12px rgba(0,0,0,.4)", opacity: hot ? 1 : 0.75 }}>
      {bell ? <span style={{ color: "var(--bell)" }}>●</span> : null}
      <span style={{ maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
    </button>
  );
}
