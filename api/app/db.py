from contextlib import contextmanager

from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_settings().database_url, min_size=1, max_size=5)
    return _pool


@contextmanager
def cursor():
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            yield cur


def ping() -> bool:
    with cursor() as cur:
        cur.execute("SELECT 1")
        return cur.fetchone() is not None


def vector_extension_ready() -> bool:
    with cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        return cur.fetchone() is not None
