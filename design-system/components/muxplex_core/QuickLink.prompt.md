Use `QuickLink` for chrome that changes what you are looking at — view switchers, sort controls, New, Export. Idempotent chrome is a link; a commit action is a real button.

```jsx
<QuickLink expanded={open} onClick={toggle}>Grid &#9662;</QuickLink>
<QuickLink caption="Sort" onClick={cycle}>Recent activity</QuickLink>
```

Hover, focus-visible, active and `aria-expanded="true"` are all the SAME colour change (`--accent` → `--accent-hover`), plus a `2px solid --accent` ring at 2px offset on focus-visible only. Never give it a background or border in any state.
