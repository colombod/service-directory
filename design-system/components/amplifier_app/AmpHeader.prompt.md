The shared Amplifier app header — mark, app name, word chrome, attention summary, agent button — plus `AgentButton` and `AttentionBadge` on their own.

```jsx
<AmpHeader appName="Resolve" attention={2} attentionNoun="run"
           onAgent={() => setAgent(!agent)} agentOpen={agent}>
  {focused ? <AmpTextControl onClick={back}>← All runs</AmpTextControl> : null}
  <AmpTextControl onClick={cycleSort}>{sort} ▾</AmpTextControl>
  <AmpFilter value={filter} onChange={setFilter} />
</AmpHeader>
```

Notes
- Height is `--header-height` (44px) and fixed; the header never grows.
- `markSrc` must resolve from the *page*, not the component: pass the correct relative path to `assets/amplifier/amplifier-icon-32.png`.
- `AttentionBadge` needs the `amp-pulse` keyframes in the page (1.4s ease-in-out infinite) — it is the only looping motion an Amplifier app ships.
- Violet is the agent and "this needs you"; it is never used for errors (`--amp-err`) or warnings (`--amp-warn`).
