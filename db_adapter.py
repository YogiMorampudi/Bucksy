"""
Database adapter for Bucksy.
Supports SQLite (local dev) and PostgreSQL (Vercel + Supabase production).

Usage:
    from db_adapter import db, init_db, USE_POSTGRES

The `db()` function returns a context-manager connection that behaves
identically for both backends.  All SQL in app.py uses `?` placeholders
(SQLite style).  When USE_POSTGRES is True, the adapter transparently
rewrites `?` → `%s` so existing queries work unmodified.
"""

import os
import re
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# ── Backend Selection ─────────────────────────────────────────────────────────
# Set DATABASE_URL to a PostgreSQL connection string to use Postgres.
# Example: postgresql://user:pass@host:5432/dbname
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")

# ── SQLite Fallback ───────────────────────────────────────────────────────────
import shutil

# On serverless (Vercel/AWS Lambda), the code directory is strictly read-only.
# /tmp is the only writable filesystem directory.
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = Path("/tmp/bucksy.db")
    _src_db = Path(__file__).parent / "bucksy.db"
    if _src_db.exists() and not DB_PATH.exists():
        try:
            shutil.copyfile(_src_db, DB_PATH)
        except Exception:
            pass
else:
    DB_PATH = Path(__file__).parent / "bucksy.db"

# ── Placeholder Rewriter ─────────────────────────────────────────────────────
# Converts SQLite's `?` placeholders to PostgreSQL's `%s`.
# Skips `?` inside string literals (single-quoted).
_Q_RE = re.compile(r"'[^']*'|(\?)")

def _rewrite_placeholders(sql):
    """Replace ? with %s for PostgreSQL, ignoring ? inside string literals."""
    def _replacer(m):
        if m.group(1):
            return "%s"
        return m.group(0)
    return _Q_RE.sub(_replacer, sql)


# ══════════════════════════════════════════════════════════════════════════════
# PostgreSQL Wrapper
# ══════════════════════════════════════════════════════════════════════════════
class _PgRow(dict):
    """Dict subclass that also supports attribute-style access, like sqlite3.Row."""
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def keys(self):
        return list(super().keys())


class _PgCursorWrapper:
    """Wraps a psycopg2 cursor so that .execute() auto-rewrites `?` → `%s`
    and results are returned as _PgRow dicts (like sqlite3.Row)."""

    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, sql, params=None):
        sql = _rewrite_placeholders(sql)
        self._cur.execute(sql, params or ())
        return self

    def executescript(self, sql):
        """Run multiple statements. psycopg2 can handle `;`-separated SQL."""
        sql = _rewrite_placeholders(sql)
        self._cur.execute(sql)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [desc[0] for desc in self._cur.description]
        return _PgRow(zip(cols, row))

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        cols = [desc[0] for desc in self._cur.description]
        return [_PgRow(zip(cols, r)) for r in rows]

    @property
    def lastrowid(self):
        return self._cur.fetchone()[0] if self._cur.description else None

    @property
    def rowcount(self):
        return self._cur.rowcount


class _PgConnectionWrapper:
    """Wraps a psycopg2 connection to expose execute/executescript methods
    with automatic placeholder rewriting and dict-row results."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        cur = self._conn.cursor()
        wrapper = _PgCursorWrapper(cur)
        wrapper.execute(sql, params)
        return wrapper

    def executescript(self, sql):
        cur = self._conn.cursor()
        wrapper = _PgCursorWrapper(cur)
        wrapper.executescript(sql)
        return wrapper

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        # Don't close — let the caller manage lifecycle
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def db():
    """Return a database connection (SQLite or PostgreSQL)."""
    if USE_POSTGRES:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        return _PgConnectionWrapper(conn)
    else:
        conn = sqlite3.connect(str(DB_PATH), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


# ── Schema Initialisation ─────────────────────────────────────────────────────

_SQLITE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL COLLATE NOCASE,
    ip_address TEXT,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    amount REAL NOT NULL CHECK(amount > 0),
    method TEXT NOT NULL DEFAULT 'Cash',
    txn_date TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS khata_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    person_id INTEGER NOT NULL,
    direction TEXT NOT NULL CHECK(direction IN ('given','received','borrowed','repaid')),
    amount REAL NOT NULL CHECK(amount > 0),
    entry_date TEXT NOT NULL,
    note TEXT DEFAULT '',
    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    goal_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    product_model TEXT DEFAULT '',
    price REAL NOT NULL CHECK(price > 0),
    extra_costs REAL NOT NULL DEFAULT 0 CHECK(extra_costs >= 0),
    current_savings REAL NOT NULL DEFAULT 0 CHECK(current_savings >= 0),
    saving_amount REAL NOT NULL CHECK(saving_amount > 0),
    saving_frequency TEXT NOT NULL DEFAULT 'daily' CHECK(saving_frequency IN ('daily','weekly','monthly')),
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK(priority IN ('High','Medium','Low')),
    product_source TEXT DEFAULT '',
    price_checked_at TEXT DEFAULT '',
    target_date TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','achieved','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_POSTGRES_SCHEMA = """\
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    used_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    ip_address TEXT,
    attempted_at TEXT NOT NULL,
    success INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    amount REAL NOT NULL CHECK(amount > 0),
    method TEXT NOT NULL DEFAULT 'Cash',
    txn_date TEXT NOT NULL,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS people (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS khata_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK(direction IN ('given','received','borrowed','repaid')),
    amount REAL NOT NULL CHECK(amount > 0),
    entry_date TEXT NOT NULL,
    note TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS goals (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    goal_name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    product_model TEXT DEFAULT '',
    price REAL NOT NULL CHECK(price > 0),
    extra_costs REAL NOT NULL DEFAULT 0 CHECK(extra_costs >= 0),
    current_savings REAL NOT NULL DEFAULT 0 CHECK(current_savings >= 0),
    saving_amount REAL NOT NULL CHECK(saving_amount > 0),
    saving_frequency TEXT NOT NULL DEFAULT 'daily' CHECK(saving_frequency IN ('daily','weekly','monthly')),
    priority TEXT NOT NULL DEFAULT 'Medium' CHECK(priority IN ('High','Medium','Low')),
    product_source TEXT DEFAULT '',
    price_checked_at TEXT DEFAULT '',
    target_date TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','achieved','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
    "CREATE INDEX IF NOT EXISTS idx_reset_token_hash ON password_reset_tokens(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_login_attempts_filter ON login_attempts(email, attempted_at)",
    "CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_people_user ON people(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_khata_user ON khata_entries(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id)",
]


def _pg_column_exists(conn, table, column):
    """Check if a column exists in a PostgreSQL table."""
    cur = conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
        (table, column)
    )
    return cur.fetchone() is not None


def _sqlite_column_exists(conn, table, column):
    """Check if a column exists in a SQLite table."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def init_db():
    """Create all tables, run migrations, and create indexes."""
    with db() as conn:
        if USE_POSTGRES:
            conn.executescript(_POSTGRES_SCHEMA)

            # Migration: add user_id if missing
            for table in ("transactions", "people", "khata_entries", "goals"):
                if not _pg_column_exists(conn, table, "user_id"):
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                    )
        else:
            conn.executescript(_SQLITE_SCHEMA)

            # Migration: add user_id if missing
            for table in ("transactions", "people", "khata_entries", "goals"):
                if not _sqlite_column_exists(conn, table, "user_id"):
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN user_id INTEGER REFERENCES users(id)"
                    )

        # Create indexes (syntax is the same for both backends)
        for idx_sql in _INDEXES:
            conn.execute(idx_sql)
