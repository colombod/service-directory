// Resolved catalogue, shaped like GET /api/services. Addresses are tailnet-first.
function links(port, path) {
  return [
    { label: "Tailnet", url: "http://100.111.191.22:" + port + (path || "/") },
    { label: "LAN", url: "http://192.168.1.86:" + port + (path || "/") },
  ];
}
window.NODES = [
  { name: "node-a", description: "Home lab tailnet node", role: "primary" },
  { name: "node-b", description: "Studio mini", role: null },
];
window.CATALOGUE = [
  { name: "Resolve", origin: "node-a", description: "Amplifier Resolve dot-graph pipeline runner",
    category: "pipelines", tags: ["video", "editor"], icon: "🎬", owner: "amplifier-team",
    docs_url: "https://example.invalid/docs/resolve", view_kind: "iframe", source: "static", links: links(8080) },
  { name: "Context Intelligence", origin: "node-a", description: "Status endpoint, auto-refresh 30s",
    view_kind: "json", view_refresh_seconds: 30, source: "static", links: links(8000, "/status") },
  { name: "muxplex", origin: "node-a", description: "tmux session dashboard",
    category: "tools", view_kind: "iframe", source: "static", links: links(8088) },
  { name: "muxterm", origin: "node-a", description: "Browser terminal", source: "dynamic", links: links(8311) },
  { name: "browser-bridge hub", origin: "node-b", description: "Chrome relay", source: "static", links: links(8900) },
  { name: "grafana", origin: "node-b", description: "Metrics — refuses framing",
    category: "observability", view_kind: "auto", source: "static", links: links(3000) },
];
window.HEALTH = { Resolve: "up", "Context Intelligence": "up", muxplex: "up", muxterm: "down",
  "browser-bridge hub": "up", grafana: "up" };
window.STATUS_JSON = { status: "ok", version: "0.1.0", queued: 3, degraded: false,
  peers: [{ name: "node-b", reachable: true, version: "0.1.0" }], last_error: null };
