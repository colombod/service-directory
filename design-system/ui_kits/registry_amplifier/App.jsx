function App() {
  const [services, setServices] = React.useState(window.SERVICES);
  const [filter, setFilter] = React.useState("");
  const [openName, setOpenName] = React.useState(null);
  const [mode, setMode] = React.useState("detail");
  const [settings, setSettings] = React.useState(false);
  const [agent, setAgent] = React.useState(false);
  const [toast, setToast] = React.useState(null);

  React.useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2400);
    return () => clearTimeout(t);
  }, [toast]);

  const q = filter.trim().toLowerCase();
  const visible = services.filter((s) =>
    !q || (s.name + " " + s.description + " " + s.origin + " " + (s.tags || []).join(" ")).toLowerCase().includes(q));
  const open = services.find((s) => s.name === openName) || null;
  const attention = services.reduce((n, s) => n + (s.attention > 0 ? 1 : 0), 0);
  const remove = (svc) => {
    setServices((list) => list.filter((s) => s.name !== svc.name));
    if (openName === svc.name) { setOpenName(null); setMode("detail"); }
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden" }}>
      <Header filter={filter} setFilter={setFilter} focused={!!open}
        onBack={() => { setOpenName(null); setMode("detail"); }}
        onSettings={() => setSettings(true)} onAgent={() => setAgent((a) => !a)}
        agentOpen={agent} attention={attention} />
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {open ? (
          <React.Fragment>
            <Rail services={visible} selectedName={openName}
              onOpen={(s) => { setOpenName(s.name); setMode("detail"); }}
              filter={filter} setFilter={setFilter} />
            <Pane svc={open} mode={mode} setMode={setMode} onRemove={remove} onToast={setToast} />
          </React.Fragment>
        ) : (
          <Overview services={visible} onRemove={remove}
            onOpen={(s) => { setOpenName(s.name); setMode("detail"); }} />
        )}
      </div>
      {settings ? <Settings onClose={() => setSettings(false)} onToast={setToast} /> : null}
      {agent ? <AgentPanel onClose={() => setAgent(false)} onToast={setToast} /> : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
