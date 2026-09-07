The 200px rail lists every session as a `SidebarItem`, grouped by device with `DeviceHeader`.

```jsx
<DeviceHeader version="v0.47.9">macbook</DeviceHeader>
<SidebarItem name="build" active preview={tail} badge={<Badge tone="accent">mb</Badge>} />
```

Vertical rhythm comes only from the list's `gap` (`--sidebar-gap`), never from padding inside an item.
