Use `TextInput` for any typed value: the catalogue filter, the write token, add-service fields, pairing URL/code.

```jsx
<TextInput size="filter" search placeholder="Filter&hellip;" aria-label="Filter services" />
<TextInput size="md" type="password" placeholder="Bearer write token (optional on localhost)" />
```

Focus is always `border-color: var(--accent)` plus the 3px `--accent-weak` ring — the only ring in the system. Placeholders render at `--text-faint`, full opacity.
