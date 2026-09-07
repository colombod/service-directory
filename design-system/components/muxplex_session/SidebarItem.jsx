import React from "react";

const PREVIEW_FONT = "'SF Mono', 'Fira Code', Consolas, monospace";

/** The sidebar's 120px session card — the same object as a tile, at rail
 *  density. Active adds a raised fill and an accent edge bar. */
export function SidebarItem({ name, active = false, bell = false, preview = "", badge, onClick }) {
  const [hover, setHover] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        height: "var(--sidebar-item-height)",
        flexShrink: 0,
        background: active ? "var(--bg-surface)" : "var(--bg-secondary)",
        cursor: "pointer",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        border: "1px solid " + (bell ? "var(--bell-border)" : active || hover ? "var(--accent)" : "var(--border)"),
        borderLeft: "3px solid " + (bell ? "var(--bell)" : active ? "var(--accent)" : hover ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)",
        boxShadow: bell ? "var(--glow-bell)" : "none",
        transition: "border-color var(--t-fast), border-left-color var(--t-fast), box-shadow var(--t-fast)",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          justifyContent: "space-between",
          padding: "8px 8px 4px",
          height: "var(--tile-header-height)",
          gap: "var(--space-xs)",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "var(--text-sm)",
            fontWeight: "var(--weight-semibold)",
            color: "var(--text)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            flex: 1,
            minWidth: 0,
          }}
        >
          {name}
        </span>
        {badge}
      </div>
      <div style={{ flex: 1, position: "relative", overflow: "hidden", background: "var(--terminal-bg)" }}>
        <pre
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: "6px 8px",
            fontFamily: PREVIEW_FONT,
            fontSize: "var(--text-2xs)",
            lineHeight: "var(--leading-preview)",
            color: "var(--terminal-fg)",
            whiteSpace: "pre",
            overflow: "hidden",
            margin: 0,
          }}
        >
          {preview}
        </pre>
      </div>
    </div>
  );
}

/** Uppercase device grouping heading inside the sidebar list. */
export function DeviceHeader({ children, version }) {
  return (
    <h4
      style={{
        fontSize: "var(--text-2xs)",
        textTransform: "uppercase",
        letterSpacing: "var(--tracking-caps-wide)",
        color: "var(--text-dim)",
        padding: "0 var(--space-lg)",
        margin: "var(--sidebar-gap) 0 0",
        fontWeight: "var(--weight-semibold)",
      }}
    >
      {children}
      {version ? (
        <span style={{ textTransform: "none", letterSpacing: "normal" }}> {version}</span>
      ) : null}
    </h4>
  );
}
