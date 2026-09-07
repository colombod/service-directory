# UI kit — Service Directory (web app)

A recreation of the single server-rendered dashboard page in
`colombod/service-directory` (`_render_html()` in `src/service_directory/app.py`).

Two-pane workspace: the catalogue rail on the left grouped by origin node, the
viewer pane on the right. Opening a service **in-app** is the default action;
external links are always an explicit `target="_blank"` option.

## Screens / states

| State | What it shows |
|---|---|
| Catalogue (default) | node groups, health pills, filter, viewer welcome, register-a-service panel |
| Service detail | metadata, docs link, external addresses, "Open here" |
| Embedded (iframe) | viewer toolbar + framed service |
| JSON view | collapsible JSON tree, Refresh + Auto-refresh, "updated Ns ago" |
| Fallback | can't-embed reason + "Open in a new tab ↗" |
| Settings | right-anchored overlay: write token, node identity, peers, pairing |

## Fidelity notes

- Values are verbatim from the app's inline `<style>` block; the palette is
  scoped through `products/service-directory.css`, never mixed with muxplex names.
- The service name is a real `<button>`: in-app opening must be in the a11y tree.
- Static (YAML) rows never get a remove `×`; only dynamically registered ones do.
- A peer that was not observed is `unknown`, never `down`.
