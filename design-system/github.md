repo: colombod/service-directory
branch: main
path: design-system

## Last sync

date: 2026-09-07T12:51:25Z

### Updated in this project

- Imported the whole `design-system/` tree verbatim (tokens, 22 guideline cards, components, 4 UI kits, brand assets).
- Added `components/amplifier_app/` — the Amplifier app primitives extracted from the app-shell UI kit.
- Added `templates/amplifier-app/` (app shell template) and `thumbnail.html`.
- Renamed each UI kit's root component off `App` so all four kits bundle together.

## Screen map

| In this project | Built from (repo paths) |
|---|---|
| `styles.css`, `tokens/*`, `products/service-directory.css` | `design-system/styles.css`, `design-system/tokens/*`, `design-system/products/service-directory.css` |
| `guidelines/*.card.html` | `design-system/guidelines/*` |
| `components/{muxplex_core,muxplex_session,muxplex_overlay,directory_core,catalogue,viewer,settings}/` | same paths under `design-system/components/` |
| `components/amplifier_app/` | `design-system/ui_kits/amplifier_app/Shell.jsx`, `Agent.jsx`, `design-system/tokens/amplifier-app.css` |
| `ui_kits/amplifier_app/index.html` | `design-system/ui_kits/amplifier_app/*` |
| `ui_kits/muxplex/index.html` | `design-system/ui_kits/muxplex/*` |
| `ui_kits/registry_amplifier/index.html` | `design-system/ui_kits/registry_amplifier/*` |
| `ui_kits/service_directory/index.html` | `design-system/ui_kits/service_directory/*` |
| `templates/amplifier-app/AmplifierApp.dc.html` | `design-system/ui_kits/amplifier_app/*` (composed from `components/amplifier_app/`) |
| `example/*.html` | `design-system/example/*` |
| `assets/` | `design-system/assets/` |
