"""SQLite database management, initialization, and persistence helpers."""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .schema import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_USER_ID,
    DEFAULT_WATCHLIST,
    SCHEMA_SQL,
)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format with Z suffix."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_db_path(explicit_path: str | Path | None = None) -> Path:
    """Resolve the SQLite database path from explicit arg, DB_PATH env var, or default.

    Default is:
    - <repo_root>/db/finally.db when running locally from backend/app/db/
    - /app/db/finally.db when running inside the Docker image (/app/app/db/)
    """
    if explicit_path is not None:
        return Path(explicit_path)

    env_path = os.environ.get("DB_PATH", "").strip()
    if env_path:
        return Path(env_path)

    # backend/app/db/database.py -> parents[2] is backend (local) or /app (Docker)
    package_root = Path(__file__).resolve().parents[2]
    if package_root.name == "backend":
        return package_root.parent / "db" / "finally.db"
    return package_root / "db" / "finally.db"


class Database:
    """Thin, synchronous SQLite wrapper with transaction support."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_db_path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager that commits on success and rolls back on error."""
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        """Create parent directory, tables, and seed default data if fresh."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute(
                "SELECT id FROM users_profile WHERE id = ?",
                (DEFAULT_USER_ID,),
            ).fetchone()
            if row is None:
                now = utc_now_iso()
                conn.execute(
                    "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                    (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
                )
                for ticker in DEFAULT_WATCHLIST:
                    conn.execute(
                        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                        (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now),
                    )
                conn.execute(
                    "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, now),
                )

    def get_tracked_tickers(self, user_id: str = DEFAULT_USER_ID) -> list[str]:
        """Return sorted union of watchlist and open position tickers."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT ticker FROM watchlist WHERE user_id = ?
                UNION
                SELECT ticker FROM positions WHERE user_id = ?
                ORDER BY ticker ASC
                """,
                (user_id, user_id),
            ).fetchall()
            return [row["ticker"] for row in rows]

    def get_cash_balance(self, user_id: str = DEFAULT_USER_ID) -> float:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?",
                (user_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"User profile '{user_id}' not initialized")
            return float(row["cash_balance"])

    def get_positions(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, quantity, avg_cost, updated_at
                FROM positions
                WHERE user_id = ?
                ORDER BY ticker ASC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def has_position(self, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM positions WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
            return row is not None

    def get_watchlist(self, user_id: str = DEFAULT_USER_ID) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, ticker, added_at
                FROM watchlist
                WHERE user_id = ?
                ORDER BY added_at ASC, rowid ASC
                """,
                (user_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def is_in_watchlist(self, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            ).fetchone()
            return row is not None

    def add_to_watchlist(self, ticker: str, user_id: str = DEFAULT_USER_ID) -> dict | None:
        """Insert ticker into watchlist. Returns the row dict, or None if already present."""
        now = utc_now_iso()
        row_id = str(uuid.uuid4())
        with self.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (row_id, user_id, ticker, now),
                )
            except sqlite3.IntegrityError:
                return None
        return {"id": row_id, "user_id": user_id, "ticker": ticker, "added_at": now}

    def remove_from_watchlist(self, ticker: str, user_id: str = DEFAULT_USER_ID) -> bool:
        """Delete ticker from watchlist. Returns True if a row was deleted."""
        with self.connection() as conn:
            cur = conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                (user_id, ticker),
            )
            return cur.rowcount > 0

    def record_portfolio_snapshot(
        self, total_value: float, user_id: str = DEFAULT_USER_ID
    ) -> dict:
        now = utc_now_iso()
        row_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)
                VALUES (?, ?, ?, ?)
                """,
                (row_id, user_id, round(total_value, 2), now),
            )
        return {"id": row_id, "total_value": round(total_value, 2), "recorded_at": now}

    def get_portfolio_history(
        self, limit: int = 500, user_id: str = DEFAULT_USER_ID
    ) -> list[dict]:
        """Return up to the most recent `limit` snapshots ordered by recorded_at ASC."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT total_value, recorded_at
                FROM (
                    SELECT total_value, recorded_at, rowid
                    FROM portfolio_snapshots
                    WHERE user_id = ?
                    ORDER BY recorded_at DESC, rowid DESC
                    LIMIT ?
                )
                ORDER BY recorded_at ASC, rowid ASC
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_chat_message(
        self,
        role: str,
        content: str,
        actions_json: str | None = None,
        user_id: str = DEFAULT_USER_ID,
    ) -> dict:
        now = utc_now_iso()
        row_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row_id, user_id, role, content, actions_json, now),
            )
        return {
            "id": row_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "actions": actions_json,
            "created_at": now,
        }

    def get_chat_messages(
        self, limit: int = 50, user_id: str = DEFAULT_USER_ID
    ) -> list[dict]:
        """Return up to the most recent `limit` chat messages ordered by created_at ASC."""
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, actions, created_at
                FROM (
                    SELECT id, role, content, actions, created_at, rowid
                    FROM chat_messages
                    WHERE user_id = ?
                    ORDER BY created_at DESC, rowid DESC
                    LIMIT ?
                )
                ORDER BY created_at ASC, rowid ASC
                """,
                (user_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]
