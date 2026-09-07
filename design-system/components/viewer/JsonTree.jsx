import React from "react";

function Value({ value }) {
  if (value === null) return <span style={{ color: "var(--text-faint)", fontStyle: "italic" }}>null</span>;
  if (typeof value === "string") return <span style={{ color: "var(--up)" }}>"{value}"</span>;
  if (typeof value === "number") return <span style={{ color: "var(--json-num)" }}>{String(value)}</span>;
  if (typeof value === "boolean") return <span style={{ color: "var(--json-bool)" }}>{String(value)}</span>;
  return null;
}

function Node({ k, value, depth }) {
  const isObj = value && typeof value === "object";
  const key = k === undefined ? null : <span style={{ color: "var(--accent)", fontWeight: 600 }}>{k}: </span>;
  if (!isObj) {
    return (
      <li>
        {key}
        <Value value={value} />
      </li>
    );
  }
  const entries = Array.isArray(value) ? value.map((v, i) => [i, v]) : Object.entries(value);
  return (
    <li>
      <details open={depth < 2}>
        <summary style={{ cursor: "pointer", listStyle: "none" }}>
          {key}
          <span style={{ color: "var(--text-faint)" }}>{Array.isArray(value) ? "[…]" : "{…}"}</span>
        </summary>
        <ul style={{ listStyle: "none", margin: "0 0 0 18px", padding: 0 }}>
          {entries.map(([ck, cv]) => (
            <Node key={String(ck)} k={ck} value={cv} depth={depth + 1} />
          ))}
        </ul>
      </details>
    </li>
  );
}

/** Collapsible JSON tree for json-kind services, fetched through /api/view-proxy. */
export function JsonTree({ data, style }) {
  return (
    <div style={{ flex: 1, overflow: "auto", padding: "18px 24px", fontFamily: "var(--mono)", fontSize: "13px", ...style }}>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        <Node value={data} depth={0} />
      </ul>
    </div>
  );
}
