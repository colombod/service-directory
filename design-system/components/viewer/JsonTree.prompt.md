Use `JsonTree` for a service whose `view_kind` is `json` (or an `auto` service whose probe reports a JSON content type).

```jsx
<JsonTree data={payload} />
```

Keys are accent + semibold, strings green, numbers amber, booleans violet, `null` faint italic. Pair it with a Refresh / Auto-refresh pair and an "updated Ns ago" indicator in the `ViewerHeader` actions slot when `view_refresh_seconds` is set.
