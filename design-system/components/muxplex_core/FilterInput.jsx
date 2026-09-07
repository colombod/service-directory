import React from "react";

/** The filter field. It must CLEARLY read as a typable field — it carries a
 *  real surface and border at rest, unlike QuickLink beside it. */
export function FilterInput({ value = "", onValueChange, onClear, caption, style, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  const [hover, setHover] = React.useState(false);
  const field = (
    <div style={{ position: "relative", display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
      <input
        value={value}
        onChange={(e) => onValueChange && onValueChange(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          fontSize: "var(--text-md)",
          fontFamily: "var(--font-ui)",
          color: "var(--text)",
          background: "var(--bg-surface)",
          border: "1px solid " + (focus || hover ? "var(--accent)" : "var(--border)"),
          borderRadius: "var(--radius-sm)",
          padding: "4px 24px 4px 10px",
          maxWidth: caption ? "none" : "140px",
          minWidth: 0,
          flex: caption ? 1 : undefined,
          outline: focus ? "var(--focus-ring)" : "none",
          outlineOffset: "1px",
          ...style,
        }}
        {...rest}
      />
      {value ? (
        <button
          type="button"
          onClick={onClear}
          aria-label="Clear filter"
          style={{
            position: "absolute",
            right: "6px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: "16px",
            height: "16px",
            padding: 0,
            background: "transparent",
            border: "none",
            borderRadius: "3px",
            color: "var(--text-muted)",
            fontSize: "15px",
            lineHeight: 1,
            cursor: "pointer",
          }}
        >
          &times;
        </button>
      ) : null}
    </div>
  );
  if (!caption) return field;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "var(--space-sm)", minWidth: 0 }}>
      <span
        style={{
          fontSize: "var(--text-xs)",
          fontWeight: "var(--weight-semibold)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-caps)",
          color: "var(--text-muted)",
          flexShrink: 0,
        }}
      >
        {caption}
      </span>
      {field}
    </div>
  );
}

/** A labelled input row inside a settings panel: label, control, helper. */
export function Field({ label, helper, children }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-sm)", marginBottom: "var(--space-lg)" }}>
      <label style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>{label}</label>
      {children}
      {helper ? <span style={{ fontSize: "var(--text-xs)", color: "var(--text-dim)" }}>{helper}</span> : null}
    </div>
  );
}
