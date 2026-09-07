Metadata decorations for a catalogue row or node header.

```jsx
<CategoryChip>pipelines</CategoryChip>
<TagList tags={["video", "editor"]} />
<ReachableBadge />
```

Categories are lowercase single words from config. Tags render `#tag` with the hash at 60% opacity. `ReachableBadge` only ever appears on a node group that is currently reachable — an unreachable node contributes no section at all.
