// Shapes match GET /api/services and GET /api/federation/nodes. Addresses are
// tailnet-first, exactly as the resolver orders them.
function links(port, path) {
  return [
    { label: "Tailnet", url: "http://100.111.191.22:" + port + (path || "/") },
    { label: "LAN", url: "http://192.168.1.86:" + port + (path || "/") },
  ];
}
window.NODE = { name: "node-a", role: "primary", version: "0.1.0",
  base_url: "http://100.111.191.22:80", description: "Home lab tailnet node", federation_enabled: true };
window.NODES = [
  { name: "node-a", description: "Home lab tailnet node", reachable: true },
  { name: "node-b", description: "Studio mini", reachable: true },
];
window.SERVICES = [
  { name: "Resolve", origin: "node-a", category: "pipelines", tags: ["video", "editor"], icon: "🎬",
    owner: "amplifier-team", docs_url: "https://example.invalid/docs/resolve", view_kind: "iframe",
    source: "static", health: "up", attention: 0, links: links(8080),
    description: "Amplifier Resolve dot-graph pipeline runner" },
  { name: "Context Intelligence", origin: "node-a", view_kind: "json", view_refresh_seconds: 30,
    source: "static", health: "up", attention: 0, links: links(8000, "/status"),
    description: "Status endpoint — rendered as a JSON tree, auto-refresh 30s" },
  { name: "muxplex", origin: "node-a", category: "tools", view_kind: "iframe", source: "static",
    health: "up", attention: 0, links: links(8088), description: "tmux session dashboard across devices" },
  { name: "muxterm", origin: "node-a", source: "dynamic", ttl: 90, view_kind: "iframe",
    health: "down", attention: 1, links: links(8311),
    description: "Browser terminal — registered at runtime, heartbeat overdue" },
  { name: "browser-bridge hub", origin: "node-b", source: "static", view_kind: "iframe",
    health: "up", attention: 0, links: links(8900), description: "Chrome relay for headless drivers" },
  { name: "grafana", origin: "node-b", category: "observability", view_kind: "auto", source: "static",
    health: "up", attention: 0, links: links(3000), description: "Metrics — sends X-Frame-Options, refuses framing" },
];
window.STATUS_JSON = { status: "ok", version: "0.1.0", queued: 3, degraded: false,
  peers: [{ name: "node-b", reachable: true, version: "0.1.0" }], last_error: null };
