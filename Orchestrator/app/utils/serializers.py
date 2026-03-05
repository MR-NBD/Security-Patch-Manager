"""
SPM Orchestrator - Serialization Utilities

Funzioni condivise per serializzare tipi PostgreSQL in JSON.
Usato da: approval_manager, queue_manager, api/tests.
"""

from datetime import datetime, date
from decimal import Decimal


def serialize(obj):
    """Converte tipi PostgreSQL non-JSON-serializable."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


def serialize_row(row: dict) -> dict:
    """Serializza tutti i valori di un RealDictRow PostgreSQL."""
    return {k: serialize(v) for k, v in row.items()}
