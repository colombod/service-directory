import React from "react";

const SIZES = {
  sm: { padding: "4px 10px", fontSize: "12px", borderRadius: "5px" },
  md: { padding: "6px 12px", fontSize: "13px", borderRadius: "6px" },
  lg: { padding: "8px 16px", fontSize: "13px", borderRadius: "7px" },
  xl: { padding: "9px 22px", fontSize: "14px", borderRadius: "7px" },
};

/**
 * The dashboard's only button. Three variants, taken verbatim from app.py:
 * primary = accent fill + white ink (detail "Open here", settings actions),
 * secondary = alt fill + strong border + muted ink (Settings, collapse, reload),
 * ghost = no chrome, muted ink (× close, × remove).
 */
export function Button({
  variant = "secondary",
  size = "md",
  as = "button",
  fullWidth = false,
  disabled = false,
  style,
  children,
  ...rest
}) {
  const s = SIZES[size] || SIZES.md;
  const base = {
    font: "inherit",
    fontFamily: "var(--font-ui)",
    fontWeight: 600,
    lineHeight: 1,
    cursor: disabled ? "default" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    width: fullWidth ? "100%" : undefined,
    opacity: disabled ? 0.5 : 1,
    ...s,
  };
  const variants = {
    primary: { color: "var(--text-on-accent)", background: "var(--accent)", border: "none" },
    secondary: {
      color: "var(--text-muted)",
      background: "var(--alt)",
      border: "1px solid var(--border-strong)",
    },
    ghost: {
      color: "var(--text-faint)",
      background: "none",
      border: "none",
      padding: "0 3px",
      fontSize: size === "sm" ? "16px" : "22px",
      fontWeight: 400,
    },
  };
  const Tag = as;
  return (
    <Tag
      disabled={as === "button" ? disabled : undefined}
      style={{ ...base, ...variants[variant], ...style }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
