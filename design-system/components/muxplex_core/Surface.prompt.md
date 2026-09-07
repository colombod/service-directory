`Surface` is the answer to "what do I put content in?" — flat, 1px border, 4px radius, never a shadow. A shadow is earned only by overlapping live content (see Panel / Modal / Menu).

```jsx
<Surface padded>{settingsRows}</Surface>
<Badge tone="accent">macbook</Badge>
<Badge tone="bell" pill={false}>3</Badge>
```

If you cannot say in one clause what a fill *means*, remove it.
