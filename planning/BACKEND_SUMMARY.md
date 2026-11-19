# FinAlly Backend — Summary (M0, M1, M2)

**Status:** Complete and tested (109 passing tests, 98% coverage, `ruff check` clean).

## Overview

The FinAlly backend (`backend/app/`) is a single-process FastAPI application managed with `uv`. It combines:

1. **Market Data Subsystem (`app/market/`, M0)** — `MarketDataSource` (`SimulatorDataSource` GBM default + `MassiveDataSource` snapshot/EOD poller), thread-safe `PriceCache`, SSE router (`/api/stream/prices`), and Rich terminal demo (`backend/market_data_demo.py`). See `planning/MARKET_DATA_SUMMARY.md` for market-data-specific details.
2. **Database & REST API (`app/db/`, `app/services/`, `app/routes/`, `app/main.py`, M1)** — SQLite persistence initialized during FastAPI lifespan startup, portfolio & atomic trade accounting, watchlist CRUD synchronized with `MarketDataSource`, periodic portfolio snapshots, health check, OpenAPI schema, and optional `APP_PASSWORD` middleware.
3. **LLM Chat Assistant (`app/services/chat.py`, `app/routes/chat.py`, M2)** — Async LiteLLM (`litellm.acompletion`) integration via OpenRouter (`openrouter/openai/gpt-oss-120b` with Cerebras provider ordering) using strict Pydantic structured outputs (`LLMResponse`), deterministic `LLM_MOCK=true` mode, single retry with HTTP 200 fallback, auto-execution of trades and watchlist changes, and in-memory 10 req/min rate limiting.

## Module Map

| Path | Responsibility |
|---|---|
| `app/main.py` | `create_app()` factory, FastAPI lifespan (DB init, market data start/stop, 30s snapshot loop), `APP_PASSWORD` middleware, `/api/health`, static file mount |
| `app/schemas.py` | Shared Pydantic request/response models, `Ticker` (`strip().upper()`, `^[A-Z]{1,5}$`) and `PositiveFiniteFloat` validators, strict LLM structured output models (`LLMResponse`, `Trade`, `WatchlistChange`) |
| `app/db/schema.py` | SQLite DDL (`users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`) and default seed constants |
| `app/db/database.py` | `Database` wrapper, `DB_PATH` resolution (local `<repo_root>/db/finally.db` vs Docker `/app/db/finally.db`), idempotent seeding, transaction context manager |
| `app/services/portfolio.py` | `PortfolioService` — valuation (with `avg_cost` fallback when price is uncached), atomic buy/sell execution, weighted-average cost, post-trade snapshot recording |
| `app/services/watchlist.py` | `WatchlistService` — watchlist queries and add/remove coordinated with `MarketDataSource` (retains tracked ticker if still held in `positions`) |
| `app/services/chat.py` | `ChatService` & `FixedWindowRateLimiter` — portfolio context builder, mock mode parser, async Cerebras/OpenRouter call with 30s timeout & 1 retry, action auto-execution |
| `app/routes/portfolio.py` | `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history` |
| `app/routes/watchlist.py` | `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}` |
| `app/routes/chat.py` | `GET /api/chat/history`, `POST /api/chat` |
| `app/market/` | Market data subsystem (see `planning/MARKET_DATA_SUMMARY.md`) |

## API Contract (`/openapi.json`)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/health` | Exempt from `APP_PASSWORD`; reports source type and tracked ticker count |
| `GET` | `/api/stream/prices` | SSE stream (`retry: 1000`); accepts `X-App-Password` header or `?key=` when `APP_PASSWORD` is set |
| `GET` | `/api/portfolio` | Cash balance, total value, unrealized P&L, weighted positions |
| `POST` | `/api/portfolio/trade` | Atomic market order (`buy`/`sell`); auto-adds unwatched ticker on buy; records snapshot |
| `GET` | `/api/portfolio/history` | Up to last 500 portfolio snapshots ordered `recorded_at ASC` |
| `GET` | `/api/watchlist` | Watched tickers with latest `PriceCache` fields |
| `POST` | `/api/watchlist` | Returns `201 Created` (`409` duplicate, `422` invalid ticker) |
| `DELETE` | `/api/watchlist/{ticker}` | Returns `200 OK` (`404` missing, `422` invalid); keeps ticker streaming if held |
| `GET` | `/api/chat/history` | Up to last 50 persisted messages ordered `created_at ASC` |
| `POST` | `/api/chat` | Rate limited (10 req/min → `429`); returns assistant response + `actions` array |

## Verification

```bash
cd backend
uv sync --python 3.12 --extra dev
uv run pytest -v
uv run ruff check app tests
```

- **109 tests passing (98% overall coverage)** across `tests/market/` (89 tests) and `tests/test_db.py`, `tests/test_portfolio.py`, `tests/test_watchlist.py`, `tests/test_chat.py`, `tests/test_security_and_app.py` (20 tests).
- **Market Data Demo:** `uv run market_data_demo.py`
- **Dev Server:** `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`
