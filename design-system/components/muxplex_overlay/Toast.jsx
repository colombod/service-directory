import React from "react";

/** Bottom-centre transient confirmation. Non-interactive by design. */
export function Toast({ children, style }) {
  return (
    <div
      style={{
        position: "absolute",
        bottom: "80px",
        left: "50%",
        transform: "translateX(-50%)",
        background: "var(--bg-header)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-sm)",
        padding: "var(--space-md) var(--space-xl)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        color: "var(--text-muted)",
        zIndex: "var(--z-popover)",
        pointerEvents: "none",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Anchored popup. One mechanism drives every instance; content is policy. */
export function Menu({ items = [], onSelect, style }) {
  return (
    <div
      role="menu"
      style={{
        position: "absolute",
        minWidth: "180px",
        background: "var(--bg-secondary)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-popover)",
        zIndex: "var(--z-popover)",
        padding: "var(--space-xs) 0",
        ...style,
      }}
    >
      {items.map((it) => (
        <MenuItem key={it.label} item={it} onSelect={onSelect} />
      ))}
    </div>
  );
}

function MenuItem({ item, onSelect }) {
  const [hover, setHover] = React.useState(false);
  return (
    <button
      type="button"
      role="menuitem"
      onClick={() => onSelect && onSelect(item)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-md)",
        width: "100%",
        padding: "var(--space-sm) var(--space-lg)",
        background: hover ? "var(--accent-dim)" : "transparent",
        border: "none",
        color: item.tone === "err" ? "var(--err)" : "var(--text)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        textAlign: "left",
        cursor: "pointer",
      }}
    >
      {item.label}
    </button>
  );
}

/** Backdrop + centred dialog that takes over. */
export function Modal({ open = true, title, onClose, children, width = 520 }) {
  if (!open) return null;
  return (
    <div style={{ position: "absolute", inset: 0, zIndex: "var(--z-modal-backdrop)" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "var(--bg-overlay)" }} />
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: "var(--z-modal)",
          width: width + "px",
          maxWidth: "92%",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-modal)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "var(--space-lg)",
            borderBottom: "1px solid var(--border-subtle)",
          }}
        >
          <h2 style={{ margin: 0, fontSize: "var(--text-lg)", fontWeight: "var(--weight-semibold)", color: "var(--text)" }}>
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              fontSize: "var(--text-xl)",
              lineHeight: 1,
              cursor: "pointer",
            }}
          >
            &times;
          </button>
        </div>
        <div style={{ padding: "var(--space-lg)" }}>{children}</div>
      </div>
    </div>
  );
}

/** Bottom-anchored panel for touch viewports. Rounded on the exposed corners
 *  only, square against the edges it is anchored to. */
export function BottomSheet({ open = true, items = [], onSelect, onClose }) {
  if (!open) return null;
  return (
    <div style={{ position: "absolute", inset: 0, zIndex: "var(--z-panel)", display: "flex", alignItems: "flex-end" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "var(--bg-overlay)" }} />
      <div
        style={{
          position: "relative",
          width: "100%",
          background: "var(--bg-header)",
          borderTop: "1px solid var(--border)",
          borderRadius: "var(--radius-lg) var(--radius-lg) 0 0",
          maxHeight: "var(--sheet-max-height)",
          overflowY: "auto",
        }}
      >
        <div style={{ width: "36px", height: "4px", background: "var(--border)", borderRadius: "2px", margin: "10px auto 6px" }} />
        <ul style={{ listStyle: "none", margin: 0, padding: "0 0 var(--space-md)" }}>
          {items.map((it) => (
            <SheetItem key={it.name} item={it} onSelect={onSelect} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function SheetItem({ item, onSelect }) {
  const [hover, setHover] = React.useState(false);
  return (
    <li
      onClick={() => onSelect && onSelect(item)}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "0 var(--space-xl)",
        height: "56px",
        cursor: "pointer",
        fontSize: "var(--text-lg)",
        color: "var(--text)",
        borderBottom: "1px solid var(--border-subtle)",
        background: hover ? "var(--accent-dim)" : "transparent",
        transition: "background var(--t-fast)",
      }}
    >
      {item.bell ? <span style={{ color: "var(--bell)" }}>&#9679;</span> : null}
      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name}</span>
      {item.time ? <span style={{ fontSize: "var(--text-sm)", color: "var(--text-dim)" }}>{item.time}</span> : null}
    </li>
  );
}
