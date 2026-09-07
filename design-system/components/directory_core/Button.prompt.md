Use `Button` for every clickable control in a Service Directory surface — there is no other button in the product.

```jsx
<Button variant="primary" size="xl">Open here</Button>
<Button variant="secondary">&#9881; Settings</Button>
<Button variant="ghost" size="sm" title="Remove">&times;</Button>
```

- **primary** is reserved for the one committing action on a surface ("Open here", "Pair with peer", "Add service"). Its hover is `opacity: .9` — never a darker fill.
- **secondary** is the workhorse: Settings, sidebar collapse, viewer Reload/Refresh/Close. Hover only changes ink from `--text-muted` to `--text`.
- **ghost** is only ever an `×`. Hover turns it `--down`.
- Sizes map to real call sites: `sm` viewer toolbar, `md` header, `lg` settings, `xl` the detail-pane "Open here".
