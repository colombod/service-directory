import React from "react";
import { ServiceRow } from "./ServiceRow.jsx";
import { ReachableBadge } from "./CategoryChip.jsx";

/** A node-group section: uppercase origin heading, reachable badge, optional
 *  em-dash description, then that node's borderless table. */
export function NodeGroup({ origin, description, children, style }) {
  return (
    <section style={{ marginBottom: "4px", ...style }}>
      <div style={{ display: "flex", alignItems: "center", gap: "7px", padding: "6px 14px 4px" }}>
        <h2
          style={{
            margin: 0,
            fontSize: "10.5px",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: ".06em",
            color: "var(--text-muted)",
          }}
        >
          {origin}
        </h2>
        <ReachableBadge />
        {description ? (
          <span style={{ fontSize: "11px", color: "var(--text-faint)" }}>&mdash; {description}</span>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function ServiceTable({ services = [], health = {}, compact = false, selected, onOpen, onRemove }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        {services.map((s) => (
          <ServiceRow
            key={s.name}
            service={s}
            status={health[s.name] || "unknown"}
            selected={selected === s.name}
            compact={compact}
            onOpen={onOpen}
            onRemove={onRemove}
          />
        ))}
      </tbody>
    </table>
  );
}
