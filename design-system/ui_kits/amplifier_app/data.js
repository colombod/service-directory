// Replace with your app's items. "Run" is a placeholder for whatever unit
// your Amplifier app supervises — a build, a pipeline, a session, a service.
window.APP_NAME = "Resolve Runs";
window.ITEMS = [
  { id: "r-412", name: "service-directory · block 3", owner: "colombod", status: "needs-you", attention: 2,
    meta: "18m · 3 blocks", summary: "Self-management block finished; the resolver is asking whether to promote the wheel.",
    preview: "resolve: block 3 — self-management\n  [ok]  doctor checklist        12 checks\n  [ok]  systemd unit generated\n  [ok]  hermetic suite          412 passed\n  [??]  promote 0.1.0 to uv tool? (y/N) " },
  { id: "r-411", name: "muxplex · agent panel lane", owner: "bkrabach", status: "running", attention: 0,
    meta: "4m · 1 block", summary: "Migrating the panel to the layer ladder, one component per change.",
    preview: "resolve: migrate .agent-panel\n  [ok]  z-index 9000 → --z-panel\n  [ok]  shadow → --shadow-edge-left\n  [··]  bubbles → text on the page" },
  { id: "r-409", name: "tokens guard test", owner: "bkrabach", status: "ok", attention: 0,
    meta: "2h · 1 block", summary: "Structural guard: fails the build if a second tokens.css appears.",
    preview: "resolve: guard test\n  [ok]  walk repo for tokens.css   1 found\n  [ok]  shared names agree         13/13\n  done in 4.2s" },
  { id: "r-407", name: "federation · transitive merge", owner: "colombod", status: "failed", attention: 0,
    meta: "5h · 2 blocks", summary: "A peer of a peer was counted twice in the merged catalogue.",
    preview: "resolve: federation merge\n  [ok]  pair handshake\n  [!!]  transitive peers double-counted\n        expected 11 services, got 14" },
  { id: "r-402", name: "brand asset render", owner: "bkrabach", status: "ok", attention: 0,
    meta: "1d · 1 block", summary: "Regenerated icons, favicons, OG and lockups from the SVG sources.",
    preview: "render-brand-assets.py\n  icons/      11 files\n  favicons/    5 files\n  og/          2 files" },
  { id: "r-398", name: "context-intel · status endpoint", owner: "colombod", status: "idle", attention: 0,
    meta: "2d · 1 block", summary: "Idle since the JSON view landed. Nothing pending.",
    preview: "GET /status 200 · 12ms\nGET /status 200 · 11ms" },
];
window.STATUS_TONE = { ok: "ok", running: "accent", failed: "err", idle: "dim", "needs-you": "attention" };
