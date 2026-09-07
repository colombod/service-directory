import React from "react";

/** One trusted peer: name, monospace base URL, reachability, remove ×. */
export function PeerItem({ name, baseUrl, reachable = "unknown", onRemove, last = false }) {
  const badge =
    reachable === "up"
      ? { color: "var(--up)", background: "var(--up-bg)" }
      : { color: "var(--unknown)", background: "var(--unknown-bg)" };
  return (
    <li
      style={{
        display: "flex",
        alignItems: "center",
        gap: "10px",
        padding: "8px 0",
        borderBottom: last ? "none" : "1px solid var(--border)",
        fontSize: "13px",
      }}
    >
      <span style={{ fontWeight: 600, flex: 1 }}>{name}</span>
      <span style={{ color: "var(--text-muted)", fontSize: "11px", fontFamily: "var(--mono)" }}>{baseUrl}</span>
      <span style={{ fontSize: "10px", fontWeight: 600, padding: "1px 6px", borderRadius: "4px", ...badge }}>
        {reachable === "up" ? "reachable" : "unknown"}
      </span>
      <button
        type="button"
        onClick={onRemove}
        title={"Remove " + name}
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
    </li>
  );
}

/** The issued one-time pairing code and its TTL. */
export function PairingCode({ code, ttlSeconds = 600 }) {
  return (
    <div
      style={{
        marginTop: "10px",
        padding: "10px 14px",
        background: "var(--alt)",
        border: "1px solid var(--border-strong)",
        borderRadius: "7px",
        fontSize: "13px",
      }}
    >
      <span style={{ fontFamily: "var(--mono)", fontWeight: 700, fontSize: "15px", color: "var(--accent)", letterSpacing: ".05em" }}>
        {code}
      </span>
      <div style={{ color: "var(--text-faint)", fontSize: "11px", marginTop: "4px" }}>
        Expires in {ttlSeconds}s (one-time use)
      </div>
    </div>
  );
}
