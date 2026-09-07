import React from "react";

/** Category chip that sits immediately after a service name. */
export function CategoryChip({ children, style }) {
  return (
    <span
      style={{
        marginLeft: "7px",
        fontSize: "10px",
        fontWeight: 600,
        color: "var(--accent)",
        background: "var(--accent-weak)",
        padding: "1px 6px",
        borderRadius: "4px",
        ...style,
      }}
    >
      {children}
    </span>
  );
}

/** Hash-prefixed tag run. The "#" is decoration, not part of the value. */
export function TagList({ tags = [], style }) {
  return (
    <span style={{ marginLeft: "6px", display: "inline-flex", gap: "4px", ...style }}>
      {tags.map((t) => (
        <span key={t} style={{ fontSize: "10.5px", color: "var(--text-faint)" }}>
          <span style={{ opacity: 0.6 }}>#</span>
          {t}
        </span>
      ))}
    </span>
  );
}

/** The green dot + "reachable" label in a node-group header. */
export function ReachableBadge({ label = "reachable", style }) {
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 600,
        color: "var(--up)",
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        ...style,
      }}
    >
      <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "currentColor" }} />
      {label}
    </span>
  );
}
