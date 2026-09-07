Use `ServiceRow` inside `ServiceTable` — never on its own.

```jsx
<ServiceRow service={svc} status="up" compact onOpen={openInViewer} onRemove={remove} />
```

- The name is a `<button>`; clicking the row or the name opens the detail view in the viewer pane.
- `compact` is what the 340px sidebar uses: name + category + status only.
- A static (YAML-declared) row must never render a remove `×`.
