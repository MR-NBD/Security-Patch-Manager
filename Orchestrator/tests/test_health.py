"""
Test - Health Endpoints

Esegui con: pytest tests/test_health.py -v
"""

import pytest
from unittest.mock import patch
from app.main import create_app


@pytest.fixture
def client():
    """Client Flask per i test"""
    with patch("app.main.init_db", return_value=True):
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c


# ──────────────────────────────────────────────────────────────
# GET /api/v1/health
# ──────────────────────────────────────────────────────────────

class TestHealthBasic:
    """Test GET /api/v1/health — risposta rapida, nessun check componenti."""

    def test_health_returns_200(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        response = client.get("/api/v1/health")
        assert response.get_json() is not None

    def test_health_has_required_fields(self, client):
        data = client.get("/api/v1/health").get_json()
        assert "status" in data
        assert "version" in data
        assert "app" in data

    def test_health_status_is_healthy(self, client):
        data = client.get("/api/v1/health").get_json()
        assert data["status"] == "healthy"

    def test_health_app_name(self, client):
        data = client.get("/api/v1/health").get_json()
        assert data["app"] == "spm-orchestrator"

    def test_health_version_format(self, client):
        data = client.get("/api/v1/health").get_json()
        parts = data["version"].split(".")
        assert len(parts) >= 2
        assert all(p.isdigit() for p in parts)


# ──────────────────────────────────────────────────────────────
# GET /api/v1/health/detail
# ──────────────────────────────────────────────────────────────

class TestHealthDetail:
    """Test GET /api/v1/health/detail — check componenti DB/UYUNI/Prometheus."""

    def _all_ok_patches(self):
        """Context manager che mocca tutti i componenti come connected."""
        return [
            patch("app.api.health.check_db_health",
                  return_value={"status": "connected"}),
            patch("app.api.health._check_uyuni",
                  return_value={"status": "connected"}),
            patch("app.api.health._check_prometheus",
                  return_value={"status": "connected"}),
        ]

    def test_health_detail_returns_200_when_all_ok(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            response = client.get("/api/v1/health/detail")
            assert response.status_code == 200

    def test_health_detail_has_components(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            data = client.get("/api/v1/health/detail").get_json()
            assert "components" in data
            # Componenti attivi: database, uyuni, prometheus
            assert "database"   in data["components"]
            assert "uyuni"      in data["components"]
            assert "prometheus" in data["components"]

    def test_health_detail_has_uptime(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            data = client.get("/api/v1/health/detail").get_json()
            assert "uptime_seconds" in data
            assert isinstance(data["uptime_seconds"], int)

    def test_health_detail_has_version_and_app(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            data = client.get("/api/v1/health/detail").get_json()
            assert "version" in data
            assert "app"     in data

    def test_health_detail_degraded_if_db_error(self, client):
        with patch("app.api.health.check_db_health",
                   return_value={"status": "error", "message": "Connection refused"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            response = client.get("/api/v1/health/detail")
            data = response.get_json()
            assert data["status"] == "degraded"
            assert response.status_code == 207

    def test_health_detail_degraded_if_uyuni_error(self, client):
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",
                   return_value={"status": "error", "message": "Connection refused"}), \
             patch("app.api.health._check_prometheus", return_value={"status": "connected"}):
            response = client.get("/api/v1/health/detail")
            data = response.get_json()
            assert data["status"] == "degraded"
            assert response.status_code == 207

    def test_health_detail_healthy_if_only_prometheus_unavailable(self, client):
        """Prometheus non è critico — non porta a 'degraded'."""
        with patch("app.api.health.check_db_health", return_value={"status": "connected"}), \
             patch("app.api.health._check_uyuni",    return_value={"status": "connected"}), \
             patch("app.api.health._check_prometheus",
                   return_value={"status": "unavailable", "message": "not reachable"}):
            response = client.get("/api/v1/health/detail")
            data = response.get_json()
            assert data["status"] == "healthy"
            assert response.status_code == 200


# ──────────────────────────────────────────────────────────────
# Error handlers globali
# ──────────────────────────────────────────────────────────────

class TestErrorHandlers:
    """Test handler errori globali Flask."""

    def test_404_returns_json(self, client):
        response = client.get("/api/v1/nonexistent-endpoint")
        assert response.status_code == 404
        assert response.get_json()["error"] == "not_found"

    def test_405_returns_json(self, client):
        response = client.delete("/api/v1/health")
        assert response.status_code == 405
        assert response.get_json()["error"] == "method_not_allowed"
