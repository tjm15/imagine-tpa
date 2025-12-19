from __future__ import annotations

import os
import logging
from typing import Any

from fastapi import HTTPException
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_db_pool: ConnectionPool | None = None
_logger = logging.getLogger(__name__)


def init_db_pool() -> None:
    """
    Initialise the global DB pool from `TPA_DB_DSN`.

    The API is allowed to start without a DB (scaffold mode), but DB-backed endpoints will return 503.
    """
    global _db_pool
    if _db_pool is not None:
        return

    dsn = os.environ.get("TPA_DB_DSN")
    if not dsn:
        return

    max_size = int(os.environ.get("TPA_DB_POOL_MAX", "6"))
    max_size = max(1, min(max_size, 32))
    pool = ConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=max_size,
        open=False,
        kwargs={"autocommit": True},
    )
    try:
        pool.open()
    except Exception:
        # Degraded mode is preferable to crashing the whole API and causing UI-level 502s.
        # DB-backed endpoints will return 503 until the DB is reachable and the API restarts.
        _logger.exception("Failed to initialise DB pool; running in degraded mode.")
        try:
            pool.close()
        except Exception:
            _logger.debug("Failed to close DB pool after init failure.", exc_info=True)
        _db_pool = None
        return

    _db_pool = pool


def shutdown_db_pool() -> None:
    global _db_pool
    if _db_pool is None:
        return
    _db_pool.close()
    _db_pool = None


def _db_pool_or_503() -> ConnectionPool:
    if _db_pool is None:
        # Best-effort lazy initialisation (e.g., DB starts after API, or API is reused in tests).
        init_db_pool()
    if _db_pool is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not ready (check Postgres and TPA_DB_DSN).",
        )
    return _db_pool


def _db_fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    pool = _db_pool_or_503()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()  # Ensure transaction is closed so connection is returned clean
            return dict(row) if row else None


def _db_fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    pool = _db_pool_or_503()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            conn.commit()  # Ensure transaction is closed so connection is returned clean
            return [dict(r) for r in rows]


def _db_execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    pool = _db_pool_or_503()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def _db_execute_returning(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    pool = _db_pool_or_503()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="DB did not return a row for RETURNING statement")
            conn.commit()
            return dict(row)


def db_ping() -> bool:
    """
    Best-effort DB connectivity check.

    Returns `True` when the DB is reachable and can execute a trivial query.
    """
    try:
        pool = _db_pool_or_503()
    except HTTPException:
        return False

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
        return True
    except Exception:
        _logger.debug("DB ping failed.", exc_info=True)
        return False
