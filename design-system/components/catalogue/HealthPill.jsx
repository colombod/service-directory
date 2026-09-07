import React from "react";

const STATES = {
  up: { color: "var(--up)", background: "var(--up-bg)" },
  down: { color: "var(--down)", background: "var(--down-bg)" },
  unknown: { color: "var(--unknown)", background: "var(--unknown-bg)" },
};

/** Per-row health, filled in client-side from one batched /api/health call.
 *  Starts as "unknown" — never as an optimistic "up". */
export function HealthPill({ status = "unknown", label, style }) {
  const s = STATES[status] || STATES.unknown;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        fontSize: "10.5px",
        fontWeight: 600,
        padding: "2px 7px",
        borderRadius: "4px",
        textTransform: "capitalize",
        ...s,
        ...style,
      }}
    >
      <span style={{ fontSize: "6px", lineHeight: 1 }}>&#9679;</span>
      <span>{label || status}</span>
    </span>
  );
}
