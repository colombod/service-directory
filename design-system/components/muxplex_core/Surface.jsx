import React from "react";

/** A flat rectangle holding content: session tile, sidebar row, settings
 *  panel, menu body. --bg-secondary, 1px --border, --radius-sm, NO shadow. */
export function Surface({ as = "div", padded = false, style, children, ...rest }) {
  const Tag = as;
  return (
    <Tag
      style={{
        background: "var(--bg-secondary)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        boxShadow: "none",
        padding: padded ? "var(--space-lg)" : undefined,
        ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** A small status marker attached to something else. Fill ONLY when it
 *  carries a state. */
export function Badge({ tone = "neutral", pill = true, children, style }) {
  const tones = {
    neutral: { color: "var(--text-muted)", background: "transparent", border: "1px solid var(--border)" },
    accent: { color: "var(--accent)", background: "var(--accent-dim)", border: "1px solid var(--accent)" },
    bell: { color: "#0D1117", background: "var(--bell)", border: "none", fontWeight: 700 },
    ok: { color: "var(--ok)", background: "transparent", border: "1px solid var(--ok)" },
    warn: { color: "var(--warn)", background: "transparent", border: "1px solid var(--warn)" },
    err: { color: "var(--err)", background: "transparent", border: "1px solid var(--err)" },
  };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "var(--text-xs)",
        lineHeight: "var(--leading-ui)",
        padding: "var(--space-2xs) var(--space-xs)",
        borderRadius: pill ? "var(--radius-pill)" : "var(--radius-sm)",
        ...tones[tone],
        ...style,
      }}
    >
      {children}
    </span>
  );
}
