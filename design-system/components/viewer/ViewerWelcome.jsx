import React from "react";

const ICON_MASK =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Cpath d='M3 9h18M9 21V9'/%3E%3C/svg%3E\") center/22px no-repeat";

/** The viewer pane's default state: a masked panel-layout glyph and one line
 *  telling the user what the pane is for. */
export function ViewerWelcome({
  title = "Select a service to open it here",
  hint = "Pick a service to open it here \u2014 without leaving the directory.",
}) {
  return (
    <div style={{ padding: "56px 32px 40px", textAlign: "center", borderBottom: "1px solid var(--border)" }}>
      <div
        style={{
          width: "44px",
          height: "44px",
          margin: "0 auto 16px",
          borderRadius: "11px",
          background: "var(--accent)",
          WebkitMask: ICON_MASK,
          mask: ICON_MASK,
        }}
      />
      <h2
        style={{
          fontSize: "17px",
          fontWeight: 650,
          color: "var(--text)",
          margin: "0 0 8px",
          letterSpacing: "-.01em",
        }}
      >
        {title}
      </h2>
      <p style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--text-muted)", margin: "0 auto", maxWidth: "440px" }}>
        {hint}
      </p>
    </div>
  );
}

/** Viewer toolbar shown above an embedded service. */
export function ViewerHeader({ name, url, actions, onClose }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "12px",
        padding: "10px 18px",
        borderBottom: "1px solid var(--border)",
        background: "var(--alt)",
        flexShrink: 0,
      }}
    >
      <span style={{ fontWeight: 600, fontSize: "14px", flex: 1 }}>{name}</span>
      {actions}
      {url ? (
        <a href={url} target="_blank" rel="noopener" style={{ fontSize: "12px", color: "var(--accent)", textDecoration: "none" }}>
          open in new tab &#8599;
        </a>
      ) : null}
      <button
        type="button"
        onClick={onClose}
        style={{
          border: "1px solid var(--border-strong)",
          background: "var(--panel)",
          color: "var(--text-muted)",
          borderRadius: "5px",
          padding: "4px 10px",
          fontSize: "12px",
          cursor: "pointer",
        }}
      >
        Close
      </button>
    </div>
  );
}

/** Shown when a service refuses framing or is unreachable. Never a dead end. */
export function ViewerFallback({ name, url, reason }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px",
        textAlign: "center",
      }}
    >
      <p style={{ fontSize: "16px", fontWeight: 600, color: "var(--text)", margin: "0 0 8px" }}>{name}</p>
      <p style={{ color: "var(--text-muted)", fontSize: "13px", margin: "0 0 20px" }}>{reason}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener"
        style={{
          fontSize: "14px",
          fontWeight: 600,
          color: "var(--accent)",
          border: "1px solid var(--accent)",
          padding: "8px 18px",
          borderRadius: "7px",
          textDecoration: "none",
        }}
      >
        Open {name} in a new tab &#8599;
      </a>
    </div>
  );
}
