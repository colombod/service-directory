import React from "react";

const PREVIEW_FONT = "'SF Mono', 'Fira Code', Consolas, monospace";

/** A live session in the grid. Fixed 300px tall, 4px radius, flat, with a
 *  3px left edge bar that is ALWAYS present so the bell state changes its
 *  colour rather than its geometry. */
export function SessionTile({
  name,
  meta,
  preview = "",
  bellCount = 0,
  edgeBell = false,
  deviceTag,
  loading = false,
  onClick,
  style,
}) {
  const [hover, setHover] = React.useState(false);
  const bell = bellCount > 0;
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        height: "var(--tile-height)",
        background: "var(--bg-tile)",
        border: "1px solid " + (bell ? "var(--bell-border)" : hover ? "var(--accent)" : "var(--border)"),
        borderLeft: "3px solid " + (bell || edgeBell ? "var(--bell)" : hover ? "var(--accent)" : "var(--border)"),
        borderRadius: "var(--radius-sm)",
        boxShadow: bell ? "var(--glow-bell)" : "none",
        display: "flex",
        flexDirection: "column",
        cursor: "pointer",
        overflow: "hidden",
        position: "relative",
        opacity: loading ? 0.6 : 1,
        pointerEvents: loading ? "none" : undefined,
        transition: "border-color var(--t-fast), border-left-color var(--t-fast), box-shadow var(--t-fast)",
        ...style,
      }}
    >
      <div
        style={{
          height: "var(--tile-header-height)",
          padding: "0 10px",
          background: "var(--bg-header)",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "var(--space-xs)",
          flexShrink: 0,
        }}
      >
        {bell ? (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              minWidth: "16px",
              height: "16px",
              padding: "0 3px",
              borderRadius: "8px",
              background: "var(--bell)",
              color: "#0D1117",
              fontSize: "9px",
              fontWeight: 700,
              lineHeight: 1,
              flexShrink: 0,
              marginRight: "var(--space-sm)",
            }}
          >
            {bellCount}
          </span>
        ) : null}
        <span
          style={{
            fontSize: "var(--text-md)",
            fontWeight: "var(--weight-medium)",
            color: "var(--text)",
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            flex: 1,
          }}
        >
          {name}
        </span>
        {meta ? (
          <span
            style={{
              fontSize: "var(--text-xs)",
              color: "var(--text-muted)",
              whiteSpace: "nowrap",
              marginLeft: "var(--space-md)",
              opacity: hover ? 0 : 1,
              transition: "opacity var(--t-fast)",
            }}
          >
            {meta}
          </span>
        ) : null}
      </div>
      <div style={{ flex: 1, overflow: "hidden", position: "relative", background: "var(--terminal-bg)" }}>
        <pre
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: "6px 8px",
            fontFamily: PREVIEW_FONT,
            fontSize: "var(--text-xs)",
            lineHeight: "var(--leading-preview)",
            color: "var(--terminal-fg)",
            whiteSpace: "pre",
            overflow: "hidden",
            margin: 0,
          }}
        >
          {preview}
        </pre>
        {deviceTag ? (
          <span
            style={{
              position: "absolute",
              right: "6px",
              bottom: "4px",
              zIndex: "var(--z-raised)",
              maxWidth: "45%",
              padding: "1px 5px",
              border: "1px solid var(--border-subtle)",
              borderRadius: "3px",
              background: "var(--bg-header)",
              color: "var(--text-muted)",
              fontFamily: "var(--font-ui)",
              fontSize: "var(--text-2xs)",
              lineHeight: "var(--leading-ui)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              pointerEvents: "none",
            }}
          >
            {deviceTag}
          </span>
        ) : null}
      </div>
    </div>
  );
}
