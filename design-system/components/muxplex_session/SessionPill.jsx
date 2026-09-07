import React from "react";

/** Floating pill that returns you to the session you were in. Rounded 20px,
 *  75% opacity at rest, and shadowed because it floats over the page. */
export function SessionPill({ label, bell = false, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        position: "absolute",
        bottom: "24px",
        right: "16px",
        zIndex: "var(--z-float)",
        background: "var(--bg-header)",
        border: "1px solid " + (hover ? "var(--accent)" : "var(--border)"),
        borderRadius: "20px",
        padding: "8px 14px",
        display: "flex",
        alignItems: "center",
        gap: "var(--space-sm)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        color: hover ? "var(--text)" : "var(--text-muted)",
        cursor: "pointer",
        boxShadow: "0 4px 12px rgba(0, 0, 0, 0.4)",
        opacity: hover ? 1 : 0.75,
      }}
    >
      {bell ? <span style={{ color: "var(--bell)" }}>&#9679;</span> : null}
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: "140px" }}>
        {label}
      </span>
    </button>
  );
}

/** Filter pill row — a 14px-radius toggle, filled with accent-dim when active. */
export function FilterPill({ active = false, children, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        fontSize: "var(--text-sm)",
        fontFamily: "var(--font-ui)",
        borderRadius: "14px",
        border: "1px solid " + (active || hover ? "var(--accent)" : "var(--border)"),
        background: active ? "var(--accent-dim)" : "transparent",
        color: active || hover ? "var(--accent)" : "var(--text-muted)",
        fontWeight: active ? 700 : 400,
        padding: "3px 10px",
        cursor: "pointer",
        lineHeight: "var(--leading-ui)",
        transition: "border-color var(--t-fast), color var(--t-fast)",
      }}
    >
      {children}
    </button>
  );
}
