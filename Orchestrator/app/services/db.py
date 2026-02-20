"""
SPM Orchestrator - Database Connection

Gestisce connessioni a PostgreSQL locale.
Usa un semplice pool di connessioni con psycopg2.
"""

import logging
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
from typing import Optional

from app.config import Config

logger = logging.getLogger(__name__)

# Pool globale (inizializzato in init_db)
_pool: Optional[ThreadedConnectionPool] = None


def init_db() -> bool:
    """
    Inizializza pool connessioni PostgreSQL.
    Chiamato all'avvio dell'applicazione.
    Ritorna True se OK, False se errore.
    """
    global _pool

    try:
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=Config.db_dsn(),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )

        # Verifica connessione
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version()")
            version = cursor.fetchone()
            logger.info(f"Database connected: {version['version'][:50]}")

        return True

    except psycopg2.OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        _pool = None
        return False


def close_db():
    """Chiude pool connessioni (chiamato allo shutdown)"""
    global _pool
    if _pool:
        _pool.closeall()
        _pool = None
        logger.info("Database pool closed")


@contextmanager
def get_db():
    """
    Context manager per ottenere una connessione dal pool.

    Uso:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ...")
    """
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def check_db_health() -> dict:
    """
    Verifica stato database per health endpoint.
    Ritorna dict con status e dettagli.
    """
    if _pool is None:
        return {"status": "error", "message": "Pool not initialized"}

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total FROM orchestrator_config")
            result = cursor.fetchone()

        return {
            "status": "connected",
            "config_entries": result["total"] if result else 0,
        }

    except psycopg2.OperationalError as e:
        return {"status": "error", "message": str(e)}

    except psycopg2.ProgrammingError:
        # Schema non ancora applicato
        return {
            "status": "connected",
            "message": "Schema not applied yet - run migrations",
        }
