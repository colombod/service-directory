import React from "react";

/** The "Register a service" pattern: a native details/summary whose marker is
 *  a +/− glyph in accent, not a triangle. */
export function Disclosure({ title, open = false, children, style }) {
  const [isOpen, setIsOpen] = React.useState(open);
  return (
    <div style={{ padding: "20px 28px", background: "var(--alt)", borderTop: "1px solid var(--border)", ...style }}>
      <div
        role="button"
        tabIndex={0}
        onClick={() => setIsOpen(!isOpen)}
        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") setIsOpen(!isOpen); }}
        style={{
          margin: 0,
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--text-muted)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "7px",
          userSelect: "none",
          marginBottom: isOpen ? "14px" : 0,
        }}
      >
        <span style={{ fontSize: "15px", lineHeight: 1, color: "var(--accent)" }}>
          {isOpen ? "\u2212" : "+"}
        </span>
        {title}
      </div>
      {isOpen ? children : null}
    </div>
  );
}
