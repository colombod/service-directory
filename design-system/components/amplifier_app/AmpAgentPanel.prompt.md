The Amplifier Agent panel — use it whenever an app exposes the agent; it is the same surface in every Amplifier app.

```jsx
{agent ? (
  <AmpAgentPanel log={log} draft={draft} onDraft={setDraft}
                 onSend={send} onClose={() => setAgent(false)} />
) : null}
```

Notes
- It is a **panel, not a modal**: `--z-panel` (200), no backdrop, the page keeps running behind it. The violet left edge is the only chrome that marks it as the agent.
- Messages are labelled text on the page (`AGENT` / `YOU` in caps as a *style*), never chat bubbles and never a product header inside your app.
- Its parent must be `position: relative` — the panel pins to that box, not the viewport.
- The one shadow (`--shadow-edge-left`) is legitimate here: the panel overlaps live content.
