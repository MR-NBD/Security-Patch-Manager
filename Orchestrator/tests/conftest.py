"""
Fixture condivise per tutti i test SPM Orchestrator.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.main import create_app


# ──────────────────────────────────────────────────────────────
# Flask test client
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    """
    Flask test client con DB non inizializzato (patch init_db).
    Usato da tutti i test di API endpoint.
    """
    with patch("app.main.init_db", return_value=True):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ──────────────────────────────────────────────────────────────
# DB mock helpers
# ──────────────────────────────────────────────────────────────

def make_mock_cursor(fetchone_result=None, fetchall_result=None, rowcount=0):
    """
    Crea un cursore mock compatibile con RealDictCursor.
    fetchone_result e fetchall_result devono essere dict o list[dict].
    """
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.rowcount = rowcount
    return cursor


def make_mock_db(cursor=None):
    """
    Crea un context manager mock per get_db().
    Uso: patch("app.services.foo.get_db", return_value=make_mock_db(cursor))
    """
    if cursor is None:
        cursor = make_mock_cursor()
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn
