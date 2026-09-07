import React from "react";

/** Dashed-border empty card. The one dashed border in the system. */
export function EmptyState({ title, hint, style }) {
  return (
    <div
      style={{
        border: "1px dashed var(--border-strong)",
        borderRadius: "10px",
        padding: "44px",
        textAlign: "center",
        color: "var(--text-muted)",
        background: "var(--alt)",
        ...style,
      }}
    >
      <p style={{ fontSize: "15px", fontWeight: 600, color: "var(--text)", margin: "0 0 6px" }}>{title}</p>
      {hint ? <p style={{ margin: 0, fontSize: "13px" }}>{hint}</p> : null}
    </div>
  );
}
