import React from "react";

/** Chrome is words. A view/sort/back control is azure text with no box:
 *  --amp-azure at rest, --amp-azure-hover on hover or while expanded. */
export function AmpTextControl({ expanded, style, children, ...rest }) {
  const [hot, setHot] = React.useState(false);
  return (
    <button
      onMouseEnter={() => setHot(true)}
      onMouseLeave={() => setHot(false)}
      aria-expanded={expanded === undefined ? undefined : String(expanded)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--control-gap)",
        padding: "var(--control-pad-y) var(--control-pad-x)",
        background: "transparent",
        border: "none",
        borderRadius: "var(--radius-sm)",
        color: hot || expanded ? "var(--amp-interactive-hover)" : "var(--amp-interactive)",
        fontSize: "var(--text-md)",
        fontFamily: "var(--font-ui)",
        cursor: "pointer",
        transition: "color var(--t-fast)",
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

/** The one filter field. Azure border + 2px outline on focus; a × clears it.
 *  `wide` fills its container (rail); unset is the 150px header width. */
export function AmpFilter({ value, onChange, placeholder = "Filter", wide, style }) {
  const [hot, setHot] = React.useState(false);
  return (
    <div style={{ position: "relative", display: "flex", alignItems: "center", flex: wide ? 1 : undefined, ...style }}>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setHot(true)}
        onBlur={() => setHot(false)}
        style={{
          fontSize: "var(--text-md)",
          fontFamily: "var(--font-ui)",
          color: "var(--amp-ink)",
          background: "var(--amp-hover)",
          border: "1px solid " + (hot ? "var(--amp-interactive)" : "var(--amp-line)"),
          borderRadius: "var(--radius-sm)",
          padding: "4px 24px 4px 10px",
          width: wide ? "100%" : 150,
          outline: hot ? "2px solid var(--amp-interactive)" : "none",
          outlineOffset: 1,
        }}
      />
      {value ? (
        <button
          onClick={() => onChange("")}
          aria-label="Clear filter"
          style={{
            position: "absolute", right: 6, width: 16, height: 16, padding: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "transparent", border: "none", borderRadius: 3,
            color: "var(--amp-ink-muted)", fontSize: 15, lineHeight: 1, cursor: "pointer",
          }}
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
