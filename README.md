# RepoMind

Ask a codebase where things live, and get an answer that points at real files and
line numbers.

RepoMind indexes a local repository structurally (functions, classes, methods —
not arbitrary 500-character slices), embeds those units, and answers questions
using hybrid retrieval plus a language model that is forbidden from asserting
anything the retrieved evidence does not show.

---

## The problem

Asking a general-purpose chat model about your repository fails in two specific
ways:

1. **It does not have your code.** It answers from priors about how codebases
   usually look, and the answer is fluent and wrong.
2. **Naive RAG makes it worse.** Splitting source files into fixed-size text
   windows cuts functions in half, so a retrieved chunk often contains a
   signature with no body or a body with no name. Citations drift and the model
   fills the gap with invention.

RepoMind addresses both: chunks follow the syntax tree, every answer is
constrained to retrieved evidence, and every claim carries a `file:line-line`
citation the reader can check in seconds.

---

## Architecture

```
                    ┌──────────────────────────────┐
                    │   React + TypeScript (Vite)  │
                    └───────────────┬──────────────┘
                                    │ HTTP
                    ┌───────────────▼──────────────┐
                    │      FastAPI  (api/)         │
                    │  path allowlist, schemas     │
                    └───────────────┬──────────────┘
                                    │
                    ┌───────────────▼──────────────┐
                    │   ServiceContainer           │
                    │   one embedder, one client   │
                    └──┬─────────────┬─────────────┘
                       │             │
         ┌─────────────▼───┐    ┌────▼──────────────────┐
         │  IngestionSvc   │    │     RagService        │
         └────┬────────────┘    └────┬──────────────────┘
              │                      │
   scan → parse → embed         retrieve → context → prompt → LLM
      │      │       │               │
      │      │       │          ┌────▼─────────┐
      │      │       │          │ RetrievalSvc │
      │      │       │          │ semantic ────┼──► Qdrant
      │      │       │          │ keyword  ────┼──► SQLite FTS5 (BM25)
      │      │       │          │ hybrid   ────┼──► RRF fusion
      │      │       │          └──────────────┘
      │      │       └──────────────────────────► Qdrant  (vectors + payload)
      │      └──────────────────────────────────► SQLite  (FTS5 index)
      └─────────────────────────────────────────► SQLite  (file digests, chunks)
```

Three storage responsibilities, deliberately separate:

| Store | Holds | Why |
|---|---|---|
| SQLite `files`/`chunks` | SHA-256 digests, chunk coordinates | decides new / modified / unchanged / deleted |
| SQLite FTS5 | chunk text, symbols, paths | exact-identifier search with BM25 |
| Qdrant | vectors + citation payload | semantic similarity |

---

## Features

- Structural chunking: Python via the standard `ast`, C/C++/Java/JS/TS/TSX via
  tree-sitter, Markdown by heading.
- Incremental indexing driven by content hashes, with deterministic chunk IDs.
- Hybrid retrieval: dense + BM25 fused with Reciprocal Rank Fusion.
- Grounded answers with file and line citations, and an explicit "I don't have
  the evidence" path.
- Prompt-injection resistance: repository content is framed and sanitised as
  untrusted data.
- Repository-root allowlisting, traversal and symlink protection, secret-file
  exclusion, size and count limits.
- FastAPI service, React UI, Docker Compose with Qdrant, CLI, evaluation harness.

---

## Tech stack

**Backend** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, pytest
**Parsing** Python `ast`, tree-sitter
**Storage** SQLite (state + FTS5), Qdrant
**Embeddings** sentence-transformers, default `all-MiniLM-L6-v2` (384-d, CPU)
**LLM** Gemini via REST, behind an `LLMClient` protocol
**Frontend** React 18, TypeScript, Vite
**Infra** Docker, Docker Compose

---

## Setup

### Local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # then fill in GEMINI_API_KEY

docker run -p 6333:6333 -v "$PWD/data/qdrant:/qdrant/storage" qdrant/qdrant:v1.9.0

export REPOSITORIES_ROOT="$PWD/repositories"
export DATABASE_PATH="$PWD/data/repomind.db"
export QDRANT_HOST=localhost

uvicorn repomind.api.main:app --reload --port 8000
```

### Docker

```bash
cp .env.example .env          # GEMINI_API_KEY at minimum
git clone <your-repo> repositories/example
docker compose up --build
```

The API listens on `http://localhost:8000`; OpenAPI docs are at `/docs`.
Repositories are bind-mounted **read-only** — RepoMind never writes to or
executes the code it analyses.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `QDRANT_HOST` / `QDRANT_PORT` | `localhost` / `6333` | vector store location |
| `QDRANT_COLLECTION` | `repomind_chunks` | collection name |
| `VECTOR_BACKEND` | `qdrant` | `memory` runs without Qdrant (nothing persists) |
| `LLM_PROVIDER` | `gemini` | provider selector |
| `GEMINI_API_KEY` | *(empty)* | unset ⇒ retrieval works, generation is disabled |
| `GEMINI_MODEL` | `gemini-2.0-flash` | model id |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | `hashing` selects the offline encoder |
| `REPOSITORIES_ROOT` | `/repositories` | **allowlist root — every path must resolve inside it** |
| `DATABASE_PATH` | `/data/repomind.db` | SQLite state + FTS5 |
| `MAX_FILE_BYTES` | `1048576` | per-file size ceiling |
| `MAX_CONTEXT_CHARACTERS` | `24000` | evidence budget per question |
| `RRF_K` | `60` | fusion constant |
| `CORS_ALLOW_ORIGINS` | `http://localhost:5173` | comma-separated |

Full list in `.env.example`. Secrets are never logged; `Settings.gemini_api_key`
is excluded from `repr`, and the Gemini key travels in a header rather than a
URL so it cannot leak into access logs.

---

## API

```
GET  /health                         liveness, touches nothing
GET  /ready                          per-dependency readiness
POST /repositories/index             index or incrementally re-index
GET  /repositories/status            counts and languages for one repository
GET  /repositories                   every indexed repository
POST /repositories/query             grounded answer with citations
POST /repositories/search            raw retrieval, no generation
```

```bash
curl -X POST localhost:8000/repositories/query \
  -H 'Content-Type: application/json' \
  -d '{
        "repository_path": "/repositories/example",
        "question": "Where is authentication implemented?",
        "top_k": 5,
        "mode": "hybrid"
      }'
```

```json
{
  "question": "Where is authentication implemented?",
  "answer": "Authentication is handled by TokenService in app/auth.py:8-24 ...",
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

### CLI

```bash
python -m repomind index  /repositories/example
python -m repomind search /repositories/example "token validation" --mode keyword
python -m repomind query  /repositories/example "How are sessions invalidated?"
python -m repomind status /repositories/example
```

---

## Frontend usage

Enter a repository path, index it, then ask. The left rail shows live index
state (files, chunks, languages, last run, per-service health); the main column
holds the question, the retrieval-mode switch, the answer, and the citation list.
Citations get the strongest visual treatment on the page because verifying them
is the workflow.

---

## Retrieval architecture

**Chunking.** A class does not swallow its methods. The class chunk carries the
declaration, docstring and class-level attributes; each method is its own chunk.
Storing the class body twice would waste index space and blur the embedding.
Module-level code (imports, constants, script bodies) is preserved as contiguous
`MODULE` chunks with true line ranges. Fixed-size windowing exists only as a
fallback for files that fail to parse — a syntax error degrades one file, never
the run.

**Embedded text.** Each chunk is embedded with a metadata header
(`path | kind symbol`) prepended to its body, because file paths and symbol names
carry real signal for "where is X" questions.

**Semantic.** Cosine similarity over Qdrant, with payload indexes on
`repository_path`, `file_path`, `language` and `chunk_type` so repository
filtering does not degrade into a full scan.

**Keyword.** SQLite FTS5 with BM25, column weights `symbol 6 : path 2 : content 1`.
Identifiers are stored both verbatim and camel/snake-split, so `getUserToken`
matches `user` and `token`. Query terms are extracted with a whitelist regex and
re-quoted, which makes FTS5 operator injection impossible.

**Why both.** Embeddings are poor at exact identifiers — asking for
`ERR_TOKEN_EXPIRED` returns "something about authentication". BM25 is poor at
paraphrase — "how do we keep people logged in" matches nothing. Each covers the
other's failure mode.

### Hybrid retrieval

Reciprocal Rank Fusion, not a weighted score sum:

```
score(d) = Σ  1 / (k + rank(d, list))      k = 60
```

Cosine similarity (≈0–1) and BM25 (unbounded, corpus-dependent) are not
comparable quantities, and per-query normalisation is unstable when one list is
short or empty. RRF consumes only ranks, so it is immune to both problems. Each
backend is queried for `max(3 × top_k, 20)` candidates so fusion has room to
promote a document that ranks moderately well in both lists over one that ranks
first in only one. `k = 60` is the value from Cormack et al.; smaller `k` lets a
single list dominate, larger `k` flattens the advantage of top ranks.

Every result is returned with `match_type` (`semantic` / `keyword` / `hybrid`)
and its per-backend rank, so retrieval behaviour is inspectable rather than a
black box.

---

## Incremental indexing

State is keyed on SHA-256 of file content, not mtime or size, so a touched file
is correctly skipped and a reverted file is correctly recognised as unchanged.

| Case | Action |
|---|---|
| New file | parse → embed → store |
| Unchanged digest | skip entirely |
| Changed digest | delete old chunks from all three stores → reparse → re-embed → store |
| Missing from scan | delete chunks and state |

Chunk IDs are UUIDv5 over `(repository, path, kind, symbol, start, end)`. They
are deterministic — so upserts replace instead of duplicating — and UUID-shaped,
which Qdrant requires for point IDs.

There is no distributed transaction across SQLite and Qdrant. Instead the
pipeline is **idempotent**: deletes always precede writes, IDs are stable, and
re-running after a partial failure converges to the correct state.

---

## Testing

```bash
pytest -m "not integration"      # unit + API, no external services
pytest -m integration            # requires a running Qdrant
```

The suite runs entirely offline: an in-memory vector store and a deterministic
hashing embedder stand in for Qdrant and sentence-transformers, and the LLM is a
stub that records the prompts it receives. Coverage includes scanner edge cases
(binary, invalid UTF-8, symlinks, secrets, size and count limits), AST chunk
shapes and line accuracy, the full new/modified/unchanged/deleted state machine,
BM25 ranking and FTS injection attempts, RRF arithmetic and tie-breaking, context
budgeting and deduplication, prompt-injection containment, Gemini error handling
and key hygiene, path-traversal rejection, and the HTTP contract end to end.

Tests assert behaviour, not importability — for example, that a modified file
leaves no orphaned chunks, and that a file containing `</evidence>` cannot close
the evidence block in the prompt.

---

## Evaluation

```bash
python -m evaluation.benchmark \
  --repository /repositories/example \
  --queries evaluation/queries.example.json \
  --output evaluation/results.json
```

Reports, per mode (`keyword`, `semantic`, `hybrid`): Recall@1/@3/@5, MRR@5,
Hit Rate@5, mean and p95 retrieval latency. Separately times a full rebuild, a
no-op re-index and a single-file change, which is how the incremental path is
measured rather than assumed.

Relevance is judged at file granularity, which suits the question this system
answers ("where is X implemented"). Write your own `queries.json` against a
repository you know well; the bundled file is a format example.

> **No benchmark numbers are published here.** The harness has been executed only
> against a three-file synthetic fixture using the offline hashing encoder, which
> measures nothing about real retrieval quality. Publishing numbers from that run
> would be dishonest. Run it on your own corpus with a real embedding model.

---

## Security

| Control | Implementation |
|---|---|
| Repository allowlist | every path resolved through `Settings.resolve_repository_path`, rejected unless it is inside `REPOSITORIES_ROOT` |
| Path traversal | `Path.resolve()` then containment check; `../`, absolute paths and symlinked escapes all rejected |
| Symlinks | never followed during scanning; symlinked files and directories are skipped outright |
| Secret exclusion | `.env*`, `*.pem`, `*.key`, `id_rsa`, keystores and similar are never read |
| Resource limits | per-file byte ceiling, per-repository file ceiling, context character budget |
| No execution | repository code is read as text and never imported, evaluated or run |
| Prompt injection | evidence delimiters neutralised in content, untrusted-data framing in the system prompt, question cannot close its own tag |
| Secrets in logs | API key excluded from `repr`, sent as a header, provider error bodies never echoed |
| Error responses | identical message for "outside root" and "does not exist", so the API cannot be used to probe the host filesystem |
| CORS | explicit origin allowlist, credentials disabled, methods limited to GET/POST |
| Container | non-root user, read-only repository mount, CPU-only wheels |

---

## Limitations

- Retrieval is chunk-level; it does not follow call graphs or resolve imports, so
  "what calls this function" is answered by lexical coincidence rather than
  analysis.
- Cross-file reasoning is limited by the context budget. Questions spanning many
  files get partial evidence.
- Tree-sitter node rules cover the common declaration forms per language, not
  every grammar corner (macro-heavy C++, decorators-as-declarations in TS).
- Markdown is chunked by heading; other config formats fall back to line windows.
- Consistency between SQLite and Qdrant is convergent, not transactional: a crash
  mid-file can leave a stale vector until the next index run.
- One embedding model per collection. Changing `EMBEDDING_MODEL` to a different
  dimension requires recreating the collection — this is detected and refused
  rather than silently corrupting the index.
- Indexing is synchronous. A very large repository blocks its request for the
  duration; a job queue would be the next step.

## Future improvements

- Import-graph and call-graph edges as retrieval signals.
- A reranker (cross-encoder) over fused candidates.
- Background indexing with progress streaming over SSE.
- Per-repository collections and multi-tenant isolation.
- Answer-level citation verification: check that every `file:line` the model
  emits actually appeared in the evidence, and flag it when it did not.
- Git-aware indexing: index by commit, diff between revisions.

---

## License

MIT
