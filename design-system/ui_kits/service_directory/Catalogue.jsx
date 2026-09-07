/* The left rail: one section per origin node, each a uniform table.
   Declutter rule from the app: the narrow rail shows name + category + status. */
function HealthPill({ status }) {
  const map = {
    up: { color: "var(--sd-up)", background: "var(--sd-up-bg)" },
    down: { color: "var(--sd-down)", background: "var(--sd-down-bg)" },
    unknown: { color: "var(--sd-unknown)", background: "var(--sd-unknown-bg)" },
  };
  const s = map[status] || map.unknown;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: "10.5px",
      fontWeight: 600, padding: "2px 7px", borderRadius: 4, textTransform: "capitalize", ...s }}>
      <span style={{ fontSize: 6, lineHeight: 1 }}>●</span>{status}
    </span>
  );
}

function ServiceRow({ svc, status, selected, onOpen, onRemove }) {
  const [hot, setHot] = React.useState(false);
  const cell = { padding: "8px 14px", borderBottom: "1px solid var(--sd-border)", verticalAlign: "middle" };
  return (
    <tr onClick={() => onOpen(svc)} onMouseEnter={() => setHot(true)} onMouseLeave={() => setHot(false)}
      style={{ background: hot || selected ? "var(--sd-accent-weak)" : "transparent", cursor: "pointer" }}>
      <td style={{ ...cell, whiteSpace: "nowrap" }}>
        {svc.icon ? <span style={{ marginRight: 6 }}>{svc.icon}</span> : null}
        <button type="button" title={"Open " + svc.name + " here, in this page"}
          onClick={(e) => { e.stopPropagation(); onOpen(svc); }}
          style={{ fontWeight: 600, fontSize: 13, color: "var(--sd-text)", background: "none",
            border: "none", padding: 0, cursor: "pointer" }}>{svc.name}</button>
        {svc.category ? (
          <span style={{ marginLeft: 7, fontSize: 10, fontWeight: 600, color: "var(--sd-accent)",
            background: "var(--sd-accent-weak)", padding: "1px 6px", borderRadius: 4 }}>{svc.category}</span>
        ) : null}
      </td>
      <td style={{ ...cell, whiteSpace: "nowrap" }}><HealthPill status={status} /></td>
      <td style={{ ...cell, textAlign: "right", width: 32 }}>
        {svc.source === "dynamic" ? (
          <button type="button" title={"Remove " + svc.name}
            onClick={(e) => { e.stopPropagation(); onRemove(svc); }}
            style={{ border: "none", background: "none", color: "var(--sd-text-faint)", fontSize: 16,
              cursor: "pointer", padding: "0 3px", lineHeight: 1 }}>×</button>
        ) : null}
      </td>
    </tr>
  );
}

function NodeGroup({ node, rows, health, selected, onOpen, onRemove }) {
  if (!rows.length) return null;
  return (
    <section data-origin={node.name} style={{ marginBottom: 4 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "6px 14px 4px" }}>
        <h2 style={{ margin: 0, fontSize: "10.5px", fontWeight: 700, textTransform: "uppercase",
          letterSpacing: ".06em", color: "var(--sd-text-muted)" }}>{node.name}</h2>
        <span style={{ fontSize: 10, fontWeight: 600, color: "var(--sd-up)", display: "inline-flex",
          alignItems: "center", gap: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />reachable
        </span>
        {node.description ? (
          <span style={{ fontSize: 11, color: "var(--sd-text-faint)" }}>— {node.description}</span>
        ) : null}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <tbody>
          {rows.map((s) => (
            <ServiceRow key={s.name} svc={s} status={health[s.name] || "unknown"}
              selected={selected === s.name} onOpen={onOpen} onRemove={onRemove} />
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Sidebar({ collapsed, filter, setFilter, services, health, selected, onOpen, onRemove, onCollapse }) {
  const MASK = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E\") center/contain no-repeat";
  const [focus, setFocus] = React.useState(false);
  return (
    <nav style={{ width: collapsed ? 0 : "var(--sd-sidebar-width)", minWidth: collapsed ? 0 : 220,
      flexShrink: 0, borderRight: collapsed ? "none" : "1px solid var(--sd-border)", display: "flex",
      flexDirection: "column", overflow: "hidden", background: "var(--sd-panel)" }}>
      <div style={{ padding: "14px 14px 8px", borderBottom: "1px solid var(--sd-border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ position: "relative", flex: 1 }}>
            <span aria-hidden="true" style={{ position: "absolute", left: 10, top: "50%",
              transform: "translateY(-50%)", width: 13, height: 13, background: "var(--sd-text-faint)",
              WebkitMask: MASK, mask: MASK, pointerEvents: "none" }} />
            <input value={filter} onChange={(e) => setFilter(e.target.value)}
              onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
              aria-label="Filter services by name, description, tag, or origin" placeholder="Filter…"
              style={{ width: "100%", padding: "7px 10px 7px 28px", fontSize: 13, color: "var(--sd-text)",
                background: "var(--sd-alt)", border: "1px solid " + (focus ? "var(--sd-accent)" : "var(--sd-border-strong)"),
                borderRadius: 6, outline: "none", boxShadow: focus ? "var(--sd-ring-focus)" : "none" }} />
          </div>
          <button onClick={onCollapse} title="Collapse sidebar" aria-expanded="true"
            style={{ flexShrink: 0, border: "1px solid var(--sd-border-strong)", background: "var(--sd-alt)",
              color: "var(--sd-text-muted)", borderRadius: 6, padding: "5px 9px", fontSize: 13,
              cursor: "pointer", lineHeight: 1 }}>«</button>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 0" }}>
        {window.NODES.map((n) => (
          <NodeGroup key={n.name} node={n} rows={services.filter((s) => s.origin === n.name)}
            health={health} selected={selected} onOpen={onOpen} onRemove={onRemove} />
        ))}
        {services.length === 0 ? (
          <p style={{ padding: "20px 14px", color: "var(--sd-text-muted)", fontSize: 13 }}>
            No services match this filter.
          </p>
        ) : null}
      </div>
    </nav>
  );
}
