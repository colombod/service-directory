/* Settings is the home for node/fleet management. Read-only until a write
   token is supplied — every mutation here needs it. */
function SettingsOverlay({ onClose }) {
  const [code, setCode] = React.useState(null);
  const [token, setToken] = React.useState("");
  const section = { padding: "18px 20px", borderBottom: "1px solid var(--sd-border)" };
  const h3 = { margin: "0 0 12px", fontSize: 12, fontWeight: 700, textTransform: "uppercase",
    letterSpacing: ".06em", color: "var(--sd-text-muted)" };
  const input = { width: "100%", padding: "8px 10px", fontSize: 13, color: "var(--sd-text)",
    background: "var(--sd-panel)", border: "1px solid var(--sd-border-strong)", borderRadius: 7 };
  const action = { padding: "8px 16px", fontSize: 13, fontWeight: 600, color: "#fff",
    background: "var(--sd-accent)", border: "none", borderRadius: 7, cursor: "pointer" };
  const dt = { color: "var(--sd-text-faint)", fontWeight: 600, fontSize: 11, textTransform: "uppercase",
    letterSpacing: ".04em", paddingTop: 2 };
  return (
    <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,.45)",
      zIndex: 100, display: "flex", alignItems: "flex-start", justifyContent: "flex-end" }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: "var(--sd-settings-width)", maxWidth: "100%", height: "100%", overflowY: "auto",
          background: "var(--sd-panel)", borderLeft: "1px solid var(--sd-border)", display: "flex",
          flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", padding: "18px 20px 14px",
          borderBottom: "1px solid var(--sd-border)", flexShrink: 0 }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 700, flex: 1 }}>Settings</h2>
          <button onClick={onClose} title="Close settings"
            style={{ border: "none", background: "none", fontSize: 22, cursor: "pointer",
              color: "var(--sd-text-muted)", padding: "0 4px", lineHeight: 1 }}>×</button>
        </div>
        <div style={section}>
          <h3 style={h3}>Write Token</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <label style={{ fontSize: 12, color: "var(--sd-text-muted)" }}>Write token{" "}
              <span style={{ color: "var(--sd-text-faint)" }}>(required for mutations)</span></label>
            <input type="password" value={token} onChange={(e) => setToken(e.target.value)}
              placeholder="Bearer write token (optional on localhost)" style={input} />
          </div>
        </div>
        <div style={section}>
          <h3 style={h3}>Node Identity</h3>
          <dl style={{ display: "grid", gridTemplateColumns: "130px 1fr", gap: "6px 12px", fontSize: 13, margin: 0 }}>
            <dt style={dt}>Name</dt><dd style={{ margin: 0 }}>node-a</dd>
            <dt style={dt}>Federation</dt><dd style={{ margin: 0, color: "var(--sd-up)", fontWeight: 600 }}>enabled</dd>
            <dt style={dt}>Role</dt><dd style={{ margin: 0 }}>primary</dd>
            <dt style={dt}>Version</dt><dd style={{ margin: 0 }}>0.1.0</dd>
            <dt style={dt}>Base URL</dt><dd style={{ margin: 0, wordBreak: "break-all" }}>http://100.111.191.22:80</dd>
          </dl>
        </div>
        <div style={section}>
          <h3 style={h3}>Trusted Peers</h3>
          <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
            <li style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", fontSize: 13 }}>
              <span style={{ fontWeight: 600, flex: 1 }}>node-b</span>
              <span style={{ color: "var(--sd-text-muted)", fontSize: 11, fontFamily: "var(--sd-mono)" }}>
                http://100.111.191.8:80
              </span>
              <span style={{ fontSize: 10, fontWeight: 600, padding: "1px 6px", borderRadius: 4,
                color: "var(--sd-up)", background: "var(--sd-up-bg)" }}>reachable</span>
              <button title="Remove node-b" style={{ border: "none", background: "none",
                color: "var(--sd-text-faint)", fontSize: 16, cursor: "pointer", padding: "0 3px", lineHeight: 1 }}>×</button>
            </li>
          </ul>
        </div>
        <div style={{ padding: "18px 20px" }}>
          <h3 style={h3}>Pairing</h3>
          <p style={{ color: "var(--sd-text-muted)", fontSize: 12, margin: "0 0 8px" }}>
            Issue a one-time code so another node can pair with this one:
          </p>
          <button style={action} onClick={() => setCode("4KQ2-9XPD")}>Issue pairing code</button>
          {code ? (
            <div style={{ marginTop: 10, padding: "10px 14px", background: "var(--sd-alt)",
              border: "1px solid var(--sd-border-strong)", borderRadius: 7, fontSize: 13 }}>
              <span style={{ fontFamily: "var(--sd-mono)", fontWeight: 700, fontSize: 15,
                color: "var(--sd-accent)", letterSpacing: ".05em" }}>{code}</span>
              <div style={{ color: "var(--sd-text-faint)", fontSize: 11, marginTop: 4 }}>
                Expires in 600s (one-time use)
              </div>
            </div>
          ) : null}
          <p style={{ color: "var(--sd-text-muted)", fontSize: 12, margin: "18px 0 8px" }}>
            Pair with a peer using a code they issued:
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <input placeholder="Peer base URL (https://…)" style={input} />
            <input placeholder="Pairing code" style={input} />
            <button style={action}>Pair with peer</button>
          </div>
        </div>
      </div>
    </div>
  );
}
