# FinAlly Backend

FastAPI backend for the FinAlly AI Trading Workstation.

## Structure

- `app/` — Application code
  - `main.py` — FastAPI app factory, lifespan (DB init, market data, 30s snapshot loop), `APP_PASSWORD` middleware, `/api/health`, static file serving
  - `schemas.py` — Shared Pydantic request/response models and ticker/quantity validators
  - `db/` — SQLite schema, default seed data, and database helpers
  - `services/` — Portfolio/trade accounting, watchlist synchronization, and LLM chat orchestration
  - `routes/` — REST API routers (`/api/portfolio`, `/api/watchlist`, `/api/chat`)
  - `market/` — Market data subsystem (GBM simulator, Massive API poller, `PriceCache`, SSE `/api/stream/prices`)
- `market_data_demo.py` — Rich terminal dashboard demo for the GBM market simulator
- `tests/` — Pytest unit and integration test suite (`market/`, `test_db.py`, `test_portfolio.py`, `test_watchlist.py`, `test_chat.py`, `test_security_and_app.py`)

## Running Locally

```bash
cd backend
uv sync --python 3.12 --extra dev

# Run the FastAPI server (single worker)
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

# Run the Rich market data simulator demo
uv run market_data_demo.py
```

## Running Tests & Linting

```bash
cd backend
uv run pytest -v
uv run ruff check app tests
```

## Environment Variables

See `../.env.example` for the full template:

- `GEMINI_API_KEY` — Google AI Studio API key for LLM chat (`gemini/gemini-3.1-flash-lite`)
- `MASSIVE_API_KEY` — Optional; uses Massive API when set, otherwise built-in GBM simulator
- `LLM_MOCK` — Optional; set to `true` for deterministic mock LLM responses
- `DB_PATH` — Optional; overrides SQLite path (defaults to `<repo_root>/db/finally.db` locally or `/app/db/finally.db` in Docker)
- `APP_PASSWORD` — Optional locally; when set, protects `/api/*` (except `/api/health`) via `X-App-Password` header (or `?key=` on `/api/stream/prices`)
