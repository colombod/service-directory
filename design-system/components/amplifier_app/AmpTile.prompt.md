The overview→focus pair: `AmpTile` in an `AmpTileGrid` for the overview, `AmpRailRow` for the same items once one is focused.

```jsx
<AmpTileGrid>
  {items.map((it) => (
    <AmpTile key={it.id} name={it.name} status={it.status} statusTone="ok"
             summary={it.summary} preview={it.preview} tag={it.owner}
             attention={it.attention} onOpen={() => open(it)} />
  ))}
</AmpTileGrid>

<AmpRailRow name={it.name} status={it.status} meta={it.meta}
            selected={it.id === openId} onOpen={() => open(it)} />
```

Notes
- Every tile and row carries a 3px left border **at all times** — `--amp-line` at rest, `--amp-azure` on hover/selection, `--amp-violet` + glow + count when it needs a human. Selection changes colour, never geometry.
- Tiles are fixed `--tile-height` (300px) and flat: no shadow unless the violet attention glow applies.
- The rail is the overview condensed — same items, same order, same edge colours. Don't give it its own sort or grouping.
- `statusTone` maps to the signal tokens; green/amber/red mean status only and never decorate a surface.
