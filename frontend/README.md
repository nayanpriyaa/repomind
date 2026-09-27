# RepoMind frontend

React 18 + TypeScript (strict) + Vite. Zero runtime deps beyond React. No Tailwind, no icon/syntax libraries (custom SVG set, custom lexical highlighter).

## Run
    npm install
    npm run dev        # http://localhost:5173, /api/* proxied to http://127.0.0.1:8000
    npm run typecheck
    npm run build

Bypass proxy: `VITE_API_BASE_URL=http://localhost:8000 npm run dev` (backend needs CORS then).

## Structure
    src/types/api.ts              backend contracts
    src/services/                 api.ts (transport + ApiError), health, repositories, query (query+search), source
    src/lib/                      guards (normalizers), citations (answer ref parser), highlight, format
    src/hooks/                    useHealth, useRepositories(+Status), useIndexing, useInvestigations, useRetrieval, useEvidence, ...
    src/components/               layout, repository, query, answer, citations, source-viewer, retrieval, indexing, health, ui

## API assumptions (verify against backend)
- Only `/repositories/query` shape was specified. `/health`, `/ready`, `/repositories`, `/repositories/status`, `/repositories/index`, `/repositories/search` go through tolerant normalizers in `services/` accepting common field names. Adjust key lists there if yours differ.
- `GET /repositories/status?repository_path=...`; `POST /repositories/index {repository_path}`.
- `POST /repositories/search` sends `query`; retries once with `question` on a 422 that mentions it.
- No source-file endpoint exists. Evidence code is shown only when `/search` results include chunk text (`content|text|code|snippet`). Otherwise the panel shows location metadata and a "source text unavailable" state. Plug a future endpoint into `services/source.ts`.
- Indexing progress bar is indeterminate unless status returns processed/total file counts.
- Missing `grounded` flag is treated as ungrounded.
