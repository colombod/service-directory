The four overlay components, and the only four things in the system with shadows.

```jsx
<Toast>Session created</Toast>
<Menu items={[{ label: "Rename" }, { label: "Kill session", tone: "err" }]} onSelect={run} />
<Modal title="Settings" onClose={close}>{fields}</Modal>
<BottomSheet items={sessions} onSelect={open} onClose={close} />
```

Layering comes from the measured ladder: toast/menu `--z-popover`, sheet `--z-panel`, modal `--z-modal-backdrop`/`--z-modal`. Never invent a fresh integer. Menu *content* is per-instance; the open/close mechanism is shared — a new dropdown adds a render function, never a second controller.
