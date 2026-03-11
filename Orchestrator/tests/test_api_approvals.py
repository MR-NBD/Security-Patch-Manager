"""
Test - Approvals API Endpoints

GET  /api/v1/approvals/pending
GET  /api/v1/approvals/pending/<id>
POST /api/v1/approvals/<id>/approve
POST /api/v1/approvals/<id>/reject
POST /api/v1/approvals/<id>/snooze
GET  /api/v1/approvals/history
"""

from unittest.mock import patch

_AM_PATCH = "app.api.approvals.approval_manager"

_SAMPLE_PENDING = {
    "id": 1,
    "errata_id": "USN-7412-2",
    "target_os": "ubuntu",
    "status": "pending_approval",
    "success_score": 80,
}

_SAMPLE_ACTION_RESULT = {
    "queue_id": 1,
    "action": "approved",
    "action_by": "op@example.com",
}


# ─────────────────────────────────────────────
# GET /api/v1/approvals/pending
# ─────────────────────────────────────────────

class TestListPending:

    def test_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.get_pending.return_value = [_SAMPLE_PENDING]
            response = client.get("/api/v1/approvals/pending")
        assert response.status_code == 200

    def test_returns_list(self, client):
        with patch(_AM_PATCH) as am:
            am.get_pending.return_value = [_SAMPLE_PENDING]
            data = client.get("/api/v1/approvals/pending").get_json()
        assert isinstance(data, list)

    def test_invalid_limit_returns_400(self, client):
        response = client.get("/api/v1/approvals/pending?limit=abc")
        assert response.status_code == 400

    def test_invalid_offset_returns_400(self, client):
        response = client.get("/api/v1/approvals/pending?offset=xyz")
        assert response.status_code == 400


# ─────────────────────────────────────────────
# GET /api/v1/approvals/pending/<id>
# ─────────────────────────────────────────────

class TestPendingDetail:

    def test_found_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.get_pending_detail.return_value = _SAMPLE_PENDING
            response = client.get("/api/v1/approvals/pending/1")
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch(_AM_PATCH) as am:
            am.get_pending_detail.return_value = None
            response = client.get("/api/v1/approvals/pending/9999")
        assert response.status_code == 404

    def test_response_contains_errata_id(self, client):
        with patch(_AM_PATCH) as am:
            am.get_pending_detail.return_value = _SAMPLE_PENDING
            data = client.get("/api/v1/approvals/pending/1").get_json()
        assert data["errata_id"] == "USN-7412-2"


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/approve
# ─────────────────────────────────────────────

class TestApprove:

    def _post(self, client, queue_id, body):
        return client.post(f"/api/v1/approvals/{queue_id}/approve",
                           json=body, content_type="application/json")

    def test_success_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.approve.return_value = _SAMPLE_ACTION_RESULT
            response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 200

    def test_missing_action_by_returns_400(self, client):
        response = self._post(client, 1, {})
        assert response.status_code == 400

    def test_empty_action_by_returns_400(self, client):
        response = self._post(client, 1, {"action_by": "  "})
        assert response.status_code == 400

    def test_not_pending_raises_422(self, client):
        with patch(_AM_PATCH) as am:
            am.approve.side_effect = ValueError("not in pending_approval")
            response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 422

    def test_generic_exception_returns_500(self, client):
        with patch(_AM_PATCH) as am:
            am.approve.side_effect = Exception("DB down")
            response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 500

    def test_response_contains_action(self, client):
        with patch(_AM_PATCH) as am:
            am.approve.return_value = _SAMPLE_ACTION_RESULT
            data = self._post(client, 1, {"action_by": "op@example.com"}).get_json()
        assert data["action"] == "approved"


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/reject
# ─────────────────────────────────────────────

class TestReject:

    def _post(self, client, queue_id, body):
        return client.post(f"/api/v1/approvals/{queue_id}/reject",
                           json=body, content_type="application/json")

    def test_success_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.reject.return_value = {**_SAMPLE_ACTION_RESULT, "action": "rejected"}
            response = self._post(client, 1, {
                "action_by": "op@example.com",
                "reason": "too risky",
            })
        assert response.status_code == 200

    def test_missing_action_by_returns_400(self, client):
        response = self._post(client, 1, {"reason": "no operator"})
        assert response.status_code == 400

    def test_not_pending_returns_422(self, client):
        with patch(_AM_PATCH) as am:
            am.reject.side_effect = ValueError("not in pending_approval")
            response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 422

    def test_generic_exception_returns_500(self, client):
        with patch(_AM_PATCH) as am:
            am.reject.side_effect = Exception("DB down")
            response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 500


# ─────────────────────────────────────────────
# POST /api/v1/approvals/<id>/snooze
# ─────────────────────────────────────────────

class TestSnooze:

    _VALID_BODY = {
        "action_by": "op@example.com",
        "snooze_until": "2026-04-01T08:00:00Z",
    }

    def _post(self, client, queue_id, body):
        return client.post(f"/api/v1/approvals/{queue_id}/snooze",
                           json=body, content_type="application/json")

    def test_success_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.snooze.return_value = {**_SAMPLE_ACTION_RESULT, "action": "snoozed"}
            response = self._post(client, 1, self._VALID_BODY)
        assert response.status_code == 200

    def test_missing_action_by_returns_400(self, client):
        response = self._post(client, 1, {"snooze_until": "2026-04-01T08:00:00Z"})
        assert response.status_code == 400

    def test_missing_snooze_until_returns_400(self, client):
        response = self._post(client, 1, {"action_by": "op@example.com"})
        assert response.status_code == 400

    def test_invalid_snooze_until_format_returns_400(self, client):
        response = self._post(client, 1, {
            "action_by": "op@example.com",
            "snooze_until": "not-a-date",
        })
        assert response.status_code == 400

    def test_not_pending_returns_422(self, client):
        with patch(_AM_PATCH) as am:
            am.snooze.side_effect = ValueError("not in pending_approval")
            response = self._post(client, 1, self._VALID_BODY)
        assert response.status_code == 422

    def test_generic_exception_returns_500(self, client):
        with patch(_AM_PATCH) as am:
            am.snooze.side_effect = Exception("DB down")
            response = self._post(client, 1, self._VALID_BODY)
        assert response.status_code == 500

    def test_snooze_until_naive_datetime_accepted(self, client):
        """Datetime senza timezone viene accettato (UTC assunto)."""
        with patch(_AM_PATCH) as am:
            am.snooze.return_value = {**_SAMPLE_ACTION_RESULT, "action": "snoozed"}
            response = self._post(client, 1, {
                "action_by": "op@example.com",
                "snooze_until": "2026-04-01T08:00:00",
            })
        assert response.status_code == 200


# ─────────────────────────────────────────────
# GET /api/v1/approvals/history
# ─────────────────────────────────────────────

class TestHistory:

    def test_returns_200(self, client):
        with patch(_AM_PATCH) as am:
            am.get_history.return_value = []
            response = client.get("/api/v1/approvals/history")
        assert response.status_code == 200

    def test_returns_list(self, client):
        with patch(_AM_PATCH) as am:
            am.get_history.return_value = [_SAMPLE_ACTION_RESULT]
            data = client.get("/api/v1/approvals/history").get_json()
        assert isinstance(data, list)

    def test_invalid_limit_returns_400(self, client):
        response = client.get("/api/v1/approvals/history?limit=abc")
        assert response.status_code == 400

    def test_delegates_to_manager(self, client):
        with patch(_AM_PATCH) as am:
            am.get_history.return_value = [_SAMPLE_ACTION_RESULT]
            data = client.get("/api/v1/approvals/history").get_json()
        assert len(data) == 1
        am.get_history.assert_called_once()
