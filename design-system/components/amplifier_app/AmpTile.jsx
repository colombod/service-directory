import React from "react";
import { AttentionBadge } from "./AmpHeader.jsx";

/** The left edge bar colour — the one channel that carries selection and
 *  attention. Violet wins over azure; --amp-line at rest. */
export function ampEdge({ attention = 0, selected, hot }) {
  if (attention > 0) return "var(--amp-attention)";
  if (selected || hot) return "var(--amp-interactive)";
  return "var(--amp-line)";
}

const TONES = {
  ok: "var(--amp-ok)",
  err: "var(--amp-err)",
  warn: "var(--amp-warn)",
  accent: "var(--amp-interactive)",
  attention: "var(--amp-attention)",
  dim: "var(--amp-ink-dim)",
};

/** Overview tile: equal weight, --tile-height tall, flat, a 3px left edge
 *  bar at all times, and a monospace preview well of the item's own output.
 *  Selection changes a colour, never a geometry. */
export function AmpTile({ name, status, statusTone = "dim", summary, preview, tag, attention = 0, onOpen, style }) {
  const [hot, setHot] = React.useState(false);
  const attn = attention > 0;
  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      style={{
        height: "var(--tile-height)",
        background: "var(--amp-raised)",
        border: "1px solid " + (attn ? "var(--amp-attention-edge)" : hot ? "var(--amp-interactive)" : "var(--amp-line)"),
        borderLeft: "3px solid " + ampEdge({ attention, hot }),
        borderRadius: "var(--radius-sm)",
        boxShadow: attn ? "0 0 0 1px var(--amp-attention-edge), inset 0 0 12px var(--amp-attention-soft)" : "none",
        display: "flex",
        flexDirection: "column",
        cursor: onOpen ? "pointer" : "default",
        overflow: "hidden",
        position: "relative",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)",
        ...style,
      }}
    >
      <div
        style={{
          height: "var(--tile-header-height)", padding: "0 10px", background: "var(--amp-page)",
          borderBottom: "1px solid var(--amp-line-subtle)", display: "flex", alignItems: "center",
          gap: "var(--space-sm)", flexShrink: 0,
        }}
      >
        {attn ? <AttentionBadge count={attention} /> : null}
        <span style={{ fontSize: "var(--text-md)", fontWeight: 500, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
        {status ? <span style={{ fontSize: "var(--text-xs)", whiteSpace: "nowrap", color: TONES[statusTone] }}>{status}</span> : null}
      </div>
      {summary ? (
        <div style={{ padding: "var(--space-md) 10px", borderBottom: "1px solid var(--amp-line-subtle)" }}>
          <p style={{ margin: 0, fontSize: "var(--text-sm)", color: "var(--amp-ink-muted)", lineHeight: 1.45 }}>{summary}</p>
        </div>
      ) : null}
      <div style={{ flex: 1, position: "relative", overflow: "hidden", background: "var(--amp-content)" }}>
        <pre
          style={{
            position: "absolute", bottom: 0, left: 0, right: 0, margin: 0, padding: "6px 8px",
            fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", lineHeight: 1.15,
            color: "var(--terminal-fg)", whiteSpace: "pre", overflow: "hidden",
          }}
        >
          {preview}
        </pre>
        {tag ? (
          <span
            style={{
              position: "absolute", right: 6, bottom: 4, maxWidth: "45%", padding: "1px 5px",
              border: "1px solid var(--amp-line-subtle)", borderRadius: 3, background: "var(--amp-page)",
              color: "var(--amp-ink-muted)", fontFamily: "var(--font-ui)", fontSize: "var(--text-2xs)",
              lineHeight: "var(--leading-ui)", whiteSpace: "nowrap", overflow: "hidden",
              textOverflow: "ellipsis", pointerEvents: "none",
            }}
          >
            {tag}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/** The overview grid: repeat(auto-fill, minmax(--tile-min-width, 1fr)). */
export function AmpTileGrid({ children, style }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(var(--tile-min-width), 1fr))",
        gap: "var(--grid-gap)",
        alignContent: "start",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Focused rail row: the same item, condensed. Same order, same edge
 *  colours as the tile it replaces. */
export function AmpRailRow({ name, status, statusTone = "dim", meta, attention = 0, selected, onOpen, style }) {
  const [hot, setHot] = React.useState(false);
  const attn = attention > 0;
  return (
    <div
      onClick={onOpen}
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      style={{
        background: selected ? "var(--amp-hover)" : "var(--amp-raised)",
        cursor: onOpen ? "pointer" : "default",
        border: "1px solid " + (attn ? "var(--amp-attention-edge)" : selected || hot ? "var(--amp-interactive)" : "var(--amp-line)"),
        borderLeft: "3px solid " + ampEdge({ attention, selected, hot }),
        borderRadius: "var(--radius-sm)",
        padding: "var(--space-md)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2xs)",
        boxShadow: attn ? "0 0 0 1px var(--amp-attention-edge), inset 0 0 12px var(--amp-attention-soft)" : "none",
        transition: "border-color var(--t-fast), box-shadow var(--t-fast)",
        ...style,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)" }}>
        {attn ? <AttentionBadge count={attention} small /> : null}
        <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
      </div>
      <div style={{ display: "flex", gap: "var(--space-sm)", fontSize: "var(--text-xs)" }}>
        {status ? <span style={{ color: TONES[statusTone] }}>{status}</span> : null}
        {meta ? <span style={{ color: "var(--amp-ink-dim)" }}>{meta}</span> : null}
      </div>
    </div>
  );
}
