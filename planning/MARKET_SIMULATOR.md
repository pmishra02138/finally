# Market Simulator: Approach and Code Structure

How FinAlly produces realistic, live-looking stock prices when no `MASSIVE_API_KEY` is set.
This is the **default** market data source, so most users only ever see the simulator.

Related: `MARKET_INTERFACE.md` (the contract the simulator implements), `PLAN.md` §6.

> **Status.** Implemented in `backend/app/market/simulator.py` and `seed_prices.py`, and
> covered by `tests/market/test_simulator.py` and `test_simulator_source.py`. This document
> describes that code and the changes it still needs (§8).

---

## 1. Goals

| Goal | How |
|---|---|
| Prices look like real stocks: continuous, never negative, proportional moves | Geometric Brownian Motion (GBM) |
| The dashboard feels alive | 500 ms ticks; a flash on nearly every tick |
| Stocks don't move independently | Sector-correlated random draws (Cholesky) |
| Occasional drama | Random 2–5 % shock events |
| Familiar starting point | Realistic seed prices for the 10 default tickers |
| Any ticker the user types works immediately | Unknown tickers seeded at a random $50–$300 |
| Zero dependencies, zero cost | Pure Python + NumPy, runs in-process as an asyncio task |

Non-goals: market hours, order-book microstructure, bid/ask spreads, volume, mean
reversion, fundamentals. The simulator runs 24/7.

---

## 2. The model: Geometric Brownian Motion

Each tick, every ticker's price evolves as:

```
S(t+dt) = S(t) · exp( (μ − σ²/2)·dt + σ·√dt·Z )
```

| Symbol | Meaning | Typical value |
|---|---|---|
| `S(t)` | current price | $190 |
| `μ` | annualized drift (expected return) | 0.05 |
| `σ` | annualized volatility | 0.22 |
| `dt` | tick length as a fraction of a trading year | 8.48 × 10⁻⁸ |
| `Z` | standard normal draw, **correlated across tickers** | N(0, 1) |

Why GBM:
- **Multiplicative.** `exp(·)` is always positive, so prices can never go negative, and a
  $800 stock moves proportionally more dollars than a $50 one.
- **Lognormal returns**, the textbook model behind Black–Scholes. Students may recognise it.
- **Cheap.** One `exp` per ticker per tick.
- The `−σ²/2` term (Itô correction) makes the *expected* price grow at exactly `μ`.

### Time scaling

The simulator treats wall-clock time as trading time:

```
TRADING_SECONDS_PER_YEAR = 252 days × 6.5 h × 3600 s = 5,896,800
dt = 0.5 s / 5,896,800 ≈ 8.48e-8
√dt ≈ 2.91e-4
```

So one simulated "trading day" of volatility accumulates over 6.5 real hours. What that
means per ticker (GBM component only):

| Ticker | σ | 1 tick | 1 tick ($) | 1 minute | 1 hour | 6.5 h ("1 day") |
|---|---|---|---|---|---|---|
| V | 0.17 | 0.005 % | $0.014 | 0.05 % | 0.42 % | 1.07 % |
| AAPL | 0.22 | 0.006 % | $0.012 | 0.07 % | 0.54 % | 1.39 % |
| NVDA | 0.40 | 0.012 % | $0.093 | 0.13 % | 0.99 % | 2.52 % |
| TSLA | 0.50 | 0.015 % | $0.036 | 0.16 % | 1.24 % | 3.15 % |

The drift term per tick is about 2 × 10⁻⁹, so μ is visually irrelevant at demo time scales.
It is kept for correctness.

Prices are held at full float precision internally and **rounded to 2 dp only on output**,
so rounding never accumulates. On low-priced tickers a sub-cent move rounds to the same
cent and shows as `direction: "flat"` for that tick. That is realistic and harmless.

---

## 3. Correlated moves (Cholesky)

Real stocks co-move: tech names rally together, banks together. The simulator draws `n`
independent normals and mixes them through the Cholesky factor `L` of a correlation
matrix `C` (`C = L·Lᵀ`):

```python
z_independent = np.random.standard_normal(n)
z_correlated  = L @ z_independent        # Cov(z_correlated) == C
```

### Correlation structure (`seed_prices.py`)

| Pair | ρ | Constant |
|---|---|---|
| Both in tech (AAPL, GOOGL, MSFT, AMZN, META, NVDA, NFLX) | 0.6 | `INTRA_TECH_CORR` |
| Both in finance (JPM, V) | 0.5 | `INTRA_FINANCE_CORR` |
| TSLA with anything | 0.3 | `TSLA_CORR` (checked first; TSLA "does its own thing") |
| Cross-sector, or any unknown/added ticker | 0.3 | `CROSS_GROUP_CORR` |

```python
@staticmethod
def _pairwise_correlation(t1: str, t2: str) -> float:
    if t1 == "TSLA" or t2 == "TSLA":
        return TSLA_CORR
    if t1 in tech and t2 in tech:
        return INTRA_TECH_CORR
    if t1 in finance and t2 in finance:
        return INTRA_FINANCE_CORR
    return CROSS_GROUP_CORR
```

**The matrix is always positive-definite**, so `np.linalg.cholesky` cannot fail for any
set of tickers. It decomposes as `0.3·J` (all-ones, PSD) plus block-diagonal sector extras
(0.3 within tech, 0.2 within finance, each a PSD all-ones block) plus a strictly positive
diagonal remainder (`1 − block ρ ≥ 0.4`). Anyone changing the constants must keep
`0 ≤ CROSS ≤ every intra-group ρ < 1` to preserve this.

`L` is rebuilt (O(n³), trivial for n < 50) **only when the ticker set changes**, never per
tick. With 0 or 1 tickers, `L` is `None` and draws are used as-is.

---

## 4. Random shock events

After the GBM update, each ticker independently has probability `event_probability`
(default **0.001**) per tick of a sudden shock:

```python
if random.random() < self._event_prob:
    shock = random.uniform(0.02, 0.05) * random.choice([-1, 1])
    self._prices[ticker] *= 1 + shock
```

Frequency at defaults: 10 tickers × 2 ticks/s × 0.001 = **one event roughly every 50 s**
somewhere on the board. That is about one per ticker every ~8 minutes, or ~7 per ticker
per hour. Shocks are independent across tickers (not correlated).

### Characteristic to be aware of: events dominate volatility

With ~7 shocks/hour at an RMS size of 3.6 %, shocks add **≈ 9.7 %/hour** of price
dispersion per ticker. Pure GBM gives ≈ 0.5 %/hour. So at the default settings,
*almost all visible movement over minutes to hours comes from events*, and over a long
session prices wander much further than real stocks do. Also, because `(1+u)(1−u) < 1`,
symmetric ± shocks carry a small **downward bias** (about −0.07 % per event, roughly
−0.5 %/hour per ticker).

This is acceptable for a short, dramatic demo and is the current tested behaviour. If
long-running sessions look unrealistic, tune it (§7):
- lower `event_probability` to `1e-4` (≈ one event per ticker every 80 minutes), and/or
- apply shocks log-symmetrically: `price *= math.exp(shock)`, which removes the bias.

---

## 5. Seed prices and per-ticker parameters (`seed_prices.py`)

```python
SEED_PRICES = {"AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0, "TSLA": 250.0,
               "NVDA": 800.0, "META": 500.0, "JPM": 195.0, "V": 280.0, "NFLX": 600.0}

TICKER_PARAMS = {                      # σ = annualized vol, μ = annualized drift
    "AAPL": {"sigma": 0.22, "mu": 0.05}, "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT": {"sigma": 0.20, "mu": 0.05}, "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA": {"sigma": 0.50, "mu": 0.03}, "NVDA":  {"sigma": 0.40, "mu": 0.08},
    "META": {"sigma": 0.30, "mu": 0.05}, "JPM":   {"sigma": 0.18, "mu": 0.04},
    "V":    {"sigma": 0.17, "mu": 0.04}, "NFLX":  {"sigma": 0.35, "mu": 0.05},
}
DEFAULT_PARAMS = {"sigma": 0.25, "mu": 0.05}   # any ticker not listed above
```

Unknown tickers (e.g. the user adds `PYPL`) start at `random.uniform(50, 300)` with
`DEFAULT_PARAMS` and 0.3 correlation to everything. The seed is drawn **at
`add_ticker()` time** and written to the `PriceCache` immediately (PLAN §6), so the
watchlist row shows a price and a buy can execute right away.

To make a new ticker feel "real", add it to `SEED_PRICES`, `TICKER_PARAMS` and, if it
fits, a `CORRELATION_GROUPS` set. No other code changes are needed.

---

## 6. Code structure

```
backend/app/market/
├── seed_prices.py   # data only: SEED_PRICES, TICKER_PARAMS, DEFAULT_PARAMS,
│                    #            CORRELATION_GROUPS, *_CORR constants
└── simulator.py
    ├── GBMSimulator          # pure, synchronous math engine (no asyncio, no cache)
    └── SimulatorDataSource   # async MarketDataSource adapter: loop + PriceCache writes
```

The split keeps the math **unit-testable without an event loop**. You can call `step()`
1,000 times and assert on the statistics. The adapter stays a thin layer of lifecycle glue.

### 6.1 `GBMSimulator`: the engine

```python
class GBMSimulator:
    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR

    def __init__(self, tickers: list[str], dt: float = DEFAULT_DT,
                 event_probability: float = 0.001) -> None
    def step(self) -> dict[str, float]          # advance all tickers one tick → {ticker: price (2 dp)}
    def add_ticker(self, ticker: str) -> None   # seed price + params, rebuild Cholesky; no-op if present
    def remove_ticker(self, ticker: str) -> None  # drop state, rebuild Cholesky; no-op if absent
    def get_price(self, ticker: str) -> float | None
    def get_tickers(self) -> list[str]

    # internals
    _tickers: list[str]                 # order == row order of the correlation matrix
    _prices:  dict[str, float]          # full-precision current prices
    _params:  dict[str, dict]           # {"sigma":…, "mu":…}
    _cholesky: np.ndarray | None
    def _add_ticker_internal(self, t)   # add without rebuild (batch init in __init__)
    def _rebuild_cholesky(self)
    @staticmethod
    def _pairwise_correlation(t1, t2) -> float
```

`step()` is the hot path, running every 500 ms:

```python
def step(self) -> dict[str, float]:
    n = len(self._tickers)
    if n == 0:
        return {}
    z = np.random.standard_normal(n)
    if self._cholesky is not None:
        z = self._cholesky @ z
    out = {}
    for i, t in enumerate(self._tickers):
        mu, sigma = self._params[t]["mu"], self._params[t]["sigma"]
        self._prices[t] *= math.exp((mu - 0.5 * sigma**2) * self._dt
                                    + sigma * math.sqrt(self._dt) * z[i])
        if random.random() < self._event_prob:                     # shock event
            self._prices[t] *= 1 + random.uniform(0.02, 0.05) * random.choice([-1, 1])
        out[t] = round(self._prices[t], 2)
    return out
```

### 6.2 `SimulatorDataSource`: the adapter

```python
class SimulatorDataSource(MarketDataSource):
    def __init__(self, price_cache: PriceCache, update_interval: float = 0.5,
                 event_probability: float = 0.001) -> None

    async def start(self, tickers):      # build GBMSimulator, seed cache with every price, start loop
    async def stop(self):                # cancel + await the task; idempotent
    async def add_ticker(self, ticker):  # sim.add_ticker, then cache.update(seed price) immediately
    async def remove_ticker(self, ticker):  # sim.remove_ticker, cache.remove
    def get_tickers(self):

    async def _run_loop(self):
        while True:
            try:
                for ticker, price in self._sim.step().items():
                    self._cache.update(ticker=ticker, price=price)
            except Exception:
                logger.exception("Simulator step failed")   # never let the loop die
            await asyncio.sleep(self._interval)
```

Concurrency: everything runs on the single asyncio event loop. `step()` is synchronous
and takes microseconds, so `add_ticker`/`remove_ticker` can never interleave with a step
half-way through. No locking is needed inside the simulator. The `PriceCache` has its own
lock for any thread-based readers. `CancelledError` is not caught by `except Exception`,
so `stop()` cancels cleanly.

The loop sleeps `update_interval` *after* each step, so the real period is
0.5 s + step time. That gap is negligible, and nothing depends on exact timing.

### 6.3 Data flow per tick

```
_run_loop ──► GBMSimulator.step() ──► {ticker: price}
                                         │
                       PriceCache.update(ticker, price)   (computes previous_price, change,
                                         │                  direction; bumps version)
                                         ▼
                 SSE generator sees version change (≤500 ms later) ──► data: {...}
```

---

## 7. Tuning knobs

| Knob | Where | Default | Effect |
|---|---|---|---|
| `update_interval` | `SimulatorDataSource(...)` | 0.5 s | Tick rate; also how often the UI flashes |
| `event_probability` | `SimulatorDataSource(...)` / `GBMSimulator(...)` | 0.001 | Shock frequency (see §4) |
| `dt` | `GBMSimulator(...)` | 0.5 s of trading year | Time compression: larger `dt` means faster-moving prices |
| `sigma`, `mu` per ticker | `TICKER_PARAMS` | see §5 | Per-stock volatility and drift |
| Correlations | `*_CORR`, `CORRELATION_GROUPS` | 0.6 / 0.5 / 0.3 | Co-movement; keep the §3 PD constraint |

If you change `update_interval`, change `dt` to match (`dt = update_interval / TRADING_SECONDS_PER_YEAR`).
Otherwise volatility per wall-clock second changes too.

---

## 8. Required and recommended changes

| # | Change | Why | Priority |
|---|---|---|---|
| T0.1 | Normalize with `strip().upper()` (via `normalize_ticker`) in `SimulatorDataSource.start`, `add_ticker`, `remove_ticker`, and de-duplicate in `start` | PLAN §6 defence in depth: `"aapl"` must not create a second simulated AAPL | **Required (M0)** |
| S1 | Optional `seed: int \| None` constructor argument, using `np.random.default_rng(seed)` and `random.Random(seed)` instead of the global RNGs | Deterministic unit tests and reproducible E2E screenshots | Recommended |
| S2 | Log-symmetric shocks (`price *= exp(shock)`) and/or `event_probability=1e-4` | Remove the downward bias and event-dominated volatility (§4) | Optional; product decision |
| S3 | On startup, seed tickers that have an open position from the most recent trade price (`trades` table) instead of `SEED_PRICES` | The simulator restarts at seed prices on every container restart, so a user who bought AAPL at $230 after drift sees an instant P&L jump when AAPL resets to $190 | Optional |

---

## 9. Testing approach

Existing coverage lives in `tests/market/test_simulator.py` (engine) and
`test_simulator_source.py` (adapter). Keep these properties tested:

- **Engine:** prices stay positive over 10,000 steps. `step()` returns exactly the tracked
  tickers. Known tickers start at `SEED_PRICES`, and unknown tickers start in [50, 300].
  Add/remove are idempotent and keep the matrix size in sync. Cholesky succeeds for the
  default set plus arbitrary unknown tickers. With `event_probability=0`, the sample
  standard deviation of log returns is ≈ `σ·√dt` (statistical, loose tolerance). With
  `event_probability=1`, every step moves each price by at least ~2 %. With high-ρ
  constants, tech tickers' returns show positive sample correlation.
- **Adapter:** `start` seeds the cache before returning. The cache updates within a few
  intervals (use `update_interval=0.01` in tests). `add_ticker` puts a price in the cache
  immediately. `remove_ticker` clears it from the cache. `stop` is idempotent, and no
  writes happen after it. **T0.1:** `add_ticker(" pypl ")` tracks `"PYPL"`, and
  `remove_ticker("aapl")` removes `"AAPL"`.
- Once S1 lands, prefer seeded RNGs over statistical tolerances where possible.
