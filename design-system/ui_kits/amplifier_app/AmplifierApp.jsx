const SORTS = ["Recent", "Attention first", "Name", "Owner"];
const THEMES = ["Dark", "Light", "Auto"];

function AmplifierApp() {
  const [items, setItems] = React.useState(window.ITEMS);
  const [filter, setFilter] = React.useState("");
  const [sortIdx, setSortIdx] = React.useState(0);
  const [openId, setOpenId] = React.useState(null);
  const [agent, setAgent] = React.useState(false);
  const [toast, setToast] = React.useState(null);
  const [theme, setTheme] = React.useState(() => localStorage.getItem("amp-kit-theme") || "Dark");
  React.useEffect(() => {
    document.documentElement.dataset.theme = theme.toLowerCase();
    localStorage.setItem("amp-kit-theme", theme);
  }, [theme]);

  React.useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const sort = SORTS[sortIdx];
  const q = filter.trim().toLowerCase();
  let visible = items.filter((it) =>
    !q || (it.name + " " + it.owner + " " + it.status).toLowerCase().includes(q));
  if (sort === "Attention first") visible = visible.slice().sort((a, b) => b.attention - a.attention);
  if (sort === "Name") visible = visible.slice().sort((a, b) => a.name.localeCompare(b.name));
  if (sort === "Owner") visible = visible.slice().sort((a, b) => a.owner.localeCompare(b.owner));

  const open = items.find((it) => it.id === openId) || null;
  const attention = items.reduce((n, it) => n + (it.attention > 0 ? 1 : 0), 0);
  const resolve = (item) =>
    setItems((list) => list.map((it) => it.id === item.id ? { ...it, attention: 0, status: "ok" } : it));

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", position: "relative", overflow: "hidden" }}>
      <Header filter={filter} setFilter={setFilter} sort={sort}
        cycleSort={() => setSortIdx((i) => (i + 1) % SORTS.length)} focused={!!open}
        onBack={() => setOpenId(null)} onAgent={() => setAgent((a) => !a)} agentOpen={agent}
        attention={attention} theme={theme}
        cycleTheme={() => setTheme((t) => THEMES[(THEMES.indexOf(t) + 1) % THEMES.length])} />
      <div style={{ display: "flex", flex: 1, minHeight: 0, overflow: "hidden" }}>
        {open ? (
          <React.Fragment>
            <Rail items={visible} selectedId={openId} onOpen={(it) => setOpenId(it.id)}
              filter={filter} setFilter={setFilter} />
            <Detail item={open} onResolve={resolve} onToast={setToast} />
          </React.Fragment>
        ) : (
          <Overview items={visible} onOpen={(it) => setOpenId(it.id)} />
        )}
      </div>
      {agent ? <AgentPanel onClose={() => setAgent(false)} onToast={setToast} /> : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<AmplifierApp />);
