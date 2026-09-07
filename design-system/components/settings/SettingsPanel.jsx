import React from "react";

/** Right-anchored, full-height settings overlay. The only scrim in the product. */
export function SettingsPanel({ open = true, title = "Settings", onClose, children }) {
  if (!open) return null;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "var(--scrim)",
        zIndex: 100,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "flex-end",
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "480px",
          maxWidth: "100%",
          height: "100%",
          overflowY: "auto",
          background: "var(--panel)",
          borderLeft: "1px solid var(--border)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "18px 20px 14px",
            borderBottom: "1px solid var(--border)",
            flexShrink: 0,
          }}
        >
          <h2 style={{ margin: 0, fontSize: "16px", fontWeight: 700, flex: 1 }}>{title}</h2>
          <button
            type="button"
            onClick={onClose}
            title="Close settings"
            style={{
              border: "none",
              background: "none",
              fontSize: "22px",
              cursor: "pointer",
              color: "var(--text-muted)",
              padding: "0 4px",
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>{children}</div>
      </div>
    </div>
  );
}

export function SettingsSection({ title, children, style }) {
  return (
    <div style={{ padding: "18px 20px", borderBottom: "1px solid var(--border)", ...style }}>
      <h3
        style={{
          margin: "0 0 12px",
          fontSize: "12px",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: ".06em",
          color: "var(--text-muted)",
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

/** Uppercase-label / value grid used for node identity. */
export function KeyValueList({ items = [] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "130px 1fr", gap: "6px 12px", fontSize: "13px", margin: "0 0 8px" }}>
      {items.map((it) => (
        <React.Fragment key={it.label}>
          <dt
            style={{
              color: "var(--text-faint)",
              fontWeight: 600,
              fontSize: "11px",
              textTransform: "uppercase",
              letterSpacing: ".04em",
              paddingTop: "2px",
            }}
          >
            {it.label}
          </dt>
          <dd style={{ margin: 0, color: "var(--text)", wordBreak: "break-all" }}>{it.value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
