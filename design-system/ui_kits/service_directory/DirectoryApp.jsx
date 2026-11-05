function DirectoryApp() {
  const [filter, setFilter] = React.useState("");
  const [collapsed, setCollapsed] = React.useState(false);
  const [selected, setSelected] = React.useState(null);
  const [mode, setMode] = React.useState("welcome");
  const [settings, setSettings] = React.useState(false);
  const [services, setServices] = React.useState(window.CATALOGUE);

  const q = filter.trim().toLowerCase();
  const visible = services.filter((s) =>
    !q || (s.name + " " + (s.description || "") + " " + s.origin + " " + (s.tags || []).join(" ")).toLowerCase().includes(q)
  );
  const svc = services.find((s) => s.name === selected) || null;

  const openHere = (s) => {
    if (s.view_kind === "json") setMode("json");
    else if (s.name === "grafana") setMode("fallback");
    else setMode("iframe");
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden" }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 16, padding: "22px 28px 16px",
        borderBottom: "1px solid var(--sd-border)", flexShrink: 0 }}>
        <h1 style={{ margin: 0, fontSize: 17, fontWeight: 650, letterSpacing: "-.01em" }}>Service Directory</h1>
        <div style={{ fontSize: "12.5px", color: "var(--sd-text-muted)" }}>
          <span style={{ fontWeight: 600, color: "var(--sd-text)" }}>node-a</span>
          {" · "}
          <span style={{ color: "var(--sd-accent)", fontWeight: 600 }}>primary</span>
        </div>
        <button onClick={() => setSettings(true)} title="Settings" aria-label="Settings"
          style={{ marginLeft: "auto", border: "1px solid var(--sd-border-strong)", background: "var(--sd-alt)",
            color: "var(--sd-text-muted)", borderRadius: 6, padding: "6px 12px", fontSize: 13,
            cursor: "pointer", flexShrink: 0, whiteSpace: "nowrap" }}>⚙ Settings</button>
      </header>
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        <Sidebar collapsed={collapsed} filter={filter} setFilter={setFilter} services={visible}
          health={window.HEALTH} selected={selected} onCollapse={() => setCollapsed(true)}
          onOpen={(s) => { setSelected(s.name); setMode("detail"); }}
          onRemove={(s) => setServices((list) => list.filter((x) => x.name !== s.name))} />
        {collapsed ? (
          <button onClick={() => setCollapsed(false)} title="Expand sidebar"
            style={{ alignSelf: "flex-start", margin: "14px 0 0 10px", border: "1px solid var(--sd-border-strong)",
              background: "var(--sd-alt)", color: "var(--sd-text-muted)", borderRadius: 6, padding: "5px 9px",
              fontSize: 13, cursor: "pointer", lineHeight: 1 }}>»</button>
        ) : null}
        <Viewer svc={mode === "welcome" ? null : svc} status={svc ? (window.HEALTH[svc.name] || "unknown") : "unknown"}
          mode={mode} onOpenHere={openHere}
          onClose={() => { setMode("welcome"); setSelected(null); }} />
      </div>
      {settings ? <SettingsOverlay onClose={() => setSettings(false)} /> : null}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<DirectoryApp />);
