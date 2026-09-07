import React from "react";

/** One monospace address button per configured host address. The FIRST address
 *  (tailnet, by precedence) is the primary variant; the rest are secondary.
 *  Always target="_blank": external is an explicit option, never the default. */
export function AddressLink({ label, href, variant = "secondary", style, ...rest }) {
  const variants = {
    primary: { color: "var(--text-on-accent)", background: "var(--accent)" },
    secondary: { color: "var(--text-muted)", border: "1px solid var(--border-strong)" },
  };
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      title="Open externally in a new tab"
      style={{
        fontFamily: "var(--mono)",
        fontSize: "11px",
        fontWeight: 600,
        padding: "3px 8px",
        borderRadius: "5px",
        display: "inline-block",
        textDecoration: "none",
        ...variants[variant],
        ...style,
      }}
      {...rest}
    >
      {label}
    </a>
  );
}
