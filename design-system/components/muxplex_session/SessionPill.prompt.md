`SessionPill` floats bottom-right when a session is open behind the grid; `FilterPill` builds the filter bar.

```jsx
<SessionPill label="build" bell onClick={reopen} />
<FilterPill active>bell</FilterPill>
```

The pill is one of the few shadowed things in the app, and it earns it: it floats over live content.
