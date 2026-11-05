const SORTS = ["Recent activity", "Name", "Device"];

function MuxplexApp() {
  const [rail, setRail] = React.useState(true);
  const [view, setView] = React.useState("Grid");
  const [sortIdx, setSortIdx] = React.useState(0);
  const [filter, setFilter] = React.useState("");
  const [tier, setTier] = React.useState("all");
  const [openId, setOpenId] = React.useState(null);
  const [settings, setSettings] = React.useState(false);
  const [agent, setAgent] = React.useState(false);
  const [toast, setToast] = React.useState(null);
  const [zoom, setZoom] = React.useState(100);
  const [bellMode, setBellMode] = React.useState("glow");

  React.useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const sort = SORTS[sortIdx];
  const q = filter.trim().toLowerCase();
  let sessions = window.SESSIONS.filter((s) =>
    (!q || (s.name + " " + s.device).toLowerCase().includes(q)) &&
    (tier === "all" || (tier === "bell" ? s.bell > 0 : tier === "active" ? s.bell === 0 : s.bell === 0))
  );
  if (sort === "Name") sessions = sessions.slice().sort((a, b) => a.name.localeCompare(b.name));
  if (sort === "Device") sessions = sessions.slice().sort((a, b) => a.device.localeCompare(b.device));

  const open = window.SESSIONS.find((s) => s.id === openId);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column",
      "--preview-zoom": zoom / 100, position: "relative", overflow: "hidden" }}>
      <Header view={view} setView={setView} sort={sort} cycleSort={() => setSortIdx((i) => (i + 1) % SORTS.length)}
        filter={filter} setFilter={setFilter} onToggleRail={() => setRail((r) => !r)}
        onSettings={() => setSettings(true)} onAgent={() => setAgent((a) => !a)} />
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        <Rail collapsed={!rail} sessions={sessions} activeId={openId} onOpen={(s) => setOpenId(s.id)}
          sort={sort} cycleSort={() => setSortIdx((i) => (i + 1) % SORTS.length)}
          filter={filter} setFilter={setFilter} />
        {open
          ? <SessionView s={open} onBack={() => setOpenId(null)} />
          : <SessionGrid sessions={sessions} tier={tier} setTier={setTier}
              onOpen={(s) => { setOpenId(s.id); setToast("Attached to " + s.name); }} />}
      </div>
      {!open && window.SESSIONS.some((s) => s.bell > 0)
        ? <SessionPillFloating label="deploy" bell onClick={() => setOpenId("deploy")} /> : null}
      {settings ? <SettingsDialog onClose={() => setSettings(false)} zoom={zoom} setZoom={setZoom}
        bell={bellMode} setBell={setBellMode} /> : null}
      {agent ? <AgentPanel onClose={() => setAgent(false)} onSend={() => setToast("Sent to Amplifier Agent")} /> : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<MuxplexApp />);
