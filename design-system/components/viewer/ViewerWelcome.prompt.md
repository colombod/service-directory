The three states of the right-hand viewer pane.

```jsx
<ViewerWelcome />
<ViewerHeader name="Resolve" url={url} actions={<Button size="sm">Reload</Button>} onClose={close} />
<ViewerFallback name="Grafana" url={url} reason="This service cannot be embedded (X-Frame-Options or CSP frame-ancestors)." />
```

The fallback always offers "Open <name> in a new tab ↗" — the user is never left with a dead end. Reasons are quoted verbatim from the probe, not softened.
