import React from "react";

/**
 * The reference component. A borderless text control that reads as a link,
 * not a button — the header and sidebar view switchers and both sort controls
 * are ONE component with four instances.
 *
 * The no-box guarantee is EXPLICIT in every state (background: transparent,
 * border: none), not merely absent: an explicit override wins the cascade
 * regardless of what any other rule declares for the same property.
 */
export function QuickLink({ as = "button", expanded, caption, children, style, ...rest }) {
  const [active, setActive] = React.useState(false);
  const Tag = as;
  const control = (
    <Tag
      aria-expanded={expanded === undefined ? undefined : String(expanded)}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onFocus={() => setActive(true)}
      onBlur={() => setActive(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)",
        background: "transparent",
        border: "none",
        borderRadius: "var(--radius-sm)",
        color: active || expanded ? "var(--accent-hover)" : "var(--accent)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        cursor: "pointer",
        transition: "color var(--t-fast)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </Tag>
  );
  if (!caption) return control;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", minWidth: 0 }}>
      <span
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-semibold)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-caps)",
          color: "var(--text-muted)",
          flexShrink: 0,
        }}
      >
        {caption}
      </span>
      {control}
    </div>
  );
}
