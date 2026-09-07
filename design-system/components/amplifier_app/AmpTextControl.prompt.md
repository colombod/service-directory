Word chrome for an Amplifier app header: `AmpTextControl` for view/sort/back controls, `AmpFilter` for the one filter field.

```jsx
<AmpTextControl onClick={back}>← All runs</AmpTextControl>
<AmpTextControl expanded={open} onClick={cycleSort}>{sort} ▾</AmpTextControl>
<AmpFilter value={filter} onChange={setFilter} />
```

Notes
- View, sort and filter controls are azure **text**, never glyph buttons — the only bordered controls on a surface are the agent button and the single primary action.
- `expanded` both colours the control as hovered and sets `aria-expanded`; use it for a control whose menu is open.
- `wide` on `AmpFilter` is the focused-rail variant (fills width); the default 150px is the header variant.
