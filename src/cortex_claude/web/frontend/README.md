# Cortex dashboard

Vue 3 + TypeScript + Mavis Web/core/Jolt 0.1.0-rc.12.1, built with Vite. Node 22.12 or newer is required.

```sh
npm ci
npm run dev
npm run lint
npm run typecheck
npm run build
npm run test:browser
```

Development proxies /api to the Cortex server on 127.0.0.1:37800. Production assets go to ../static and ship in the Python wheel. Views use Mavis controls, services and theme tokens; local SVG icons avoid the full icon font. The connections view loads Cytoscape on demand.

Browser tests launch the production bundle with the real Python HTTP API and temporary databases via scripts/dashboard_fixture.py. Install the Python environment from the repository root with uv sync --all-extras first. Locally Playwright uses installed Google Chrome; CI installs Chromium. Screenshots and failure traces stay in ignored test-results.

The API client checks both HTTP errors and application errors. Mutable actions refresh their source data; task writes send expected_revision. Destructive actions use Mavis confirmation dialogs. The backend only accepts localhost Host/Origin values.
