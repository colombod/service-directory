import React from "react";
import { HealthPill } from "./HealthPill.jsx";
import { CategoryChip, TagList } from "./CategoryChip.jsx";
import { AddressLink } from "./AddressLink.jsx";

/** One catalogue row. The service NAME is a real button — opening in-app is the
 *  default action and must be in the accessibility tree. */
export function ServiceRow({
  service,
  status = "unknown",
  selected = false,
  compact = false,
  onOpen,
  onRemove,
}) {
  const [hover, setHover] = React.useState(false);
  const cell = { padding: "8px 14px", borderBottom: "1px solid var(--border)", verticalAlign: "middle" };
  const links = service.links || [];
  return (
    <tr
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={() => onOpen && onOpen(service)}
      style={{ background: hover || selected ? "var(--accent-weak)" : "transparent", cursor: "pointer" }}
    >
      <td style={{ ...cell, whiteSpace: "nowrap" }}>
        {service.icon ? <span style={{ marginRight: "6px" }}>{service.icon}</span> : null}
        <button
          type="button"
          title={"Open " + service.name + " here, in this page"}
          onClick={(e) => { e.stopPropagation(); onOpen && onOpen(service); }}
          style={{
            font: "inherit",
            fontFamily: "var(--font-ui)",
            fontWeight: 600,
            fontSize: "13px",
            color: "var(--text)",
            background: "none",
            border: "none",
            padding: 0,
            cursor: "pointer",
          }}
        >
          {service.name}
        </button>
        {service.category ? <CategoryChip>{service.category}</CategoryChip> : null}
      </td>
      {compact ? null : (
        <td style={{ ...cell, color: "var(--text-muted)", fontSize: "12px", maxWidth: "200px" }}>
          {service.description}
          {service.tags && service.tags.length ? <TagList tags={service.tags} /> : null}
        </td>
      )}
      <td style={{ ...cell, whiteSpace: "nowrap" }}>
        <HealthPill status={status} />
      </td>
      {compact ? null : (
        <td style={{ ...cell, whiteSpace: "nowrap" }}>
          {links.map((l, i) => (
            <span key={l.label} style={{ marginRight: "4px" }}>
              <AddressLink label={l.label} href={l.url} variant={i === 0 ? "primary" : "secondary"} />
            </span>
          ))}
        </td>
      )}
      {compact ? null : (
        <td style={{ ...cell, whiteSpace: "nowrap" }}>
          <span style={{ fontSize: "11px", color: "var(--text-faint)" }}>
            {service.owner ? <span style={{ marginRight: "8px" }}>{service.owner}</span> : null}
            {service.docs_url ? (
              <a href={service.docs_url} style={{ color: "var(--accent)", fontWeight: 600, textDecoration: "none" }}>
                docs
              </a>
            ) : null}
          </span>
        </td>
      )}
      <td style={{ ...cell, textAlign: "right", width: "32px" }}>
        {service.source === "dynamic" && onRemove ? (
          <button
            type="button"
            title={"Remove " + service.name}
            onClick={(e) => { e.stopPropagation(); onRemove(service); }}
            style={{
              border: "none",
              background: "none",
              color: "var(--text-faint)",
              fontSize: "16px",
              cursor: "pointer",
              padding: "0 3px",
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        ) : null}
      </td>
    </tr>
  );
}
