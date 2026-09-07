Use `ServiceDetail` as the viewer pane's content after a row click, before anything is embedded.

```jsx
<ServiceDetail service={svc} status="up" onOpenHere={openServiceInViewer} />
```

"Open here" is the one primary button on the surface. When a service has neither a `view_url` nor a primary link, show the literal line "No in-app view configured for this service" instead of a disabled button.
