"""
Test - UYUNI Client (funzioni pure + mock XML-RPC)

Funzioni pure: os_from_group(), severity_from_advisory_type()
Con mock: UyuniSession.get_errata_details_severity(), get_test_groups(), ecc.
"""

from unittest.mock import MagicMock, patch

from app.services.uyuni_client import (
    os_from_group,
    severity_from_advisory_type,
    _UYUNI_SEVERITY_MAP,
    UyuniSession,
)


# ──────────────────────────────────────────────────────────────
# Fixture helper — mock proxy UYUNI
# ──────────────────────────────────────────────────────────────

def make_session_with_mock_proxy():
    """Ritorna (session, mock_proxy) con _make_proxy patchato."""
    mock_proxy = MagicMock()
    mock_proxy.auth.login.return_value = "fake-session-key"
    session = UyuniSession.__new__(UyuniSession)
    session._url = "https://uyuni.test/rpc/api"
    session._username = "admin"
    session._password = "pass"
    session._key = None
    import threading
    session._local = threading.local()
    session._local.proxy = mock_proxy
    session._key = "fake-session-key"
    return session, mock_proxy


# ──────────────────────────────────────────────────────────────
# os_from_group()
# ──────────────────────────────────────────────────────────────

class TestOsFromGroup:
    """Testa os_from_group() — mappa nome gruppo UYUNI → target_os."""

    def test_ubuntu_group(self):
        assert os_from_group("test-ubuntu-2404") == "ubuntu"

    def test_ubuntu_2204(self):
        assert os_from_group("test-ubuntu-2204") == "ubuntu"

    def test_rhel9_group(self):
        assert os_from_group("test-rhel9") == "rhel"

    def test_rhel8_group(self):
        assert os_from_group("test-rhel8") == "rhel"

    def test_centos_group(self):
        assert os_from_group("test-centos7") == "rhel"

    def test_debian_group(self):
        assert os_from_group("test-debian12") == "debian"

    def test_custom_os_returns_first_segment(self):
        """Gruppo non riconosciuto → primo segmento dopo il prefisso."""
        assert os_from_group("test-suse-15") == "suse"

    def test_prefix_is_removed(self):
        """Il prefisso 'test-' viene rimosso prima del matching."""
        result = os_from_group("test-ubuntu-2404")
        assert result == "ubuntu"
        assert "test" not in result


# ──────────────────────────────────────────────────────────────
# severity_from_advisory_type()
# ──────────────────────────────────────────────────────────────

class TestSeverityFromAdvisoryType:
    """Testa severity_from_advisory_type() — mapping statico advisory_type → severity."""

    def test_security_advisory_returns_medium(self):
        assert severity_from_advisory_type("Security Advisory") == "Medium"

    def test_bug_fix_advisory_returns_low(self):
        assert severity_from_advisory_type("Bug Fix Advisory") == "Low"

    def test_enhancement_advisory_returns_low(self):
        assert severity_from_advisory_type("Product Enhancement Advisory") == "Low"

    def test_unknown_type_returns_unknown(self):
        assert severity_from_advisory_type("Something Else") == "Unknown"

    def test_empty_string_returns_unknown(self):
        assert severity_from_advisory_type("") == "Unknown"

    def test_case_sensitive(self):
        """Il mapping è case-sensitive."""
        assert severity_from_advisory_type("security advisory") == "Unknown"


# ──────────────────────────────────────────────────────────────
# _UYUNI_SEVERITY_MAP
# ──────────────────────────────────────────────────────────────

class TestUyuniSeverityMap:
    """Verifica i valori della mappa UYUNI label → interno."""

    def test_critical_maps_to_critical(self):
        assert _UYUNI_SEVERITY_MAP["Critical"] == "Critical"

    def test_important_maps_to_high(self):
        assert _UYUNI_SEVERITY_MAP["Important"] == "High"

    def test_moderate_maps_to_medium(self):
        assert _UYUNI_SEVERITY_MAP["Moderate"] == "Medium"

    def test_low_maps_to_low(self):
        assert _UYUNI_SEVERITY_MAP["Low"] == "Low"

    def test_unspecified_not_in_map(self):
        assert "Unspecified" not in _UYUNI_SEVERITY_MAP

    def test_empty_string_not_in_map(self):
        assert "" not in _UYUNI_SEVERITY_MAP

    def test_map_has_exactly_four_entries(self):
        assert len(_UYUNI_SEVERITY_MAP) == 4


# ──────────────────────────────────────────────────────────────
# UyuniSession.get_errata_details_severity()
# ──────────────────────────────────────────────────────────────

class TestGetErrataDetailsSeverity:
    """Testa get_errata_details_severity() con proxy UYUNI mockato."""

    def test_critical_label_returns_critical(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "Critical"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result == "Critical"

    def test_important_label_returns_high(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "Important"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result == "High"

    def test_moderate_label_returns_medium(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "Moderate"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result == "Medium"

    def test_low_label_returns_low(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "Low"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result == "Low"

    def test_unspecified_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "Unspecified"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result is None

    def test_missing_severity_field_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"other_field": "value"}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result is None

    def test_none_severity_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": None}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result is None

    def test_empty_severity_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": ""}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result is None

    def test_xml_rpc_exception_returns_none(self):
        """Eccezione XML-RPC → None (graceful degradation)."""
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.side_effect = Exception("UYUNI error")
        result = session.get_errata_details_severity("USN-7412-2")
        assert result is None

    def test_severity_with_leading_trailing_spaces(self):
        """Severity con spazi viene strip()ata prima del lookup."""
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.getDetails.return_value = {"severity": "  Critical  "}
        result = session.get_errata_details_severity("USN-7412-2")
        assert result == "Critical"


# ──────────────────────────────────────────────────────────────
# UyuniSession.get_test_groups()
# ──────────────────────────────────────────────────────────────

class TestGetTestGroups:
    """Testa get_test_groups() — filtra per prefisso 'test-'."""

    def test_filters_non_test_groups(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.systemgroup.listAllGroups.return_value = [
            {"name": "test-ubuntu-2404", "id": 1},
            {"name": "production-servers", "id": 2},
            {"name": "test-rhel9", "id": 3},
            {"name": "staging", "id": 4},
        ]
        result = session.get_test_groups()
        names = [g["name"] for g in result]
        assert "test-ubuntu-2404" in names
        assert "test-rhel9" in names
        assert "production-servers" not in names
        assert "staging" not in names

    def test_returns_empty_when_no_test_groups(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.systemgroup.listAllGroups.return_value = [
            {"name": "production", "id": 1},
        ]
        result = session.get_test_groups()
        assert result == []

    def test_returns_all_when_all_are_test(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.systemgroup.listAllGroups.return_value = [
            {"name": "test-ubuntu-2404", "id": 1},
            {"name": "test-rhel9", "id": 2},
        ]
        result = session.get_test_groups()
        assert len(result) == 2

    def test_exception_is_re_raised(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.systemgroup.listAllGroups.side_effect = Exception("UYUNI down")
        import pytest
        with pytest.raises(Exception, match="UYUNI down"):
            session.get_test_groups()


# ──────────────────────────────────────────────────────────────
# UyuniSession.get_errata_cves()
# ──────────────────────────────────────────────────────────────

class TestGetErrataCves:
    """Testa get_errata_cves() — lista CVE IDs."""

    def test_returns_cve_list(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listCves.return_value = ["CVE-2024-1234", "CVE-2024-5678"]
        result = session.get_errata_cves("USN-7412-2")
        assert result == ["CVE-2024-1234", "CVE-2024-5678"]

    def test_returns_empty_list_on_exception(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listCves.side_effect = Exception("UYUNI error")
        result = session.get_errata_cves("USN-7412-2")
        assert result == []

    def test_returns_empty_list_when_no_cves(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listCves.return_value = []
        result = session.get_errata_cves("USN-7412-2")
        assert result == []


# ──────────────────────────────────────────────────────────────
# UyuniSession.get_errata_packages()
# ──────────────────────────────────────────────────────────────

class TestGetErrataPackages:
    """Testa get_errata_packages() — mapping pacchetti UYUNI → {name, version, size_kb}."""

    def test_maps_package_fields_correctly(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listPackages.return_value = [{
            "name": "openssl", "version": "3.0.2", "file_size": 2048000,
        }]
        result = session.get_errata_packages("USN-7412-2")
        assert len(result) == 1
        assert result[0]["name"] == "openssl"
        assert result[0]["version"] == "3.0.2"
        assert result[0]["size_kb"] == 2000  # 2048000 // 1024

    def test_file_size_none_gives_zero_size_kb(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listPackages.return_value = [{
            "name": "pkg", "version": "1.0", "file_size": None,
        }]
        result = session.get_errata_packages("X")
        assert result[0]["size_kb"] == 0

    def test_returns_empty_on_exception(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listPackages.side_effect = Exception("error")
        result = session.get_errata_packages("X")
        assert result == []

    def test_multiple_packages(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.errata.listPackages.return_value = [
            {"name": "pkg1", "version": "1.0", "file_size": 1024},
            {"name": "pkg2", "version": "2.0", "file_size": 2048},
        ]
        result = session.get_errata_packages("X")
        assert len(result) == 2


# ──────────────────────────────────────────────────────────────
# UyuniSession.get_system_network_ip()
# ──────────────────────────────────────────────────────────────

class TestGetSystemNetworkIp:
    """Testa get_system_network_ip() — risolve IP da system.getNetwork."""

    def test_returns_ip_field(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.return_value = {"ip": "10.172.2.18"}
        result = session.get_system_network_ip(1000010000)
        assert result == "10.172.2.18"

    def test_falls_back_to_ip4(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.return_value = {"ip4": "10.172.2.18"}
        result = session.get_system_network_ip(1000010000)
        assert result == "10.172.2.18"

    def test_prefers_ip_over_ip4(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.return_value = {
            "ip": "10.172.2.18", "ip4": "192.168.1.1"
        }
        result = session.get_system_network_ip(1000010000)
        assert result == "10.172.2.18"

    def test_loopback_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.return_value = {"ip": "127.0.0.1"}
        result = session.get_system_network_ip(1000010000)
        assert result is None

    def test_exception_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.side_effect = Exception("UYUNI error")
        result = session.get_system_network_ip(1000010000)
        assert result is None

    def test_empty_ip_returns_none(self):
        session, proxy = make_session_with_mock_proxy()
        proxy.system.getNetwork.return_value = {"ip": ""}
        result = session.get_system_network_ip(1000010000)
        assert result is None
