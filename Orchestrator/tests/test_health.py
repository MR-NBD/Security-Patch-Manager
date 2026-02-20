"""
Test - Health Endpoints

Esegui con: pytest tests/test_health.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from app.main import create_app


@pytest.fixture
def client():
    """Client Flask per i test"""
    # Mock init_db per evitare connessione reale
    with patch("app.main.init_db", return_value=True):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


class TestHealthBasic:
    """Test GET /api/v1/health"""

    def test_health_returns_200(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        response = client.get("/api/v1/health")
        data = response.get_json()
        assert data is not None

    def test_health_has_required_fields(self, client):
        response = client.get("/api/v1/health")
        data = response.get_json()
        assert "status" in data
        assert "version" in data
        assert "app" in data

    def test_health_status_is_healthy(self, client):
        response = client.get("/api/v1/health")
        data = response.get_json()
        assert data["status"] == "healthy"

    def test_health_app_name(self, client):
        response = client.get("/api/v1/health")
        data = response.get_json()
        assert data["app"] == "spm-orchestrator"


class TestHealthDetail:
    """Test GET /api/v1/health/detail"""

    def test_health_detail_returns_200_or_207(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_spm_sync", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni", return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):

            response = client.get("/api/v1/health/detail")
            assert response.status_code in [200, 207]

    def test_health_detail_has_components(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_spm_sync", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni", return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):

            response = client.get("/api/v1/health/detail")
            data = response.get_json()

            assert "components" in data
            assert "database" in data["components"]
            assert "spm_sync" in data["components"]
            assert "uyuni" in data["components"]
            assert "prometheus" in data["components"]

    def test_health_detail_degraded_if_db_error(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "error", "message": "Connection refused"}), \
             patch("app.api.health._check_spm_sync", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni", return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):

            response = client.get("/api/v1/health/detail")
            data = response.get_json()
            assert data["status"] == "degraded"
            assert response.status_code == 207

    def test_health_detail_has_uptime(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_spm_sync", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni", return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):

            response = client.get("/api/v1/health/detail")
            data = response.get_json()
            assert "uptime_seconds" in data
            assert isinstance(data["uptime_seconds"], int)


class TestErrorHandlers:
    """Test handler errori globali"""

    def test_404_returns_json(self, client):
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"] == "not_found"

    def test_405_returns_json(self, client):
        response = client.delete("/api/v1/health")
        assert response.status_code == 405
        data = response.get_json()
        assert data["error"] == "method_not_allowed"
