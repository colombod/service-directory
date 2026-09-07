import React from "react";
import { AMPLIFIER_ICON } from "./amplifier-icon.js";

/** A real bordered button — used for header actions and for commit actions
 *  (Send), deliberately distinct from QuickLink. The agent variant carries the
 *  Amplifier mark at 16px: one logo asset, not a second one. */
export function HeaderButton({ variant = "default", icon, children, style, ...rest }) {
  const [hover, setHover] = React.useState(false);
  const isAgent = variant === "agent";
  const isCommit = variant === "commit";
  return (
    <button
      type="button"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)",
        minHeight: "26px",
        background: isCommit ? "var(--accent-dim)" : "transparent",
        border: "1px solid " + (hover || isCommit ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)",
        color: isCommit || hover ? "var(--accent)" : "var(--text-muted)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        cursor: "pointer",
        transition: "border-color var(--t-fast), color var(--t-fast)",
        ...style,
      }}
      {...rest}
    >
      {isAgent ? <img src={AMPLIFIER_ICON} alt="" width="16" height="16" /> : icon}
      {children}
    </button>
  );
}
