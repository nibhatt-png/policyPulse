"""Shared Postgres connection pool for the API.

Opening a new connection to Supabase costs ~0.6s per request; reusing pooled
connections removes that. FastAPI runs sync endpoints in a thread pool, so the
pool must be thread-safe.
"""
import os, threading, time
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

# TCP keepalives make the OS notice (and report) a connection the network or
# Supabase dropped while it sat idle in the pool, instead of it hanging.
KEEPALIVES = dict(keepalives=1, keepalives_idle=60, keepalives_interval=10, keepalives_count=3)

class ConfigError(Exception):
    """A required setting (environment variable) is missing."""

def _get_pool() -> ThreadedConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            url = os.getenv("DATABASE_URL")
            if not url:   # psycopg2 would otherwise quietly try a local database
                raise ConfigError("DATABASE_URL isn't set")
            _pool = ThreadedConnectionPool(MIN_CONN, MAX_CONN, url, **KEEPALIVES)
        return _pool

def _is_connection_error(e: Exception) -> bool:
    return isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError, psycopg2.DatabaseError))

def run(fn: Callable[[psycopg2.extensions.cursor], T]) -> T:
    """Run fn(cursor) on a pooled connection in one transaction and return its result.

    Pooled connections go stale when Supabase or the network drops them while
    idle, and after a network blip usually ALL of them have. A dead connection
    is discarded and fn retried on the next one, up to the pool size plus one,
    so the last attempt always gets a freshly opened connection. (Retrying only
    once used to leave the API failing on every request until restarted.)
    An error on a connection that's still open (e.g. a statement timeout) is
    retried once. fn should only do reads or idempotent work.
    """
    pool = _get_pool()
    attempts = MAX_CONN + 1
    open_conn_retried = False
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            conn = pool.getconn()  # may open a new connection, which can also fail
        except psycopg2.OperationalError:
            if attempt >= 1:
                raise              # can't open a new connection: really unreachable
            time.sleep(1)
            continue
        try:
            with conn.cursor() as cur:
                result = fn(cur)
            conn.commit()
            pool.putconn(conn)
            return result
        except Exception as e:
            dead = bool(conn.closed)
            if not dead:
                try:
                    conn.rollback()
                except psycopg2.Error:
                    dead = True
            pool.putconn(conn, close=dead)
            if not _is_connection_error(e) or last:
                raise
            if dead:
                continue           # try the next pooled connection, or a new one
            if open_conn_retried or not isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
                raise
            open_conn_retried = True
    raise RuntimeError("unreachable")
