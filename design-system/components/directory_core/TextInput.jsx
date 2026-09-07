import React from "react";

const SEARCH_MASK =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cline x1='16.5' y1='16.5' x2='21' y2='21'/%3E%3C/svg%3E\") center/contain no-repeat";

/** Every text field in the product: the sidebar filter, the write-token
 *  password box, the add-service grid fields and the pairing inputs. */
export function TextInput({ size = "md", search = false, style, ...rest }) {
  const sizes = {
    filter: { padding: "7px 10px 7px 28px", fontSize: "13px", borderRadius: "6px", background: "var(--alt)" },
    sm: { padding: "8px 10px", fontSize: "13px", borderRadius: "7px", background: "var(--panel)" },
    md: { padding: "9px 12px", fontSize: "13.5px", borderRadius: "7px", background: "var(--panel)" },
  };
  const [focused, setFocused] = React.useState(false);
  const input = (
    <input
      onFocus={(e) => { setFocused(true); rest.onFocus && rest.onFocus(e); }}
      onBlur={(e) => { setFocused(false); rest.onBlur && rest.onBlur(e); }}
      style={{
        width: "100%",
        color: "var(--text)",
        fontFamily: "var(--font-ui)",
        border: "1px solid " + (focused ? "var(--accent)" : "var(--border-strong)"),
        boxShadow: focused ? "var(--ring-focus)" : "none",
        outline: "none",
        ...(sizes[size] || sizes.md),
        ...style,
      }}
      {...rest}
    />
  );
  if (!search) return input;
  return (
    <div style={{ position: "relative", flex: 1 }}>
      <span
        aria-hidden="true"
        style={{
          content: "''",
          position: "absolute",
          left: "10px",
          top: "50%",
          transform: "translateY(-50%)",
          width: "13px",
          height: "13px",
          background: "var(--text-faint)",
          WebkitMask: SEARCH_MASK,
          mask: SEARCH_MASK,
          pointerEvents: "none",
        }}
      />
      {input}
    </div>
  );
}
