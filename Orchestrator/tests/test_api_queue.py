"""
Test - Queue API Endpoints

GET    /api/v1/queue
POST   /api/v1/queue
GET    /api/v1/queue/stats
GET    /api/v1/queue/<id>
PATCH  /api/v1/queue/<id>
DELETE /api/v1/queue/<id>
"""

from unittest.mock import patch

_QM_PATCH = "app.api.queue.qm"

_SAMPLE_ITEM = {
    "id": 1,
    "errata_id": "USN-7412-2",
    "target_os": "ubuntu",
    "status": "queued",
    "success_score": 80,
    "priority_override": 0,
    "queued_at": "2026-03-11T10:00:00+00:00",
    "superseded": [],
}


class TestListQueue:

    def test_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue.return_value = [_SAMPLE_ITEM]
            qm.get_queue_stats.return_value = {"total": 1}
            response = client.get("/api/v1/queue")
        assert response.status_code == 200

    def test_response_is_list(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue.return_value = [_SAMPLE_ITEM]
            data = client.get("/api/v1/queue").get_json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_valid_status_filter(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue.return_value = []
            qm.get_queue_stats.return_value = {"total": 0}
            response = client.get("/api/v1/queue?status=queued")
        assert response.status_code == 200

    def test_invalid_status_returns_400(self, client):
        response = client.get("/api/v1/queue?status=invalid_status")
        assert response.status_code == 400

    def test_valid_os_filter(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue.return_value = []
            qm.get_queue_stats.return_value = {"total": 0}
            response = client.get("/api/v1/queue?target_os=ubuntu")
        assert response.status_code == 200

    def test_invalid_os_returns_400(self, client):
        response = client.get("/api/v1/queue?target_os=windows")
        assert response.status_code == 400

    def test_invalid_limit_returns_400(self, client):
        response = client.get("/api/v1/queue?limit=abc")
        assert response.status_code == 400

    def test_qm_exception_returns_500(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue.side_effect = Exception("DB error")
            response = client.get("/api/v1/queue")
        assert response.status_code == 500


class TestAddToQueue:

    def _post(self, client, body):
        return client.post("/api/v1/queue",
                           json=body,
                           content_type="application/json")

    def test_single_errata_returns_201(self, client):
        with patch(_QM_PATCH) as qm:
            qm.add_to_queue.return_value = _SAMPLE_ITEM
            response = self._post(client, {
                "errata_id": "USN-7412-2",
                "target_os": "ubuntu",
            })
        assert response.status_code == 201

    def test_missing_target_os_returns_400(self, client):
        response = self._post(client, {"errata_id": "USN-7412-2"})
        assert response.status_code == 400

    def test_invalid_target_os_returns_400(self, client):
        response = self._post(client, {
            "errata_id": "USN-7412-2", "target_os": "windows"
        })
        assert response.status_code == 400

    def test_missing_errata_id_returns_400(self, client):
        response = self._post(client, {"target_os": "ubuntu"})
        assert response.status_code == 400

    def test_errata_ids_with_int_values_returns_400(self, client):
        response = self._post(client, {
            "errata_ids": [123], "target_os": "ubuntu"
        })
        assert response.status_code == 400

    def test_errata_ids_with_empty_string_returns_400(self, client):
        response = self._post(client, {
            "errata_ids": [""], "target_os": "ubuntu"
        })
        assert response.status_code == 400

    def test_errata_ids_with_spaces_only_returns_400(self, client):
        response = self._post(client, {
            "errata_ids": ["   "], "target_os": "ubuntu"
        })
        assert response.status_code == 400

    def test_invalid_priority_override_returns_400(self, client):
        response = self._post(client, {
            "errata_id": "USN-7412-2",
            "target_os": "ubuntu",
            "priority_override": "abc",
        })
        assert response.status_code == 400

    def test_batch_errata_ids_returns_201(self, client):
        with patch(_QM_PATCH) as qm:
            qm.add_to_queue.return_value = _SAMPLE_ITEM
            response = self._post(client, {
                "errata_ids": ["USN-7412-2", "USN-9999-1"],
                "target_os": "ubuntu",
            })
        assert response.status_code in (201, 207)

    def test_all_fail_returns_422(self, client):
        with patch(_QM_PATCH) as qm:
            qm.add_to_queue.side_effect = ValueError("not found")
            response = self._post(client, {
                "errata_ids": ["USN-BAD-1"],
                "target_os": "ubuntu",
            })
        assert response.status_code == 422

    def test_rhel_target_os_accepted(self, client):
        with patch(_QM_PATCH) as qm:
            qm.add_to_queue.return_value = {**_SAMPLE_ITEM, "target_os": "rhel"}
            response = self._post(client, {
                "errata_id": "RHSA-2024:1234", "target_os": "rhel"
            })
        assert response.status_code == 201


class TestQueueStats:

    def test_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_stats.return_value = {"total": 5, "queued": 3}
            response = client.get("/api/v1/queue/stats")
        assert response.status_code == 200

    def test_returns_stats_from_manager(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_stats.return_value = {"total": 10, "queued": 7}
            data = client.get("/api/v1/queue/stats").get_json()
        assert data["total"] == 10

    def test_exception_returns_500(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_stats.side_effect = Exception("DB error")
            response = client.get("/api/v1/queue/stats")
        assert response.status_code == 500


class TestGetQueueItem:

    def test_found_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_item.return_value = _SAMPLE_ITEM
            response = client.get("/api/v1/queue/1")
        assert response.status_code == 200

    def test_not_found_returns_404(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_item.return_value = None
            response = client.get("/api/v1/queue/9999")
        assert response.status_code == 404

    def test_exception_returns_500(self, client):
        with patch(_QM_PATCH) as qm:
            qm.get_queue_item.side_effect = Exception("DB error")
            response = client.get("/api/v1/queue/1")
        assert response.status_code == 500


class TestUpdateQueueItem:

    def test_update_notes_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.update_queue_item.return_value = _SAMPLE_ITEM
            response = client.patch("/api/v1/queue/1",
                                    json={"notes": "reviewed"},
                                    content_type="application/json")
        assert response.status_code == 200

    def test_update_priority_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.update_queue_item.return_value = _SAMPLE_ITEM
            response = client.patch("/api/v1/queue/1",
                                    json={"priority_override": 5},
                                    content_type="application/json")
        assert response.status_code == 200

    def test_empty_body_returns_400(self, client):
        response = client.patch("/api/v1/queue/1",
                                json={},
                                content_type="application/json")
        assert response.status_code == 400

    def test_invalid_priority_returns_400(self, client):
        response = client.patch("/api/v1/queue/1",
                                json={"priority_override": "abc"},
                                content_type="application/json")
        assert response.status_code == 400

    def test_item_not_found_returns_404(self, client):
        with patch(_QM_PATCH) as qm:
            qm.update_queue_item.return_value = None
            response = client.patch("/api/v1/queue/9999",
                                    json={"notes": "x"},
                                    content_type="application/json")
        assert response.status_code == 404


class TestRemoveFromQueue:

    def test_removed_returns_200(self, client):
        with patch(_QM_PATCH) as qm:
            qm.remove_from_queue.return_value = True
            response = client.delete("/api/v1/queue/1")
        assert response.status_code == 200

    def test_not_removable_returns_404(self, client):
        with patch(_QM_PATCH) as qm:
            qm.remove_from_queue.return_value = False
            response = client.delete("/api/v1/queue/1")
        assert response.status_code == 404

    def test_exception_returns_500(self, client):
        with patch(_QM_PATCH) as qm:
            qm.remove_from_queue.side_effect = Exception("DB error")
            response = client.delete("/api/v1/queue/1")
        assert response.status_code == 500
