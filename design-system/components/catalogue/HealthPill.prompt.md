Use `HealthPill` anywhere a service or peer's liveness is shown.

```jsx
<HealthPill status="up" />
<HealthPill status="unknown" />
```

Render `unknown` first and update after the health fetch resolves. A peer that can't be reached is `unknown`, never `down` — the product refuses to state a status it hasn't observed.
