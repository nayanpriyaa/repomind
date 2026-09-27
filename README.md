# RepoMind

**RepoMind is a codebase Q&A and semantic-search system that lets you upload a repository, index its source structurally, and ask grounded questions with file-and-line evidence.**

Instead of treating a repository as a bag of arbitrary text windows, RepoMind parses source into meaningful units such as classes, functions, and methods, combines semantic and exact-match retrieval, and gives the LLM only retrieved evidence to reason over.

> **Current local LLM:** Ollama + `qwen2.5-coder:7b`
>
> **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional, CPU)
>
> **Vector store:** Qdrant
>
> **Keyword search:** SQLite FTS5 / BM25

---

## Why RepoMind?

General-purpose chat models do not automatically know the contents of a private codebase. Naive RAG also has a structural problem: fixed-size text windows frequently split functions, classes, and declarations across unrelated chunks.

RepoMind is designed around three principles:

1. **Structure-aware indexing** — source is chunked around language constructs where possible.
2. **Hybrid retrieval** — semantic similarity finds concepts while BM25 finds exact identifiers and symbols.
3. **Grounded answers** — the generation prompt is built from retrieved repository evidence, and answers expose the files and line ranges used as evidence.

The result is a workflow closer to **"ask the codebase"** than a generic chatbot.

---

## What it can do

- Upload arbitrary `.zip` repositories through the web UI.
- Safely extract archives into managed repository storage.
- Assign repositories safe IDs instead of exposing filesystem paths through the API.
- Parse supported source languages into structural chunks.
- Incrementally index repositories using SHA-256 file hashes.
- Store exact-search data in SQLite FTS5.
- Store semantic vectors and citation metadata in Qdrant.
- Fuse semantic and keyword results with Reciprocal Rank Fusion (RRF).
- Ask natural-language questions about an indexed repository.
- Return grounded answers with source files, symbols, and line ranges.
- Inspect retrieved evidence directly in the UI.
- Re-index changed repositories without rebuilding everything unnecessarily.
- Delete a repository and its associated index state through the API/UI.
- Run retrieval without invoking the LLM.
- Run an offline test suite with LLM/vector-store stubs.

---

## Architecture

```text
                           Browser
                              │
                    React + TypeScript + Vite
                              │
                           HTTP / API
                              │
                              ▼
                     ┌──────────────────┐
                     │     FastAPI      │
                     │  repository API  │
                     └────────┬─────────┘
                              │
                       ServiceContainer
                              │
             ┌────────────────┼─────────────────┐
             │                │                 │
             ▼                ▼                 ▼
        RepositoryStore   IngestionSvc       RagService
             │                │                 │
             │          scan → parse → embed    │
             │                │                 │
             │        ┌───────┴───────┐         │
             │        ▼               ▼         │
             │     SQLite           Qdrant      │
             │     state + FTS5     vectors     │
             │        │               │         │
             │        └───────┬───────┘         │
             │                │                 │
             │                └── hybrid ───────┘
             │                    retrieval
             │                        │
             │                        ▼
             │                 Context + Prompt
             │                        │
             │                        ▼
             │                Ollama / Qwen 2.5
             │                        │
             └────────────────────────┴─────────┐
                                                ▼
                                     Grounded answer + evidence
```

### Storage responsibilities

| Component | Stores | Purpose |
|---|---|---|
| **RepositoryStore** | Uploaded/extracted repositories | Persistent source-code storage |
| **SQLite** | File hashes, chunk metadata, index state | Incremental indexing and state tracking |
| **SQLite FTS5** | Chunk text, paths, symbols | Exact identifier / keyword retrieval with BM25 |
| **Qdrant** | Embeddings + citation payloads | Semantic retrieval |
| **Ollama** | Local LLM | Answer generation |

Uploaded repositories are stored in the Docker named volume mounted at `/repositories`. The uploaded ZIP is processed and extracted; the application does not execute repository code.

---

## Retrieval pipeline

A question follows this path:

```text
Question
   │
   ▼
Query embedding + keyword query
   │
   ├──────────────► Qdrant semantic search
   │
   └──────────────► SQLite FTS5 / BM25
                          │
                          ▼
                 Reciprocal Rank Fusion
                          │
                          ▼
                    Top-k chunks
                          │
                          ▼
                 Context construction
                          │
                          ▼
                     LLM prompt
                          │
                          ▼
                 Qwen 2.5 Coder 7B
                          │
                          ▼
              Grounded answer + sources
```

### Why hybrid retrieval?

Semantic search is useful for questions such as:

> "How does the application prevent two users from booking the same seat?"

BM25 is useful for exact identifiers such as:

```text
ERR_TOKEN_EXPIRED
BookingService
createBooking
```

RepoMind combines both retrieval modes with **Reciprocal Rank Fusion** rather than directly adding cosine-similarity and BM25 scores, since those scores are not naturally comparable.

The UI exposes **Hybrid**, **Semantic**, and **Keyword** retrieval modes so retrieval behaviour can be inspected directly.

---

## Structural indexing

RepoMind does not rely exclusively on arbitrary fixed-size windows.

Current parsing support includes:

- **Python** — standard-library `ast`
- **C / C++** — tree-sitter based parsing
- **Java** — tree-sitter based parsing
- **JavaScript** — tree-sitter based parsing
- **TypeScript / TSX** — tree-sitter based parsing
- **Markdown** — heading-based chunking
- Other supported/text-like files can fall back to line-based chunking when structural parsing is unavailable.

A class and its methods can be represented separately so that retrieval can surface the method implementation without repeatedly embedding the entire class body.

Chunk IDs are deterministic, allowing incremental re-indexing and safe upserts rather than accumulating duplicate vectors.

---

## Incremental indexing

Index state is based on **SHA-256 content hashes**, rather than timestamps alone.

| Repository change | Behaviour |
|---|---|
| New file | Parse → chunk → embed → store |
| Unchanged file | Skip |
| Modified file | Remove old chunks → reparse → re-embed → store |
| Deleted file | Remove chunks and index state |

The indexing pipeline is designed to be idempotent: repeating an indexing operation converges on the same state.

There is currently no distributed transaction spanning SQLite and Qdrant, so a process failure during indexing can temporarily leave stale vector state. A subsequent index run can reconcile it.

---

## LLM: Ollama + Qwen 2.5 Coder

RepoMind currently uses a local Ollama server rather than a hosted Gemini API.

Default configuration:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5-coder:7b
LLM_TIMEOUT_SECONDS=120
LLM_MAX_OUTPUT_TOKENS=1024
```

On Windows, Ollama runs on the host while the RepoMind API runs in Docker. `host.docker.internal` allows the container to reach the host's Ollama server.

Verify Ollama before starting RepoMind:

```powershell
ollama list
```

You should have:

```text
qwen2.5-coder:7b
```

You can also test the host API directly:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:11434/api/generate" `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"model":"qwen2.5-coder:7b","prompt":"Reply with exactly: Ollama works","stream":false}'
```

The model is not installed in the RepoMind Docker image. It remains managed by Ollama on the host or inference machine.

---

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite |
| API | FastAPI, Pydantic v2, Uvicorn |
| Parsing | Python `ast`, tree-sitter |
| State / keyword retrieval | SQLite + FTS5 / BM25 |
| Vector search | Qdrant |
| Embeddings | Sentence Transformers — `all-MiniLM-L6-v2` |
| LLM runtime | Ollama |
| LLM | Qwen 2.5 Coder 7B |
| Testing | pytest |
| Packaging | setuptools / `pyproject.toml` |
| Infrastructure | Docker Compose |

---

## Project structure

```text
RepoMind/
├── src/repomind/
│   ├── api/
│   │   ├── main.py              # FastAPI application and repository API
│   │   └── schemas.py           # Request/response models
│   ├── container.py              # Shared service container
│   ├── config.py                 # Environment-backed settings
│   ├── uploads.py                # ZIP validation, extraction, repository store
│   ├── ingestion.py              # Scan → parse → embed → persist
│   ├── parser.py                 # Structural parsing/chunking
│   ├── retrieval.py              # Semantic / keyword / hybrid retrieval
│   ├── qdrant_store.py            # Qdrant integration
│   ├── keyword_search.py          # SQLite FTS5 / BM25
│   ├── embeddings.py              # Embedding model integration
│   ├── rag.py                     # Retrieval → context → prompt → LLM
│   ├── llm.py                     # LLM client abstraction + Ollama client
│   ├── prompt.py                  # Grounding / prompt construction
│   ├── index_state.py             # Incremental indexing state
│   └── ...
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   └── ...
│   └── package.json
├── tests/
├── evaluation/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

---

## Running locally with Docker

### Prerequisites

- Docker Desktop
- Python 3.11+ for local development/testing
- Node.js + npm for frontend development
- Ollama installed on the host
- `qwen2.5-coder:7b` available in Ollama

### 1. Configure environment

Copy the example file:

```powershell
Copy-Item .env.example .env
```

For the current Docker + Ollama setup, use:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5-coder:7b
LLM_TIMEOUT_SECONDS=120
LLM_MAX_OUTPUT_TOKENS=1024

QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=repomind_chunks
VECTOR_BACKEND=qdrant

EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_BATCH_SIZE=32

REPOSITORIES_ROOT=/repositories
DATABASE_PATH=/data/repomind.db

MAX_UPLOAD_BYTES=209715200
MAX_EXTRACTED_BYTES=1073741824
MAX_ARCHIVE_ENTRIES=100000

CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
LOG_LEVEL=INFO
```

### 2. Start the backend and Qdrant

```powershell
docker compose up --build
```

The backend is available at:

```text
http://localhost:8000
```

FastAPI documentation:

```text
http://localhost:8000/docs
```

Qdrant is exposed locally at:

```text
http://localhost:6333
```

### 3. Start the frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

The frontend communicates with the API through the configured Vite proxy.

---

## Repository uploads

The web application accepts `.zip` repositories.

```text
ZIP upload
    ↓
archive validation
    ↓
safe staged extraction
    ↓
managed repository storage
    ↓
index
    ↓
Ask questions
```

The browser sends a repository file and optional display name. It does **not** send a filesystem path.

Repositories are assigned safe IDs and stored beneath:

```text
/repositories/<repository_id>/
```

Inside Docker, `/repositories` is backed by the named volume:

```text
repomind-repositories
```

### Upload protections

The upload path includes protections for:

- maximum archive size
- maximum extracted size
- maximum archive entry count
- compression-ratio limits
- absolute-path rejection
- `..` / traversal rejection
- Windows path-separator rejection
- symlink-member handling
- staged extraction before final placement
- duplicate repository detection

Repository source is treated as data. RepoMind does not execute uploaded code.

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Dependency readiness |
| `GET` | `/repositories` | List stored repositories and index status |
| `GET` | `/repositories/{id}` | Get one repository's status |
| `POST` | `/repositories/upload` | Upload a ZIP repository |
| `DELETE` | `/repositories/{id}` | Delete repository and index data |
| `POST` | `/repositories/index` | Index / re-index a repository |
| `POST` | `/repositories/query` | Ask a grounded question |
| `POST` | `/repositories/search` | Raw retrieval without generation |

Example upload:

```bash
curl -F 'file=@my-project.zip' http://localhost:8000/repositories/upload
```

Example indexing request:

```bash
curl -X POST http://localhost:8000/repositories/index \
  -H 'Content-Type: application/json' \
  -d '{"repository_id":"my-project","force":false}'
```

Example question:

```bash
curl -X POST http://localhost:8000/repositories/query \
  -H 'Content-Type: application/json' \
  -d '{
    "repository_id":"my-project",
    "question":"Where is authentication implemented?",
    "top_k":5,
    "mode":"hybrid"
  }'
```

A successful response contains the generated answer plus source metadata such as:

```json
{
  "question": "Where is authentication implemented?",
  "answer": "Authentication is handled by TokenService...",
  "mode": "hybrid",
  "grounded": true,
  "chunks_used": 4,
  "context_characters": 3182,
  "sources": [
    {
      "file_path": "app/auth.py",
      "start_line": 16,
      "end_line": 18,
      "symbol": "TokenService.issue",
      "language": "python",
      "chunk_type": "method",
      "score": 0.0328
    }
  ]
}
```

---

## Frontend workflow

The UI is organized around the codebase-analysis workflow:

1. **Upload** a repository ZIP.
2. **Index** the repository.
3. Select the repository from the left panel.
4. Ask a question in **Ask** mode.
5. Choose **Hybrid**, **Semantic**, or **Keyword** retrieval.
6. Inspect the generated answer.
7. Inspect the retrieved evidence and source file/line ranges.
8. Switch to **Retrieval** mode when you want to inspect search results without generation.

For example, after indexing a repository such as SeatFlow, RepoMind can answer questions about booking flow, concurrency, services, APIs, and implementation details while exposing the retrieved source evidence beside the answer.

---

## Security model

RepoMind is designed to treat uploaded repositories as untrusted input.

| Control | Behaviour |
|---|---|
| Repository IDs | API clients never provide arbitrary filesystem paths |
| Root containment | Resolved repository paths must remain inside `REPOSITORIES_ROOT` |
| ZIP traversal protection | Rejects unsafe archive member paths |
| Symlink handling | Symlink archive members are not used to escape storage |
| Archive limits | Size, entry count, expansion and compression-ratio limits |
| Atomic upload | Extraction occurs in staging before final placement |
| Secret exclusion | Sensitive repository files are excluded from scanning |
| No code execution | Repository files are parsed/read, never imported or executed |
| Prompt injection resistance | Repository content is framed as untrusted evidence |
| CORS | Explicit frontend origin allowlist |
| Container isolation | API and Qdrant run in separate containers |

### Important deployment note

The current upload/indexing architecture is suitable for a controlled deployment or portfolio/demo environment, but a public multi-user deployment should additionally add authentication, rate limiting, resource quotas, background indexing, and stronger tenant isolation.

---

## Configuration

Important environment variables:

| Variable | Current/default purpose |
|---|---|
| `LLM_PROVIDER` | `ollama` |
| `OLLAMA_BASE_URL` | Ollama endpoint, e.g. `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` |
| `LLM_TIMEOUT_SECONDS` | LLM request timeout |
| `LLM_MAX_OUTPUT_TOKENS` | Maximum generated output |
| `QDRANT_HOST` / `QDRANT_PORT` | Qdrant service location |
| `QDRANT_COLLECTION` | `repomind_chunks` |
| `VECTOR_BACKEND` | `qdrant` |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` |
| `EMBEDDING_BATCH_SIZE` | Embedding batch size |
| `REPOSITORIES_ROOT` | `/repositories` |
| `DATABASE_PATH` | `/data/repomind.db` |
| `MAX_UPLOAD_BYTES` | 200 MiB archive limit |
| `MAX_EXTRACTED_BYTES` | 1 GiB extraction limit |
| `MAX_ARCHIVE_ENTRIES` | 100,000 archive members |
| `MAX_CONTEXT_CHARACTERS` | Evidence/context budget |
| `DEFAULT_TOP_K` | Default retrieval depth |
| `MAX_TOP_K` | Maximum retrieval depth |
| `RRF_K` | RRF fusion constant |
| `CORS_ALLOW_ORIGINS` | Allowed frontend origins |
| `LOG_LEVEL` | Application logging level |

See `.env.example` for the complete configuration surface.

Never commit `.env` or credentials to Git.

---

## Testing

Run the non-integration suite:

```powershell
pytest -m "not integration"
```

Run Qdrant integration tests when Qdrant is available:

```powershell
pytest -m integration
```

Frontend checks:

```powershell
cd frontend
npm run typecheck
npm run build
```

The test suite covers areas including:

- scanner edge cases
- archive validation and upload safety
- structural parsing
- incremental indexing
- file hashing
- SQLite FTS5 retrieval
- Qdrant vector storage
- hybrid/RRF retrieval
- context construction
- prompt grounding and injection resistance
- LLM client behaviour
- API contracts

The LLM is stubbed in unit/API tests, so Ollama is not required to run the normal test suite.

---

## Evaluation

The repository includes an evaluation harness under `evaluation/`.

Example:

```bash
python -m evaluation.benchmark \
  --repository /repositories/example \
  --queries evaluation/queries.example.json \
  --output evaluation/results.json
```

The evaluation harness can measure retrieval quality using metrics such as Recall@k, MRR, hit rate, and retrieval latency.

Do not treat synthetic/offline benchmark results as evidence of production retrieval quality; evaluate against a representative codebase and manually inspect grounded answers as well.

---

## Limitations

- Retrieval is chunk-level and does not currently construct a complete call graph or import graph.
- Cross-file reasoning is limited by the retrieval/context budget.
- Parser rules do not cover every grammar corner of every supported language.
- SQLite and Qdrant are convergent rather than transactionally coupled.
- One embedding model/dimension is used for the Qdrant collection; changing embedding dimensions requires recreating/reindexing the collection.
- Indexing is currently synchronous, so a large repository can keep an HTTP request open for a significant amount of time.
- Uploads are whole-archive uploads rather than resumable/chunked uploads.
- Only ZIP archive upload is currently supported; Git URL and `tar.gz` import are not part of the current upload workflow.
- Local Ollama inference speed depends heavily on available CPU/GPU/RAM.

---

## Roadmap

Potential next improvements:

- Background indexing jobs with progress reporting / SSE.
- Authentication and per-user repository isolation.
- Rate limiting and resource quotas for public deployments.
- Import/call-graph retrieval signals.
- Cross-encoder reranking.
- Citation verification against retrieved evidence.
- Git URL and `tar.gz` imports.
- Git-aware indexing by commit and diff.
- More robust multi-tenant persistence and object storage.
- GPU-backed hosted inference for lower query latency.

---

## Docker persistence

The Docker deployment uses named volumes for persistent state:

```text
repomind-repositories   uploaded/extracted repositories
repomind-data           SQLite database
qdrant-data             Qdrant vectors
model-cache             model/cache data where applicable
```

A normal:

```powershell
docker compose down
```

does **not** remove named volumes.

Avoid:

```powershell
docker compose down -v
```

unless you intentionally want to delete the persisted Docker volumes and rebuild the stored data from scratch.

---

## License

MIT

