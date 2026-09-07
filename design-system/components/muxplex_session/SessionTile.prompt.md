`SessionTile` is the product. Lay tiles out in a grid of `repeat(auto-fill, minmax(var(--tile-min-width), 1fr))` with `--grid-gap`.

```jsx
<SessionTile name="build" meta="3w · 2m" preview={tail} bellCount={2} deviceTag="macbook" />
```

- The 3px left edge bar is always present; the bell state recolours it, never adds it.
- Attention is colour **and** border **and** glow — never colour alone.
- The device tag is fully opaque by construction: it overlays arbitrary terminal pixels, so its contrast must not depend on what is underneath.
