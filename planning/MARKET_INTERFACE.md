# Market Data Interface: Unified Python API

The single Python API through which every part of the FinAlly backend obtains stock prices.
It uses the **Massive REST API** when `MASSIVE_API_KEY` is set and non-empty, and the
built-in **GBM simulator** otherwise. Downstream code (SSE, trades, portfolio valuation,
the LLM context, snapshots) never knows or cares which one is running.

Related docs: `MASSIVE_API.md` (provider reference), `MARKET_SIMULATOR.md` (simulator
design), `MARKET_DATA_SUMMARY.md` (what is built), `PLAN.md` §6 (requirements).

> **Status.** The package `backend/app/market/` already implements most of this design.
> This document is the **target contract**. Where current code differs, §9 lists the
> gaps: Task 0 items T0.1–T0.4 from PLAN §6, plus new Massive findings T0.5–T0.8 from the
> `MASSIVE_API.md` research.

---

## 1. Architecture

```
                 env: MASSIVE_API_KEY
                          │
            create_market_data_source(cache)            ← factory.py
                 ┌────────┴─────────┐
                 ▼                  ▼
      SimulatorDataSource    MassiveDataSource           ← implement MarketDataSource (interface.py)
      (GBM, 0.5 s ticks)     (REST poll, 15 s;
                              snapshot or EOD strategy)
                 └────────┬─────────┘
                          │  cache.update(ticker, price, ts)    (writers: exactly one source)
                          ▼
                     PriceCache                          ← cache.py  (thread-safe, versioned)
                          │  get / get_price / get_all / version
       ┌──────────────┬───┴──────────┬──────────────┬─────────────────┐
       ▼              ▼              ▼              ▼                 ▼
  SSE stream     trade execution  GET /api/      snapshot task    LLM portfolio
  stream.py      (price lookup)   portfolio,     (30 s)           context
                                  watchlist
```

**Two rules hold everything together:**

1. **Producers push, consumers pull.** A data source writes to `PriceCache` on its own
   schedule. Nobody asks a data source for a price. Everybody reads the cache.
2. **The source tracks exactly `watchlist ∪ positions`.** The application layer decides
   membership (it owns the DB). The source just does what it is told via `add_ticker` /
   `remove_ticker`.

---

## 2. Public API (`app.market`)

```python
from app.market import (
    PriceUpdate,                 # immutable price snapshot
    PriceCache,                  # shared in-memory store
    MarketDataSource,            # abstract interface
    create_market_data_source,   # env-driven factory
    create_stream_router,        # SSE router factory
    Ticker, normalize_ticker,    # NEW: shared ticker type/validator (see §3)
)
```

### 2.1 `PriceUpdate` (`models.py`)

```python
@dataclass(frozen=True, slots=True)
class PriceUpdate:
    ticker: str
    price: float            # rounded to 2 dp by PriceCache
    previous_price: float   # the price at the previous cache update (tick-to-tick)
    timestamp: float        # Unix seconds

    change: float           # property: price - previous_price (4 dp)
    change_percent: float   # property: % vs previous_price (4 dp), 0.0 if previous is 0
    direction: str          # property: "up" | "down" | "flat"

    def to_dict(self) -> dict: ...   # the 7 SSE fields, in PLAN §6 order
```

`change` / `change_percent` are **tick-to-tick**, not day-over-day. That is what drives
the price-flash animation and the watchlist "%" column (PLAN §10).

### 2.2 `PriceCache` (`cache.py`)

```python
class PriceCache:
    def update(self, ticker: str, price: float, timestamp: float | None = None) -> PriceUpdate
    def get(self, ticker: str) -> PriceUpdate | None
    def get_price(self, ticker: str) -> float | None
    def get_all(self) -> dict[str, PriceUpdate]          # shallow copy
    def remove(self, ticker: str) -> None                # MUST bump version (T0.2)
    @property
    def version(self) -> int                             # monotonic; bumped on update AND remove
    def __len__(self) -> int
    def __contains__(self, ticker: str) -> bool
```

Contract:
- Thread-safe (a `threading.Lock`). Every mutation happens on the event loop today, but
  the lock keeps `to_thread` helpers safe.
- The first `update` for a ticker sets `previous_price == price` (`direction="flat"`).
- `version` increments on **every** state change, including `remove`. SSE relies on
  this to push a snapshot that no longer contains the removed ticker.
- `remove()` of an unknown ticker is a no-op. Whether it bumps `version` in that case
  doesn't matter: an extra identical SSE frame is harmless.

### 2.3 `MarketDataSource` (`interface.py`)

```python
class MarketDataSource(ABC):
    async def start(self, tickers: list[str]) -> None   # call exactly once; launches background task
    async def stop(self) -> None                        # idempotent; no cache writes afterwards
    async def add_ticker(self, ticker: str) -> None     # idempotent; normalizes input
    async def remove_ticker(self, ticker: str) -> None  # idempotent; normalizes; also cache.remove()
    def get_tickers(self) -> list[str]                  # current tracked set (copy)
```

Behavioural contract, which every implementation must pass in a shared conformance test (§8):

| Method | Requirement |
|---|---|
| `start(tickers)` | Normalizes and de-duplicates `tickers`. Writes initial prices into the cache **before returning** if it can do so without delay: the simulator always, Massive if the first poll succeeds. Starts exactly one background task. Must not raise on network failure. Massive logs the error and retries on the next interval. |
| `stop()` | Cancels the task and awaits it. Safe to call twice or before `start`. |
| `add_ticker(t)` | `t = t.strip().upper()`. No-op if tracked. The simulator seeds a price into the cache **immediately**. Massive includes it in the next poll, and in EOD mode it fills it immediately from the bars it already fetched. |
| `remove_ticker(t)` | `t = t.strip().upper()`. Removes from the tracked set **and** calls `cache.remove(t)`. No-op if absent. |
| `get_tickers()` | Returns a copy, in insertion order. |

The background task **must never die** from a single bad iteration. Wrap each
iteration's body in `try/except Exception` and log the error. `CancelledError` must
propagate so `stop()` works.

### 2.4 `create_market_data_source` (`factory.py`)

```python
def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)  # poll_interval=15.0
    return SimulatorDataSource(price_cache=price_cache)                     # update_interval=0.5
```

- Reads the environment **at call time** (inside lifespan, after `load_dotenv()`).
- Returns an **unstarted** source. The caller awaits `start()`.
- Whitespace-only keys count as unset.
- Logs which source was chosen, but never logs the key.

### 2.5 `create_stream_router` (`stream.py`)

```python
def create_stream_router(price_cache: PriceCache) -> APIRouter   # fresh APIRouter per call (T0.4)
```

`GET /api/stream/prices` → `text/event-stream`:
1. First frame: `retry: 1000\n\n`.
2. Every ~500 ms, if `price_cache.version` changed, emit
   `data: {"AAPL": {...7 fields...}, ...}\n\n`, which is the full `get_all()` map.
   **An empty map is emitted as `data: {}`** (T0.3).
3. Exits when `request.is_disconnected()`.

The cache contains exactly the tracked set (sources only write tracked tickers, and
`remove_ticker` clears the cache), so "all cached prices" == "watchlist ∪ positions".

---

## 3. Ticker normalization (single source of truth)

PLAN §6 makes the **API layer** the validation authority. Define the rule once, in
`app/market/tickers.py`, and use it everywhere (request models, path params, LLM actions,
and as defence in depth inside both sources):

```python
# app/market/tickers.py
import re
from typing import Annotated
from pydantic import AfterValidator, BeforeValidator

TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

def normalize_ticker(value: str) -> str:
    """strip().upper(). Does not validate; safe for sources."""
    return value.strip().upper()

def _validate(value: str) -> str:
    if not TICKER_RE.fullmatch(value):
        raise ValueError("ticker must be 1-5 letters A-Z")
    return value

Ticker = Annotated[
    str,
    BeforeValidator(lambda v: normalize_ticker(v) if isinstance(v, str) else v),
    AfterValidator(_validate),
]
```

```python
class TradeRequest(BaseModel):
    ticker: Ticker
    side: Literal["buy", "sell"]
    quantity: Annotated[float, Field(gt=0, allow_inf_nan=False)]

@router.delete("/api/watchlist/{ticker}")
async def remove(ticker: Annotated[Ticker, Path()]): ...
```

Invalid input fails with **422** automatically. LLM-originated actions are validated with
the same `TradeRequest` / `WatchlistChange` models, and a validation failure becomes an
action with `status: "failed"` (PLAN §9).

---

## 4. Simulator source (summary)

`SimulatorDataSource(price_cache, update_interval=0.5, event_probability=0.001)` wraps a
`GBMSimulator`. `start()` builds the simulator, seeds the cache with every starting price,
and launches the 500 ms loop. `add_ticker()` seeds the new ticker's price into the cache
at once (so a buy can execute immediately). Full design: `MARKET_SIMULATOR.md`.

---

## 5. Massive source (design)

`MassiveDataSource(api_key, price_cache, poll_interval=15.0)`.

### 5.1 Fetch strategies

The Massive plan behind a key is unknown until we call the API, and the free plan has
**no snapshot access** (see `MASSIVE_API.md` §1). The source therefore has two strategies
and picks one at runtime:

| Strategy | Endpoint | When | Price written | Effective interval |
|---|---|---|---|---|
| `snapshot` (default) | `get_snapshot_all(STOCKS, tickers)` | paid plans | last trade, falling back through `min` → `day` → `prev_day` close | `poll_interval` (15 s) |
| `eod` | `get_grouped_daily_aggs(date)`, walking back to the latest trading day | after a snapshot call fails with `NOT_AUTHORIZED` | that day's `close` | `max(poll_interval, 300 s)` |

The switch to `eod` is one-way for the life of the process and is logged once at WARNING
("Massive plan has no snapshot access; showing end-of-day closes").

In `eod` mode the source keeps the **whole-market** bar map from the last fetch, keyed by
ticker. `add_ticker()` can then write a price straight away with no extra API call. It
refetches when the interval elapses, which is cheap: usually one call.

### 5.2 Skeleton

```python
class MassiveDataSource(MarketDataSource):
    EOD_MIN_INTERVAL = 300.0

    def __init__(self, api_key: str, price_cache: PriceCache, poll_interval: float = 15.0) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._mode: Literal["snapshot", "eod"] = "snapshot"
        self._eod_bars: dict[str, GroupedDailyAgg] = {}
        self._client: RESTClient | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key, retries=1)   # explicit key; low retries (rate limit)
        self._tickers = list(dict.fromkeys(normalize_ticker(t) for t in tickers))
        await self._poll_once()                                       # immediate data; never raises
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        if self._mode == "eod" and (bar := self._eod_bars.get(ticker)) and bar.close:
            self._cache.update(ticker, bar.close, bar.timestamp / 1000)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)

    async def _poll_loop(self) -> None:
        while True:
            interval = self._interval if self._mode == "snapshot" else max(self._interval, self.EOD_MIN_INTERVAL)
            await asyncio.sleep(interval)
            await self._poll_once()

    async def _poll_once(self) -> None:
        tickers = list(self._tickers)         # copy: add/remove may run while the thread works
        if not tickers or not self._client:
            return
        try:
            prices = await (self._poll_snapshot(tickers) if self._mode == "snapshot"
                            else self._poll_eod(tickers))
        except BadResponse as e:
            if self._mode == "snapshot" and "NOT_AUTHORIZED" in str(e):
                logger.warning("Massive plan has no snapshot access; switching to end-of-day prices")
                self._mode = "eod"
                return await self._poll_once()
            logger.error("Massive poll failed: %s", _redact(e)); return
        except Exception as e:
            logger.error("Massive poll failed: %s", e); return

        current = set(self._tickers)          # drop results for tickers removed mid-poll
        for ticker, (price, ts) in prices.items():
            if ticker in current:
                self._cache.update(ticker, price, ts)
```

`_poll_snapshot` calls `get_snapshot_all` in `asyncio.to_thread` and applies
`extract_price()` (`MASSIVE_API.md` §3.3: `last_trade.sip_timestamp / 1e9`, **not**
`last_trade.timestamp / 1000`). `_poll_eod` calls `latest_grouped_daily()` in
`asyncio.to_thread`, stores `self._eod_bars`, and returns `{t: (bar.close, bar.timestamp/1000)}`
for the tracked tickers.

### 5.3 Behaviour notes

- **Price not yet available.** In snapshot mode, a ticker added between polls has no cached
  price for up to 15 s. A buy in that window returns **400 "Price not yet available for X"**
  (PLAN §7). This is expected. The frontend shows the error, and the user retries.
- **Unknown symbols** (valid format, not listed, e.g. `ZZZZZ`) never get a price. They sit
  in the watchlist with `price: null`. Trades on them return 400.
- **Market closed.** Snapshot keeps returning the last trade. `PriceCache.update` still
  bumps `version`, so SSE re-sends identical prices with `direction: "flat"`. That is fine.
- **Rate limits.** One request per poll regardless of ticker count. 15 s → 4 req/min,
  which is under the free tier's 5/min. In `eod` mode a poll may cost 1–3 requests (the
  date walk-back) every 5 minutes.
- **Key hygiene.** Never log the key. `BadResponse` bodies don't contain it, but redact
  defensively.

---

## 6. Application integration

### 6.1 Lifespan wiring (`app/main.py`)

`create_stream_router(price_cache)` needs the cache when the router is built, which is
before the lifespan runs. So `create_app()` creates the `PriceCache`, and the lifespan
picks it up from `app.state`. Each `create_app()` call gets its own cache, router and
source, which keeps tests isolated.

```python
def create_app() -> FastAPI:
    load_dotenv()
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = init_db(resolve_db_path())              # schema + seed + initial snapshot (PLAN §7)
        source = create_market_data_source(cache)    # reads MASSIVE_API_KEY now
        await source.start(tracked_tickers(db))      # watchlist ∪ positions
        snapshot_task = asyncio.create_task(snapshot_loop(db, cache), name="portfolio-snapshots")
        app.state.db, app.state.market = db, source
        try:
            yield
        finally:
            snapshot_task.cancel()
            await asyncio.gather(snapshot_task, return_exceptions=True)
            await source.stop()

    app = FastAPI(lifespan=lifespan)
    app.state.price_cache = cache
    app.include_router(create_stream_router(cache))  # fresh router per app (T0.4)
    # ... other routers, password middleware, static files mounted last
    return app

app = create_app()
```

Expose dependencies for routes:

```python
def get_cache(request: Request) -> PriceCache:          return request.app.state.price_cache
def get_market(request: Request) -> MarketDataSource:   return request.app.state.market
```

### 6.2 Keeping the tracked set = `watchlist ∪ positions`

All membership decisions live in one helper module so the rule is enforced identically by
the watchlist routes, the trade path and the LLM action executor:

```python
# app/services/tracking.py
async def ensure_tracked(market: MarketDataSource, ticker: str) -> None:
    await market.add_ticker(ticker)                      # idempotent

async def untrack_if_unused(db, market: MarketDataSource, ticker: str) -> None:
    """Call AFTER the DB change has committed."""
    if not in_watchlist(db, ticker) and not has_position(db, ticker):
        await market.remove_ticker(ticker)               # also clears PriceCache → SSE drops it
```

| Event | DB change | Market call |
|---|---|---|
| `POST /api/watchlist` | insert watchlist row | `ensure_tracked` |
| `DELETE /api/watchlist/{t}` | delete watchlist row | `untrack_if_unused` (keeps it if a position is open) |
| Buy | upsert position (+ auto-add watchlist row if missing) | `ensure_tracked` **before** price lookup |
| Sell to zero | delete position row | `untrack_if_unused` (keeps it if still watched) |
| Startup | none | `start(watchlist ∪ positions)` |

### 6.3 Reading prices

```python
price = cache.get_price(ticker)          # trades: None → 400 "Price not yet available for X"
value = cash + sum(p.quantity * (cache.get_price(p.ticker) or p.avg_cost) for p in positions)
                                         # valuation: avg_cost fallback (PLAN §7)
```

Trade handlers should read the price **once** and use that value for both the cash check
and the fill. A tick in between must not change the result.

---

## 7. Configuration

| Variable | Effect |
|---|---|
| `MASSIVE_API_KEY` | Non-empty → `MassiveDataSource`. Otherwise → `SimulatorDataSource`. |

Intervals are constructor arguments, not environment variables: simulator 0.5 s, Massive
15 s, EOD floor 300 s. Tests pass smaller values.

---

## 8. Testing the interface

- **Conformance suite** (`tests/market/test_interface_conformance.py`), parametrized over
  both sources (Massive with a fake client): normalization of `" aapl "`, idempotent
  add/remove, `remove_ticker` clears the cache and bumps `version`, `stop()` twice is
  safe, `get_tickers()` returns a copy.
- **PriceCache:** `remove` bumps `version` (T0.2).
- **SSE:** a fresh router per factory call (two apps → no duplicate routes, T0.4). The
  stream emits `data: {}` after the last ticker is removed (T0.3).
- **Massive:** build fixtures with **real model classes**
  (`TickerSnapshot.from_dict(json)`, `GroupedDailyAgg.from_dict(json)`), never bare
  `MagicMock`s. Cases to cover: ns→s timestamp; `last_trade=None` falls back to `min`/`day`/
  `prev_day`; zeroed `day` after reset; a `NOT_AUTHORIZED` `BadResponse` switches to `eod`
  and fetches grouped daily; empty grouped daily walks back one day; `add_ticker` in `eod`
  mode fills from cached bars; a ticker removed mid-poll is not re-added to the cache.
- **Factory:** empty or whitespace key → simulator. Key set → Massive.

---

## 9. Gaps between this contract and current code

| # | Gap | Where | Fix |
|---|---|---|---|
| T0.1 | Sources don't normalize in all methods | `SimulatorDataSource.start/add_ticker/remove_ticker`; `MassiveDataSource.start` | Apply `normalize_ticker()` everywhere (§2.3) |
| T0.2 | `PriceCache.remove()` doesn't bump `version` | `cache.py` | `self._version += 1` inside the lock |
| T0.3 | Empty cache never emits | `stream.py` (`if prices:`) | Always emit, including `data: {}` |
| T0.4 | Module-level `router` | `stream.py:17` | Create `APIRouter` inside the factory |
| **T0.5** | **Massive mode writes no prices at all.** `snap.last_trade.timestamp` doesn't exist on `LastTrade` (the field is `sip_timestamp`, in **ns**), so every snapshot hits the `AttributeError` handler and is skipped. | `massive_client.py` `_poll_once` | Use `extract_price()` (`MASSIVE_API.md` §3.3) |
| **T0.6** | Free-plan keys can't use snapshots (`NOT_AUTHORIZED`), so free users get no prices | `massive_client.py` | Add the `eod` strategy (§5.1) |
| **T0.7** | Massive tests mock snapshots with `MagicMock`, which hid T0.5 | `tests/market/test_massive.py` | Use `TickerSnapshot.from_dict(...)` fixtures |
| **T0.8** | `RESTClient` retries 429 three times, burning the free quota; `_fetch_snapshots` reads the mutable `self._tickers` from a worker thread | `massive_client.py` | `RESTClient(api_key=…, retries=1)`; pass a copied ticker list |

T0.5–T0.8 were found during the `MASSIVE_API.md` research and are now logged in PLAN §6
"Known Gaps" as part of Task 0 (milestone M0).
