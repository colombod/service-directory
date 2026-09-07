import React from "react";

function Meta({ label, children }) {
  return (
    <div style={{ marginBottom: "10px", fontSize: "13px" }}>
      <span
        style={{
          color: "var(--text-faint)",
          fontSize: "11px",
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: ".05em",
          marginRight: "8px",
        }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}

/** The detail view a row click opens: metadata, external links, and the single
 *  primary "Open here" action. */
export function ServiceDetail({ service, status = "unknown", onOpenHere }) {
  const links = service.links || [];
  const canView = Boolean(service.view_url || (links[0] && links[0].url));
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "28px 32px" }}>
      <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "0 0 10px", letterSpacing: "-.01em" }}>
        {service.name}
      </h2>
      {service.description ? (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", margin: "0 0 16px", lineHeight: 1.5 }}>
          {service.description}
        </p>
      ) : null}
      {service.category ? <Meta label="Category">{service.category}</Meta> : null}
      {service.tags && service.tags.length ? <Meta label="Tags">{service.tags.join(", ")}</Meta> : null}
      <Meta label="Health">
        <span style={{ fontWeight: 600 }}>{status}</span>
      </Meta>
      {service.docs_url ? (
        <Meta label="Docs">
          <a
            href={service.docs_url}
            target="_blank"
            rel="noopener"
            style={{ color: "var(--accent)", fontWeight: 600, fontSize: "13px", textDecoration: "none" }}
          >
            Documentation &#8599;
          </a>
        </Meta>
      ) : null}
      {links.length ? (
        <Meta label="Open externally">
          {links.map((l) => (
            <a
              key={l.label}
              href={l.url}
              target="_blank"
              rel="noopener"
              style={{
                fontSize: "12px",
                color: "var(--accent)",
                border: "1px solid var(--border-strong)",
                padding: "3px 8px",
                borderRadius: "5px",
                marginRight: "6px",
                display: "inline-block",
                textDecoration: "none",
              }}
            >
              {l.label}
            </a>
          ))}
        </Meta>
      ) : null}
      <div style={{ marginTop: "20px" }}>
        {canView ? (
          <button
            type="button"
            onClick={() => onOpenHere && onOpenHere(service)}
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "#fff",
              background: "var(--accent)",
              border: "none",
              borderRadius: "7px",
              padding: "9px 22px",
              cursor: "pointer",
            }}
          >
            Open here
          </button>
        ) : (
          <span style={{ fontSize: "13px", color: "var(--text-faint)" }}>
            No in-app view configured for this service
          </span>
        )}
      </div>
    </div>
  );
}
