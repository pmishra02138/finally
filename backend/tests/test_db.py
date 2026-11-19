"""Unit tests for SQLite database initialization, seeding, and queries."""

from __future__ import annotations

from pathlib import Path

from app.db import DEFAULT_CASH_BALANCE, DEFAULT_WATCHLIST, Database, resolve_db_path


def test_init_creates_parent_dir_and_seeds_defaults(tmp_path: Path) -> None:
    db_file = tmp_path / "nested" / "dir" / "finally.db"
    db = Database(db_path=db_file)
    db.init()

    assert db_file.exists()
    assert db.get_cash_balance() == DEFAULT_CASH_BALANCE
    watchlist = [row["ticker"] for row in db.get_watchlist()]
    assert watchlist == list(DEFAULT_WATCHLIST)
    history = db.get_portfolio_history()
    assert len(history) == 1
    assert history[0]["total_value"] == DEFAULT_CASH_BALANCE


def test_init_is_idempotent_across_restarts(tmp_path: Path) -> None:
    db_file = tmp_path / "finally.db"
    db = Database(db_path=db_file)
    db.init()

    # Mutate state
    db.remove_from_watchlist("NFLX")
    db.add_to_watchlist("PYPL")
    with db.connection() as conn:
        conn.execute("UPDATE users_profile SET cash_balance = 7500.0 WHERE id = 'default'")
    db.record_portfolio_snapshot(9800.0)

    # Simulate restart
    db2 = Database(db_path=db_file)
    db2.init()

    assert db2.get_cash_balance() == 7500.0
    tickers = [row["ticker"] for row in db2.get_watchlist()]
    assert "NFLX" not in tickers
    assert "PYPL" in tickers
    assert len(db2.get_portfolio_history()) == 2


def test_tracked_tickers_union_of_watchlist_and_positions(tmp_path: Path) -> None:
    db = Database(db_path=tmp_path / "finally.db")
    db.init()
    db.remove_from_watchlist("AAPL")

    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
            VALUES ('p1', 'default', 'IBM', 5.0, 150.0, '2026-01-01T00:00:00Z')
            """
        )

    tracked = db.get_tracked_tickers()
    assert "IBM" in tracked
    assert "AAPL" not in tracked


def test_history_and_chat_limits_return_most_recent_ascending(tmp_path: Path) -> None:
    db = Database(db_path=tmp_path / "finally.db")
    db.init()

    for i in range(1, 15):
        db.record_portfolio_snapshot(10000.0 + i)
    recent_snaps = db.get_portfolio_history(limit=5)
    assert len(recent_snaps) == 5
    assert [s["total_value"] for s in recent_snaps] == [10010.0, 10011.0, 10012.0, 10013.0, 10014.0]

    for i in range(1, 12):
        db.add_chat_message(role="user", content=f"msg-{i}")
    recent_msgs = db.get_chat_messages(limit=4)
    assert [m["content"] for m in recent_msgs] == ["msg-8", "msg-9", "msg-10", "msg-11"]


def test_resolve_db_path_env_override(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom.db"
    monkeypatch.setenv("DB_PATH", str(custom))
    assert resolve_db_path() == custom


def test_resolve_db_path_default_local(monkeypatch) -> None:
    monkeypatch.delenv("DB_PATH", raising=False)
    default_path = resolve_db_path()
    assert default_path.name == "finally.db"
    assert default_path.parent.name == "db"
