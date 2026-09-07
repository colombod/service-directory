Settings is the home for everything about *this node* and its fleet — identity, peers, pairing, lifecycle. New management surfaces become a `SettingsSection` here, not a new top-level page.

```jsx
<SettingsPanel onClose={close}>
  <SettingsSection title="Write Token">{tokenField}</SettingsSection>
  <SettingsSection title="Node Identity">
    <KeyValueList items={[{ label: "Name", value: "node-a" }]} />
  </SettingsSection>
</SettingsPanel>
```

Every mutation inside Settings requires the write token, and the panel stays read-only until one is supplied (localhost is the server-side exception).
