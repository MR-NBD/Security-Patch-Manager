"""
Test - Tests API Endpoints

GET    /api/v1/tests/status
POST   /api/v1/tests/run
POST   /api/v1/tests/batch
GET    /api/v1/tests/batch/<id>/status
POST   /api/v1/tests/batch/<id>/cancel
GET    /api/v1/tests/<id>
"""

from unittest.mock import patch, MagicMock

from tests.conftest import make_mock_cursor, make_mock_db


_ENGINE_STATUS_PATCH  = "app.api.tests.get_engine_status"
_RUN_NEXT_PATCH       = "app.api.tests.run_next_test"
_START_BATCH_PATCH    = "app.api.tests.start_batch"
_BATCH_STATUS_PATCH   = "app.api.tests.get_batch_status"
_CANCEL_BATCH_PATCH   = "app.api.tests.cancel_batch"
_DB_PATCH             = "app.api.tests.get_db"

_ENGINE_STATUS_RUNNING = {"testing": True,  "last_result": None}
_ENGINE_STATUS_IDLE    = {"testing": False, "last_result": "passed"}

_SAMPLE_TEST = {
    "id": 10,
    "queue_id": 1,
    "errata_id": "USN-7412-2",
    "result": "passed",
    "started_at": "2026-03-11T10:00:00+00:00",
    "completed_at": "2026-03-11T10:05:00+00:00",
    "duration_seconds": 300,
    "failure_phase": None,
    "failure_reason": None,
    "priority_override": 0,
    "created_by": "operator",
    "synopsis": "USN-7412-2 fix",
    "severity": "High",
    "errata_type": "security",
}


# ─────────────────────────────────────────────
# GET /api/v1/tests/status
# ─────────────────────────────────────────────

class TestEngineStatus:

    def _stats_cursor(self):
        cur = make_mock_cursor(fetchone_result={
            "passed_24h": 5, "failed_24h": 1,
            "error_24h": 0,  "avg_duration_s": 300,
        })
        return cur

    def test_returns_200(self, client):
        with patch(_ENGINE_STATUS_PATCH, return_value=_ENGINE_STATUS_IDLE), \
             patch(_DB_PATCH, return_value=make_mock_db(self._stats_cursor())):
            response = client.get("/api/v1/tests/status")
        assert response.status_code == 200

    def test_response_has_required_fields(self, client):
        with patch(_ENGINE_STATUS_PATCH, return_value=_ENGINE_STATUS_IDLE), \
             patch(_DB_PATCH, return_value=make_mock_db(self._stats_cursor())):
            data = client.get("/api/v1/tests/status").get_json()
        assert "engine_running" in data
        assert "last_result" in data
        assert "stats_24h" in data

    def test_engine_running_reflects_status(self, client):
        with patch(_ENGINE_STATUS_PATCH, return_value=_ENGINE_STATUS_RUNNING), \
             patch(_DB_PATCH, return_value=make_mock_db(self._stats_cursor())):
            data = client.get("/api/v1/tests/status").get_json()
        assert data["engine_running"] is True

    def test_db_failure_still_returns_200(self, client):
        """DB stats failure non blocca la risposta — stats_24h vuoto."""
        with patch(_ENGINE_STATUS_PATCH, return_value=_ENGINE_STATUS_IDLE), \
             patch(_DB_PATCH, side_effect=Exception("DB down")):
            response = client.get("/api/v1/tests/status")
        assert response.status_code == 200


# ─────────────────────────────────────────────
# POST /api/v1/tests/run
# ─────────────────────────────────────────────

class TestRunNextTest:

    def test_success_returns_200(self, client):
        with patch(_RUN_NEXT_PATCH, return_value={"status": "completed", "errata_id": "USN-7412-2"}):
            response = client.post("/api/v1/tests/run")
        assert response.status_code == 200

    def test_skipped_returns_202(self, client):
        with patch(_RUN_NEXT_PATCH, return_value={"status": "skipped", "reason": "empty queue"}):
            response = client.post("/api/v1/tests/run")
        assert response.status_code == 202

    def test_error_returns_500(self, client):
        with patch(_RUN_NEXT_PATCH, return_value={"status": "error", "error": "UYUNI down"}):
            response = client.post("/api/v1/tests/run")
        assert response.status_code == 500

    def test_get_not_allowed(self, client):
        response = client.get("/api/v1/tests/run")
        assert response.status_code == 405

    def test_response_contains_status(self, client):
        with patch(_RUN_NEXT_PATCH, return_value={"status": "completed"}):
            data = client.post("/api/v1/tests/run").get_json()
        assert "status" in data


# ─────────────────────────────────────────────
# POST /api/v1/tests/batch
# ─────────────────────────────────────────────

class TestStartBatch:

    def _post(self, client, body):
        return client.post("/api/v1/tests/batch",
                           json=body, content_type="application/json")

    def test_success_returns_202(self, client):
        with patch(_START_BATCH_PATCH, return_value="batch-abc-123"):
            response = self._post(client, {
                "queue_ids": [1, 2, 3],
                "group_name": "test-ubuntu-2404",
                "operator": "op@example.com",
            })
        assert response.status_code == 202

    def test_response_has_batch_id(self, client):
        with patch(_START_BATCH_PATCH, return_value="batch-abc-123"):
            data = self._post(client, {
                "queue_ids": [1],
                "group_name": "test-ubuntu-2404",
                "operator": "op@example.com",
            }).get_json()
        assert data["batch_id"] == "batch-abc-123"
        assert data["status"] == "started"
        assert data["total"] == 1

    def test_missing_queue_ids_returns_400(self, client):
        response = self._post(client, {
            "group_name": "test-ubuntu-2404",
            "operator": "op@example.com",
        })
        assert response.status_code == 400

    def test_empty_queue_ids_returns_400(self, client):
        response = self._post(client, {
            "queue_ids": [],
            "group_name": "test-ubuntu-2404",
            "operator": "op@example.com",
        })
        assert response.status_code == 400

    def test_non_int_queue_ids_returns_400(self, client):
        response = self._post(client, {
            "queue_ids": ["abc"],
            "group_name": "test-ubuntu-2404",
            "operator": "op@example.com",
        })
        assert response.status_code == 400

    def test_too_many_queue_ids_returns_400(self, client):
        response = self._post(client, {
            "queue_ids": list(range(101)),
            "group_name": "test-ubuntu-2404",
            "operator": "op@example.com",
        })
        assert response.status_code == 400

    def test_missing_group_name_returns_400(self, client):
        response = self._post(client, {
            "queue_ids": [1],
            "operator": "op@example.com",
        })
        assert response.status_code == 400

    def test_missing_operator_returns_400(self, client):
        response = self._post(client, {
            "queue_ids": [1],
            "group_name": "test-ubuntu-2404",
        })
        assert response.status_code == 400

    def test_engine_busy_returns_409(self, client):
        with patch(_START_BATCH_PATCH, return_value=None):
            response = self._post(client, {
                "queue_ids": [1],
                "group_name": "test-ubuntu-2404",
                "operator": "op@example.com",
            })
        assert response.status_code == 409


# ─────────────────────────────────────────────
# GET /api/v1/tests/batch/<id>/status
# ─────────────────────────────────────────────

class TestBatchStatus:

    def test_found_returns_200(self, client):
        with patch(_BATCH_STATUS_PATCH, return_value={"batch_id": "abc", "status": "running"}):
            response = client.get("/api/v1/tests/batch/abc/status")
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch(_BATCH_STATUS_PATCH, return_value=None):
            response = client.get("/api/v1/tests/batch/unknown/status")
        assert response.status_code == 404

    def test_response_contains_batch_data(self, client):
        payload = {"batch_id": "abc", "status": "completed", "total": 3, "done": 3}
        with patch(_BATCH_STATUS_PATCH, return_value=payload):
            data = client.get("/api/v1/tests/batch/abc/status").get_json()
        assert data["batch_id"] == "abc"
        assert data["status"] == "completed"


# ─────────────────────────────────────────────
# POST /api/v1/tests/batch/<id>/cancel
# ─────────────────────────────────────────────

class TestCancelBatch:

    def test_cancelled_returns_200(self, client):
        with patch(_CANCEL_BATCH_PATCH, return_value={"cancelled": True}):
            response = client.post("/api/v1/tests/batch/abc/cancel")
        assert response.status_code == 200

    def test_not_cancellable_returns_409(self, client):
        with patch(_CANCEL_BATCH_PATCH, return_value={"cancelled": False, "reason": "not found"}):
            response = client.post("/api/v1/tests/batch/abc/cancel")
        assert response.status_code == 409

    def test_response_contains_cancelled_flag(self, client):
        with patch(_CANCEL_BATCH_PATCH, return_value={"cancelled": True}):
            data = client.post("/api/v1/tests/batch/abc/cancel").get_json()
        assert data["cancelled"] is True


# ─────────────────────────────────────────────
# GET /api/v1/tests/<id>
# ─────────────────────────────────────────────

class TestGetTest:

    def _make_db_with_test(self, test_row, phases=None):
        cur = MagicMock()
        cur.fetchone.return_value = test_row
        cur.fetchall.return_value = phases or []
        db = make_mock_db(cur)
        return db

    def test_found_returns_200(self, client):
        db = self._make_db_with_test(_SAMPLE_TEST)
        with patch(_DB_PATCH, return_value=db):
            response = client.get("/api/v1/tests/10")
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        db = self._make_db_with_test(None)
        with patch(_DB_PATCH, return_value=db):
            response = client.get("/api/v1/tests/9999")
        assert response.status_code == 404

    def test_response_contains_errata_id(self, client):
        db = self._make_db_with_test(_SAMPLE_TEST)
        with patch(_DB_PATCH, return_value=db):
            data = client.get("/api/v1/tests/10").get_json()
        assert data["errata_id"] == "USN-7412-2"

    def test_response_contains_phases(self, client):
        phase = {"id": 1, "phase_name": "patch", "status": "completed",
                 "started_at": None, "completed_at": None,
                 "duration_seconds": 60, "error_message": None, "output": None}
        db = self._make_db_with_test(_SAMPLE_TEST, phases=[phase])
        with patch(_DB_PATCH, return_value=db):
            data = client.get("/api/v1/tests/10").get_json()
        assert "phases" in data
        assert len(data["phases"]) == 1

    def test_db_exception_returns_500(self, client):
        with patch(_DB_PATCH, side_effect=Exception("DB down")):
            response = client.get("/api/v1/tests/10")
        assert response.status_code == 500
