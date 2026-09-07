Group the catalogue by origin node, one `NodeGroup` per node, each wrapping one `ServiceTable`.

```jsx
<NodeGroup origin="node-a" description="Home lab tailnet node">
  <ServiceTable services={local} health={health} compact onOpen={open} />
</NodeGroup>
```

There are no per-item tiles and no motion — the catalogue is a precise table. A node section is rendered only when that node is reachable; hide the whole section when a filter matches none of its rows.
