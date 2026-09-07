// Sample fleet. Session names and previews are illustrative; the shapes match
// what /api/sessions returns in muxplex.
window.SESSIONS = [
  { id: "api", name: "api", device: "macbook", meta: "3w · 2m", bell: 0,
    preview: "$ uv run pytest -q\n....................................\n412 passed, 3 skipped in 18.42s\n$ " },
  { id: "deploy", name: "deploy", device: "macbook", meta: "1w · now", bell: 2,
    preview: "release 0.48.0 → staging\n  ✓ wheel built\n  ✓ smoke passed\n? Promote to production (y/N) " },
  { id: "web", name: "web", device: "macbook", meta: "2w · 6m", bell: 0,
    preview: "VITE v5.4.2  ready in 402 ms\n\n  ➜  Local:   http://localhost:5173/\n  ➜  Network: http://100.111.191.22:5173/" },
  { id: "resolve", name: "resolve", device: "nuc", meta: "5w · 12m", bell: 0,
    preview: "resolve: dot-graph pipeline\n  [ok] ingest        1.2s\n  [ok] transcode     44.8s\n  [··] assemble" },
  { id: "ctx", name: "context-intel", device: "nuc", meta: "1w · 31m", bell: 0,
    preview: "GET /status 200 · 14ms\nGET /status 200 · 11ms\nGET /status 200 · 12ms" },
  { id: "logs", name: "logs", device: "nuc", meta: "1w · 4h", bell: 0,
    preview: "2026-09-06T18:02:11Z peer node-b unreachable, omitted\n2026-09-06T18:02:12Z catalogue rendered (11 services)" },
];
window.DEVICES = ["macbook", "nuc"];
