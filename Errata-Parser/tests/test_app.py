"""
Unit tests per UYUNI Errata Manager.

Eseguire con:
    pip install pytest
    pytest tests/ -v
"""

import os
import sys

# Imposta DATABASE_URL e SPM_API_KEY prima di importare app
# (il modulo esce se DATABASE_URL non è impostata)
os.environ.setdefault('DATABASE_URL', 'postgresql://fake:fake@localhost/fake')
os.environ.setdefault('SPM_API_KEY', 'test-key-12345')
os.environ.setdefault('UYUNI_URL', '')

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest


# ============================================================
# Import dopo aver impostato le variabili d'ambiente
# ============================================================
from app import (
    version_ge,
    _split_epoch,
    _compare_version_string,
    map_channel_to_distribution,
    _build_package_ids,
    _sanitize_error,
    cvss_to_severity,
    _RE_CVE,
)


# ============================================================
# version_ge
# ============================================================
class TestVersionGe:

    def test_simple_equal(self):
        assert version_ge('1.2.3', '1.2.3') is True

    def test_simple_greater(self):
        assert version_ge('2.0.0', '1.9.9') is True

    def test_simple_less(self):
        assert version_ge('1.0.0', '2.0.0') is False

    def test_empty_strings(self):
        assert version_ge('', '') is True
        assert version_ge('1.0', '') is True
        assert version_ge('', '1.0') is True

    def test_epoch_equal(self):
        assert version_ge('1:2.3.0-1', '1:2.3.0-1') is True

    def test_epoch_higher(self):
        # epoch 2 > epoch 1 indipendentemente dalla versione
        assert version_ge('2:1.0.0', '1:9.9.9') is True

    def test_epoch_lower(self):
        assert version_ge('1:9.9.9', '2:1.0.0') is False

    def test_epoch_same_version_compare(self):
        assert version_ge('1:2.4.0-1', '1:2.3.0-1') is True
        assert version_ge('1:2.3.0-1', '1:2.4.0-1') is False

    def test_debian_revision_compare(self):
        # Rev 4+deb12u1: numeric part = 4 > 3 → True
        assert version_ge('2.3.1-4+deb12u1', '2.3.1-3ubuntu0.10') is True

    def test_ubuntu_security_update(self):
        # 8.9p1-3ubuntu0.10 è una security update di 8.9p1
        assert version_ge('8.9p1-3ubuntu0.10', '8.9p1') is True

    def test_non_comparable_returns_false(self):
        # Il fallback conservativo deve restituire False per versioni non confrontabili
        result = version_ge('1:abc-xyz', '2:???')
        assert result is False

    def test_none_values(self):
        assert version_ge(None, None) is True
        assert version_ge('1.0', None) is True
        assert version_ge(None, '1.0') is True


# ============================================================
# _split_epoch
# ============================================================
class TestSplitEpoch:

    def test_with_epoch(self):
        assert _split_epoch('1:2.3-4') == (1, '2.3-4')

    def test_high_epoch(self):
        assert _split_epoch('10:1.0') == (10, '1.0')

    def test_without_epoch(self):
        assert _split_epoch('2.3-4') == (0, '2.3-4')

    def test_empty(self):
        assert _split_epoch('') == (0, '')


# ============================================================
# _compare_version_string (algoritmo dpkg)
# ============================================================
class TestCompareVersionString:

    def test_equal(self):
        assert _compare_version_string('1.2.3', '1.2.3') == 0

    def test_numeric_greater(self):
        assert _compare_version_string('1.10.0', '1.9.0') > 0

    def test_numeric_less(self):
        assert _compare_version_string('1.9.0', '1.10.0') < 0

    def test_alpha_suffix(self):
        # '8.9p1' vs '8.9p1' → equal
        assert _compare_version_string('8.9p1', '8.9p1') == 0

    def test_ubuntu_revision(self):
        # '1ubuntu1.15' > '1ubuntu1.14'
        assert _compare_version_string('1ubuntu1.15', '1ubuntu1.14') > 0
        assert _compare_version_string('1ubuntu1.14', '1ubuntu1.15') < 0

    def test_tilde_sorts_before_empty(self):
        # '1.0~rc1' < '1.0'
        assert _compare_version_string('1.0~rc1', '1.0') < 0


# ============================================================
# map_channel_to_distribution
# ============================================================
class TestMapChannelToDistribution:

    def test_ubuntu(self):
        assert map_channel_to_distribution('ubuntu-22.04-amd64') == 'ubuntu'

    def test_debian_bookworm(self):
        assert map_channel_to_distribution('debian-bookworm-x86_64') == 'debian-bookworm'

    def test_debian_bullseye(self):
        assert map_channel_to_distribution('debian-bullseye-amd64') == 'debian-bullseye'

    def test_debian_trixie(self):
        assert map_channel_to_distribution('debian-trixie-x86_64') == 'debian-trixie'

    def test_debian_by_version_number(self):
        assert map_channel_to_distribution('debian-12-amd64') == 'debian-bookworm'
        assert map_channel_to_distribution('debian-11-x86_64') == 'debian-bullseye'
        assert map_channel_to_distribution('debian-13-amd64') == 'debian-trixie'

    def test_unrecognized(self):
        assert map_channel_to_distribution('centos-7-x86_64') is None
        assert map_channel_to_distribution('rhel8-base') is None

    def test_case_insensitive(self):
        assert map_channel_to_distribution('Ubuntu-22.04') == 'ubuntu'
        assert map_channel_to_distribution('DEBIAN-Bookworm') == 'debian-bookworm'


# ============================================================
# _build_package_ids
# ============================================================
class TestBuildPackageIds:

    def _make_errata_pkg(self, name, version, release='jammy'):
        return {'package_name': name, 'fixed_version': version, 'release_name': release}

    def _make_cached_pkg(self, name, pkg_id, version):
        return {'package_name': name, 'package_id': pkg_id, 'package_version': version}

    def test_basic_match(self):
        errata_pkgs = [self._make_errata_pkg('openssh-server', '8.9p1-3ubuntu0.10')]
        cached_pkgs = [self._make_cached_pkg('openssh-server', 101, '8.9p1-3ubuntu0.10')]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {101}

    def test_newer_version_in_cache(self):
        errata_pkgs = [self._make_errata_pkg('curl', '7.81.0-1ubuntu1.15')]
        cached_pkgs = [self._make_cached_pkg('curl', 202, '7.81.0-1ubuntu1.16')]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {202}

    def test_older_version_in_cache_excluded(self):
        errata_pkgs = [self._make_errata_pkg('curl', '7.81.0-1ubuntu1.15')]
        cached_pkgs = [self._make_cached_pkg('curl', 202, '7.81.0-1ubuntu1.14')]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == set()

    def test_no_fixed_version(self):
        # Se fixed_version è vuota include il package senza confronto
        errata_pkgs = [self._make_errata_pkg('libssl3', '')]
        cached_pkgs = [self._make_cached_pkg('libssl3', 303, '3.0.2-0ubuntu1.12')]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {303}

    def test_multi_release(self):
        # Stessa errata con versioni diverse per jammy e noble
        errata_pkgs = [
            self._make_errata_pkg('openssl', '3.0.2-0ubuntu1.15', 'jammy'),
            self._make_errata_pkg('openssl', '3.2.1-1ubuntu1', 'noble'),
        ]
        cached_pkgs = [
            self._make_cached_pkg('openssl', 401, '3.0.2-0ubuntu1.15'),  # jammy match
            self._make_cached_pkg('openssl', 402, '3.2.1-1ubuntu1'),     # noble match
        ]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {401, 402}

    def test_package_not_in_errata(self):
        # Package in cache ma non in errata_packages → non associare
        errata_pkgs = [self._make_errata_pkg('curl', '7.81.0')]
        cached_pkgs = [
            self._make_cached_pkg('curl', 501, '7.81.0'),
            self._make_cached_pkg('wget', 502, '1.21.0'),  # non in errata
        ]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {501}

    def test_empty_inputs(self):
        assert _build_package_ids([], []) == set()
        assert _build_package_ids([self._make_errata_pkg('curl', '1.0')], []) == set()

    def test_epoch_match(self):
        errata_pkgs = [self._make_errata_pkg('bind9', '1:9.18.18-0ubuntu0.22.04.2')]
        cached_pkgs = [self._make_cached_pkg('bind9', 601, '1:9.18.18-0ubuntu0.22.04.2')]
        assert _build_package_ids(errata_pkgs, cached_pkgs) == {601}


# ============================================================
# _sanitize_error
# ============================================================
class TestSanitizeError:

    def test_always_generic(self):
        assert _sanitize_error(Exception('some error')) == 'Internal error — see application logs'

    def test_password_not_leaked(self):
        result = _sanitize_error(Exception('password=mysecret123'))
        assert 'mysecret123' not in result

    def test_connection_string_not_leaked(self):
        result = _sanitize_error(Exception(
            'psycopg2.OperationalError: FATAL: role "errataparser" does not exist '
            'postgresql://errataparser:ErrataLocal2024@localhost:5432/uyuni_errata'
        ))
        assert 'ErrataLocal2024' not in result
        assert 'errataparser' not in result


# ============================================================
# cvss_to_severity
# ============================================================
class TestCvssToSeverity:

    def test_critical(self):
        assert cvss_to_severity(9.8) == 'CRITICAL'
        assert cvss_to_severity(9.0) == 'CRITICAL'

    def test_high(self):
        assert cvss_to_severity(8.5) == 'HIGH'
        assert cvss_to_severity(7.0) == 'HIGH'

    def test_medium(self):
        assert cvss_to_severity(6.9) == 'MEDIUM'
        assert cvss_to_severity(4.0) == 'MEDIUM'

    def test_low(self):
        assert cvss_to_severity(3.9) == 'LOW'
        assert cvss_to_severity(0.0) == 'LOW'

    def test_none(self):
        assert cvss_to_severity(None) is None


# ============================================================
# _RE_CVE validation
# ============================================================
class TestCveRegex:

    def test_valid(self):
        assert _RE_CVE.match('CVE-2024-12345')
        assert _RE_CVE.match('CVE-2023-1234')
        assert _RE_CVE.match('CVE-2019-123456')

    def test_invalid_format(self):
        assert not _RE_CVE.match('cve-2024-12345')   # lowercase
        assert not _RE_CVE.match('CVE-24-12345')     # anno corto
        assert not _RE_CVE.match('CVE-2024-123')     # numero corto (< 4 cifre)
        assert not _RE_CVE.match('CVE2024-12345')    # manca primo trattino
        assert not _RE_CVE.match('CVE-2024-ABCD')    # lettere nel numero
        assert not _RE_CVE.match('')

    def test_no_partial_match(self):
        # Il match deve essere sull'intera stringa (usa match, non search)
        assert not _RE_CVE.match('prefix-CVE-2024-12345')


# ============================================================
# Flask endpoints (smoke test con test client)
# ============================================================
class TestHealthEndpoint:

    @pytest.fixture(autouse=True)
    def client(self):
        from app import app
        app.config['TESTING'] = True
        with app.test_client() as c:
            self.client = c
            yield c

    def test_health_no_auth_required(self):
        """Health endpoint non richiede X-API-Key."""
        resp = self.client.get('/api/health')
        # Può essere 200 o 500 (DB non disponibile) ma non 401/503
        assert resp.status_code in (200, 500)

    def test_auth_required_on_sync(self):
        """Endpoint autenticati richiedono X-API-Key."""
        resp = self.client.post('/api/sync/usn')
        assert resp.status_code == 401

    def test_auth_with_valid_key(self):
        """Con chiave corretta la richiesta passa (può fallire per DB assente)."""
        resp = self.client.post('/api/sync/usn', headers={'X-API-Key': 'test-key-12345'})
        # 500 è accettabile (DB non disponibile in test), 401/503 no
        assert resp.status_code != 401
        assert resp.status_code != 503

    def test_auth_with_wrong_key(self):
        resp = self.client.post('/api/sync/usn', headers={'X-API-Key': 'wrong-key'})
        assert resp.status_code == 401
        data = resp.get_json()
        assert data['error'] == 'Unauthorized'
