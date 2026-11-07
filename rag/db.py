"""Shared Postgres connection pool for the API.

Opening a new connection to Supabase costs ~0.6s per request; reusing pooled
connections removes that. FastAPI runs sync endpoints in a thread pool, so the
pool must be thread-safe.
"""
import os, threading
from typing import Callable, TypeVar
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from dotenv import load_dotenv
load_dotenv()

MIN_CONN = 1
MAX_CONN = 5

T = TypeVar("T")

_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()

def _get_pool() -> ThreadedConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadedConnectionPool(MIN_CONN, MAX_CONN, os.getenv("DATABASE_URL"))
        return _pool

def run(fn: Callable[[psycopg2.extensions.cursor], T]) -> T:
    """Run fn(cursor) on a pooled connection in one transaction and return its result.

    A pooled connection can go stale (Supabase or the network drops it while
    idle). When that happens the connection is discarded and fn is retried once
    on a fresh one, so fn should only do reads or idempotent work.
    """
    pool = _get_pool()
    for attempt in range(2):
        try:
            conn = pool.getconn()  # may open a new connection, which can also fail
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            if attempt == 1:
                raise
            continue
        try:
            with conn.cursor() as cur:
                result = fn(cur)
            conn.commit()
            pool.putconn(conn)
            return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            pool.putconn(conn, close=True)
            if attempt == 1:
                raise
        except Exception:
            if not conn.closed:
                conn.rollback()
            pool.putconn(conn, close=bool(conn.closed))
            raise
    raise RuntimeError("unreachable")
