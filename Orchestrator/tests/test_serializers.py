"""
Test - Serialization Utilities

Funzioni pure: serialize(), serialize_row().
Nessun mock necessario.
"""

from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from app.utils.serializers import serialize, serialize_row


class TestSerialize:
    """Testa serialize(obj) — conversione tipi PostgreSQL → JSON."""

    # --- datetime ---

    def test_datetime_naive_returns_iso_string(self):
        dt = datetime(2026, 3, 11, 10, 30, 0)
        result = serialize(dt)
        assert isinstance(result, str)
        assert result == "2026-03-11T10:30:00"

    def test_datetime_utc_aware_returns_iso_string(self):
        dt = datetime(2026, 3, 11, 10, 30, 0, tzinfo=timezone.utc)
        result = serialize(dt)
        assert isinstance(result, str)
        assert "2026-03-11" in result

    def test_datetime_other_tz_returns_iso_string(self):
        tz_plus2 = timezone(timedelta(hours=2))
        dt = datetime(2026, 3, 11, 12, 30, 0, tzinfo=tz_plus2)
        result = serialize(dt)
        assert isinstance(result, str)
        assert "2026-03-11" in result

    # --- date ---

    def test_date_returns_iso_string(self):
        d = date(2026, 3, 11)
        result = serialize(d)
        assert result == "2026-03-11"

    def test_date_is_not_confused_with_datetime(self):
        d = date(2000, 1, 1)
        result = serialize(d)
        assert result == "2000-01-01"
        assert "T" not in result  # date → no time component

    # --- Decimal ---

    def test_decimal_returns_float(self):
        assert serialize(Decimal("3.14")) == pytest.approx(3.14)

    def test_decimal_zero_returns_zero_float(self):
        assert serialize(Decimal("0")) == 0.0
        assert isinstance(serialize(Decimal("0")), float)

    def test_decimal_integer_value_returns_float(self):
        assert serialize(Decimal("100")) == 100.0
        assert isinstance(serialize(Decimal("100")), float)

    # --- Passthrough ---

    def test_int_passthrough(self):
        assert serialize(42) == 42

    def test_str_passthrough(self):
        assert serialize("hello") == "hello"

    def test_none_passthrough(self):
        assert serialize(None) is None

    def test_bool_passthrough(self):
        assert serialize(True) is True
        assert serialize(False) is False

    def test_list_passthrough(self):
        lst = [1, 2, 3]
        assert serialize(lst) is lst  # stesso oggetto

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert serialize(d) is d


class TestSerializeRow:
    """Testa serialize_row(row) — serializza tutti i valori di un dict."""

    def test_empty_dict_returns_empty_dict(self):
        assert serialize_row({}) == {}

    def test_preserves_keys(self):
        row = {"id": 1, "name": "test"}
        result = serialize_row(row)
        assert set(result.keys()) == {"id", "name"}

    def test_converts_datetime_values(self):
        dt = datetime(2026, 3, 11, 10, 0, 0)
        row = {"created_at": dt, "id": 5}
        result = serialize_row(row)
        assert isinstance(result["created_at"], str)
        assert result["id"] == 5

    def test_converts_decimal_values(self):
        row = {"score": Decimal("87.5"), "name": "test"}
        result = serialize_row(row)
        assert isinstance(result["score"], float)
        assert result["score"] == pytest.approx(87.5)

    def test_preserves_none_values(self):
        row = {"field": None, "other": "value"}
        result = serialize_row(row)
        assert result["field"] is None

    def test_mixed_types(self):
        row = {
            "id": 1,
            "name": "USN-7412-2",
            "severity": "Critical",
            "score": Decimal("90"),
            "issued_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "packages": None,
        }
        result = serialize_row(row)
        assert result["id"] == 1
        assert result["name"] == "USN-7412-2"
        assert result["severity"] == "Critical"
        assert isinstance(result["score"], float)
        assert isinstance(result["issued_at"], str)
        assert result["packages"] is None

    def test_all_string_values_unchanged(self):
        row = {"a": "foo", "b": "bar", "c": "baz"}
        result = serialize_row(row)
        assert result == {"a": "foo", "b": "bar", "c": "baz"}

    def test_nested_dict_not_recursed(self):
        """serialize_row NON è ricorsiva: valori dict/list rimangono intatti."""
        inner = {"ts": datetime(2026, 1, 1)}
        row = {"data": inner}
        result = serialize_row(row)
        # Il valore interno non viene serializzato (limitazione nota)
        assert result["data"] is inner


import pytest  # noqa: E402 — importato dopo per usare pytest.approx
