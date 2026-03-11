"""
Test - Sync API Endpoints

GET  /api/v1/sync/status
POST /api/v1/sync/trigger
GET  /api/v1/errata/cache/stats
"""

from unittest.mock import patch, MagicMock

from tests.conftest import make_mock_cursor, make_mock_db


_POLLER_PATCH = "app.api.sync.poller"
_DB_PATCH     = "app.api.sync.get_db"


class TestSyncStatus:

    def test_returns_200(self, client):
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.get_sync_status.return_value = {
                "scheduler_running": True,
                "sync_running": False,
                "last_sync": None,
            }
            response = client.get("/api/v1/sync/status")
        assert response.status_code == 200

    def test_delegates_to_poller(self, client):
        expected = {"scheduler_running": True, "sync_running": False}
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.get_sync_status.return_value = expected
            data = client.get("/api/v1/sync/status").get_json()
        assert data["scheduler_running"] is True
        assert data["sync_running"] is False

    def test_json_response(self, client):
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.get_sync_status.return_value = {}
            response = client.get("/api/v1/sync/status")
        assert response.content_type == "application/json"


class TestSyncTrigger:

    def test_success_returns_200(self, client):
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.trigger_sync.return_value = {
                "status": "success", "inserted": 10, "updated": 5
            }
            response = client.post("/api/v1/sync/trigger")
        assert response.status_code == 200

    def test_error_status_returns_500(self, client):
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.trigger_sync.return_value = {
                "status": "error", "error": "UYUNI down"
            }
            response = client.post("/api/v1/sync/trigger")
        assert response.status_code == 500

    def test_skipped_status_returns_500(self, client):
        """'skipped' non è 'success' → 500."""
        with patch(_POLLER_PATCH) as mock_poller:
            mock_poller.trigger_sync.return_value = {
                "status": "skipped", "reason": "already running"
            }
            response = client.post("/api/v1/sync/trigger")
        assert response.status_code == 500

    def test_get_not_allowed(self, client):
        response = client.get("/api/v1/sync/trigger")
        assert response.status_code == 405


class TestErrataCacheStats:

    def _make_stats_cursor(self):
        """Cursore che simula la query aggregata di errata/cache/stats."""
        cur = MagicMock()
        cur.fetchone.return_value = {
            "total": 634,
            "critical": 50,
            "high": 150,
            "medium": 300,
            "ubuntu": 300,
            "debian": 0,
            "rhel": 334,
            "last_synced": None,
            "oldest_errata": None,
            "newest_errata": None,
        }
        return cur

    def test_returns_200(self, client):
        cur = self._make_stats_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            response = client.get("/api/v1/errata/cache/stats")
        assert response.status_code == 200

    def test_response_has_required_fields(self, client):
        cur = self._make_stats_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            data = client.get("/api/v1/errata/cache/stats").get_json()
        assert "total" in data
        assert "by_severity" in data
        assert "by_os" in data

    def test_total_from_db(self, client):
        cur = self._make_stats_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            data = client.get("/api/v1/errata/cache/stats").get_json()
        assert data["total"] == 634

    def test_db_error_returns_500(self, client):
        with patch(_DB_PATCH, side_effect=Exception("DB down")):
            response = client.get("/api/v1/errata/cache/stats")
        assert response.status_code == 500
