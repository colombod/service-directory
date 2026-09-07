Use `AddressLink` for every URL that leaves the dashboard.

```jsx
<AddressLink label="Tailnet" href="http://100.111.191.22:8080/" variant="primary" />
<AddressLink label="LAN" href="http://192.168.1.86:8080/" />
```

Order addresses tailnet-first. If the dashboard is served over HTTPS, every href must be HTTPS too — an `http://` link inside an HTTPS page is blocked mixed content and reads as a layout bug.
