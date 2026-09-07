Federation UI: list trusted peers, and issue or redeem a pairing code.

```jsx
<ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
  <PeerItem name="node-b" baseUrl="http://100.111.191.8:80" reachable="up" onRemove={remove} />
</ul>
<PairingCode code="4KQ2-9XPD" ttlSeconds={600} />
```

Show the Pairing section only when `federation_enabled` is true. The code is monospace, accent, letter-spaced, with its TTL stated plainly beneath.
