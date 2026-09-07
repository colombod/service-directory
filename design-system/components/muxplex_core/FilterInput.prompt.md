`FilterInput` for filtering a list; `Field` for a labelled control in a settings panel.

```jsx
<FilterInput value={q} onValueChange={setQ} onClear={() => setQ("")} placeholder="Filter" />
<FilterInput caption="Filter" value={q} onValueChange={setQ} />
<Field label="Preview zoom" helper="Scales tile height and column width together">{slider}</Field>
```

The clear `×` appears only when the field has a value. Label `--text-sm`, control `--text-md`, `--space-sm` between them, `--space-lg` between fields.
