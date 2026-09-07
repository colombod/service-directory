import React from "react";

const AMP_MARK = "../../assets/amplifier/amplifier-icon-32.png";

/** Attention count. Violet, pulsing (the only looping motion in an
 *  Amplifier app), shown only when an item needs a human. */
export function AttentionBadge({ count, small, style }) {
  return (
    <span
      style={{
        minWidth: small ? 15 : 16,
        height: small ? 15 : 16,
        padding: "0 4px",
        borderRadius: "var(--radius-pill)",
        background: "var(--amp-attention)",
        color: "#fff",
        fontSize: 9,
        fontWeight: 700,
        lineHeight: 1,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        animation: "amp-pulse 1.4s ease-in-out infinite",
        ...style,
      }}
    >
      {count}
    </span>
  );
}

/** The agent affordance: the Amplifier mark plus the word "Agent". Violet
 *  fill + violet edge while open; one of the two bordered controls allowed
 *  in the header. */
export function AgentButton({ onClick, open, markSrc = AMP_MARK, style }) {
  const [hot, setHot] = React.useState(false);
  const on = hot || open;
  return (
    <button
      onClick={onClick}
      title="Ask the Amplifier Agent"
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)",
        background: on ? "var(--amp-attention-dim)" : "transparent",
        border: "1px solid " + (on ? "var(--amp-attention-edge)" : "var(--amp-line)"),
        borderRadius: "var(--radius-sm)",
        color: on ? "var(--amp-ink)" : "var(--amp-ink-muted)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        cursor: "pointer",
        transition: "border-color var(--t-fast), color var(--t-fast)",
        ...style,
      }}
    >
      <img src={markSrc} alt="" width="16" height="16" />
      Agent
    </button>
  );
}

/** The fixed 44px Amplifier app header: mark, app name in plain type, word
 *  chrome, then attention summary and the agent button on the right.
 *  An app does not get its own wordmark. */
export function AmpHeader({ appName, markSrc = AMP_MARK, attention = 0, attentionNoun = "run", onAgent, agentOpen, children, style }) {
  return (
    <header
      style={{
        height: "var(--header-height)",
        padding: "0 var(--grid-padding)",
        background: "var(--amp-page)",
        borderBottom: "1px solid var(--amp-line)",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-md)",
        flexShrink: 0,
        ...style,
      }}
    >
      <img src={markSrc} alt="Amplifier" width="16" height="16" />
      <span style={{ fontSize: "var(--text-md)", fontWeight: 600, letterSpacing: ".01em" }}>{appName}</span>
      <div style={{ display: "flex", alignItems: "center", marginLeft: "var(--space-lg)" }}>{children}</div>
      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "var(--space-md)" }}>
        {attention ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-sm)", fontSize: "var(--text-xs)", color: "var(--amp-attention-ink)" }}>
            <AttentionBadge count={attention} small />
            {attention === 1 ? attentionNoun + " needs you" : attentionNoun + "s need you"}
          </span>
        ) : null}
        {onAgent ? <AgentButton onClick={onAgent} open={agentOpen} markSrc={markSrc} /> : null}
      </div>
    </header>
  );
}
