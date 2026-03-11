"""
Test - Poller (funzioni pure)

_parse_uyuni_date() e _build_cache_row() non toccano DB né UYUNI.
Nessun mock necessario.
"""

import xmlrpc.client
from datetime import datetime, timezone, timedelta

from app.services.poller import _parse_uyuni_date, _build_cache_row


class TestParseUyuniDate:
    """Testa _parse_uyuni_date() — conversione formati data UYUNI → ISO 8601 UTC."""

    # --- Valori falsy ---

    def test_none_returns_none(self):
        assert _parse_uyuni_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_uyuni_date("") is None

    def test_zero_returns_none(self):
        assert _parse_uyuni_date(0) is None

    # --- datetime nativo ---

    def test_naive_datetime_adds_utc(self):
        dt = datetime(2026, 3, 11, 10, 30, 0)
        result = _parse_uyuni_date(dt)
        assert result is not None
        assert "2026-03-11" in result
        assert "+00:00" in result or "Z" in result or result.endswith("00:00")

    def test_utc_aware_datetime_returns_isoformat(self):
        dt = datetime(2026, 3, 11, 10, 30, 0, tzinfo=timezone.utc)
        result = _parse_uyuni_date(dt)
        assert result is not None
        assert "2026-03-11" in result

    def test_non_utc_aware_datetime_converts_to_utc(self):
        tz_plus2 = timezone(timedelta(hours=2))
        dt = datetime(2026, 3, 11, 12, 0, 0, tzinfo=tz_plus2)
        result = _parse_uyuni_date(dt)
        assert result is not None
        # 12:00 +02:00 → 10:00 UTC
        assert "10:00" in result

    # --- Stringhe ISO ---

    def test_iso_string_without_timezone(self):
        result = _parse_uyuni_date("2024-01-15T10:30:00")
        assert result is not None
        assert "2024-01-15" in result

    def test_iso_string_with_z(self):
        result = _parse_uyuni_date("2024-01-15T10:30:00Z")
        assert result is not None
        assert "2024-01-15" in result

    def test_iso_string_with_utc_offset(self):
        result = _parse_uyuni_date("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert "2024-01-15" in result

    def test_malformed_string_returns_none(self):
        assert _parse_uyuni_date("not-a-date") is None

    def test_partial_date_string_returns_none(self):
        assert _parse_uyuni_date("2024-13-45") is None  # mese/giorno invalido

    # --- xmlrpc.client.DateTime ---

    def test_xmlrpc_datetime_object(self):
        """xmlrpc.client.DateTime ha .timetuple() ma non è datetime."""
        xdt = xmlrpc.client.DateTime("20260311T10:30:00")
        result = _parse_uyuni_date(xdt)
        assert result is not None
        assert isinstance(result, str)

    def test_xmlrpc_datetime_is_not_instance_of_datetime(self):
        """Verifica che il codice non confonda xmlrpc.DateTime con datetime."""
        xdt = xmlrpc.client.DateTime("20240101T00:00:00")
        assert not isinstance(xdt, datetime)
        assert hasattr(xdt, "timetuple")
        # La funzione deve gestirlo correttamente
        result = _parse_uyuni_date(xdt)
        assert result is not None


class TestBuildCacheRow:
    """Testa _build_cache_row() — costruzione riga errata_cache dai dati UYUNI."""

    def _base_errata(self):
        return {
            "advisory_type": "Security Advisory",
            "advisory_synopsis": "Critical update for openssl",
            "date": "2026-03-11T10:00:00Z",
        }

    # --- Struttura output ---

    def test_returns_all_required_fields(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        required = {
            "errata_id", "synopsis", "description", "severity",
            "type", "issued_date", "target_os", "packages", "cves", "source_url",
        }
        assert required.issubset(row.keys())

    def test_errata_id_is_advisory_name(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["errata_id"] == "USN-7412-2"

    def test_description_is_always_empty(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["description"] == ""

    def test_packages_is_always_empty_list(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["packages"] == []

    def test_source_url_is_none(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["source_url"] is None

    def test_target_os_propagated(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["target_os"] == "ubuntu"

    def test_type_is_advisory_type(self):
        row = _build_cache_row("USN-7412-2", self._base_errata(), [], "ubuntu")
        assert row["type"] == "Security Advisory"

    # --- Synopsis ---

    def test_uses_advisory_synopsis_when_present(self):
        base = {"advisory_type": "Security Advisory",
                "advisory_synopsis": "Critical SSL fix", "synopsis": "Old value"}
        row = _build_cache_row("X", base, [], "ubuntu")
        assert row["synopsis"] == "Critical SSL fix"

    def test_fallback_to_synopsis_when_no_advisory_synopsis(self):
        base = {"advisory_type": "Security Advisory", "synopsis": "Fallback synopsis"}
        row = _build_cache_row("X", base, [], "ubuntu")
        assert row["synopsis"] == "Fallback synopsis"

    def test_empty_synopsis_when_neither_present(self):
        base = {"advisory_type": "Security Advisory"}
        row = _build_cache_row("X", base, [], "ubuntu")
        assert row["synopsis"] == ""

    # --- Severity ---

    def test_uyuni_severity_overrides_advisory_type(self):
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu",
                               uyuni_severity="Critical")
        assert row["severity"] == "Critical"

    def test_high_severity_from_uyuni(self):
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu",
                               uyuni_severity="High")
        assert row["severity"] == "High"

    def test_fallback_to_medium_for_security_advisory(self):
        """Senza uyuni_severity, Security Advisory → Medium."""
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu",
                               uyuni_severity=None)
        assert row["severity"] == "Medium"

    def test_fallback_to_low_for_bug_fix(self):
        base = {"advisory_type": "Bug Fix Advisory", "advisory_synopsis": "Fix"}
        row = _build_cache_row("X", base, [], "rhel", uyuni_severity=None)
        assert row["severity"] == "Low"

    def test_empty_uyuni_severity_uses_fallback(self):
        """Stringa vuota è falsy → usa fallback advisory_type."""
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu",
                               uyuni_severity="")
        assert row["severity"] == "Medium"

    # --- CVEs ---

    def test_cves_propagated(self):
        cves = ["CVE-2024-1234", "CVE-2024-5678"]
        row = _build_cache_row("X", self._base_errata(), cves, "ubuntu")
        assert row["cves"] == cves

    def test_empty_cves(self):
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu")
        assert row["cves"] == []

    # --- issued_date ---

    def test_issued_date_parsed_from_base(self):
        row = _build_cache_row("X", self._base_errata(), [], "ubuntu")
        assert row["issued_date"] is not None
        assert "2026-03-11" in row["issued_date"]

    def test_issued_date_none_when_missing(self):
        base = {"advisory_type": "Security Advisory"}
        row = _build_cache_row("X", base, [], "ubuntu")
        assert row["issued_date"] is None
