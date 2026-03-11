"""
Test - Notification Manager

notify_test_result() con mock get_db.
Best-effort: non propaga mai eccezioni.
"""

from unittest.mock import patch, MagicMock

from tests.conftest import make_mock_cursor, make_mock_db
from app.services.notification_manager import notify_test_result

_DB_PATCH = "app.services.notification_manager.get_db"

_BASE = dict(
    result="failed",
    errata_id="USN-7412-2",
    queue_id=1,
    test_id=10,
    system_name="test-ubuntu",
    failure_phase="services",
    failure_reason="ssh.socket is DOWN",
    duration_s=120,
)


class TestNotifyTestResult:

    def _call(self, **kwargs):
        args = {**_BASE, **kwargs}
        return notify_test_result(**args)

    # --- Routing per result ---

    def test_failed_writes_notification(self):
        cur = make_mock_cursor(fetchone_result={"id": 42})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed")
        cur.execute.assert_called()

    def test_error_writes_notification(self):
        cur = make_mock_cursor(fetchone_result={"id": 43})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="error")
        cur.execute.assert_called()

    def test_pending_approval_writes_notification(self):
        cur = make_mock_cursor(fetchone_result={"id": 44})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="pending_approval")
        cur.execute.assert_called()

    def test_passed_does_not_write(self):
        cur = make_mock_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="passed")
        cur.execute.assert_not_called()

    def test_aborted_does_not_write(self):
        cur = make_mock_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="aborted")
        cur.execute.assert_not_called()

    def test_unknown_result_does_not_write(self):
        cur = make_mock_cursor()
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="unknown_value")
        cur.execute.assert_not_called()

    # --- Contenuto SQL ---

    def test_failed_uses_test_failure_type(self):
        """notification_type deve essere 'test_failure' per result='failed'."""
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed")
        sql_args = cur.execute.call_args[0][1]
        assert "test_failure" in sql_args

    def test_pending_approval_uses_correct_type(self):
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="pending_approval")
        sql_args = cur.execute.call_args[0][1]
        assert "pending_approval" in sql_args

    def test_subject_contains_errata_id(self):
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed", errata_id="USN-9999-1")
        sql_args = cur.execute.call_args[0][1]
        assert any("USN-9999-1" in str(a) for a in sql_args)

    def test_body_contains_failure_reason(self):
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed", failure_reason="specific-reason-xyz")
        sql_args = cur.execute.call_args[0][1]
        assert any("specific-reason-xyz" in str(a) for a in sql_args)

    # --- Best-effort: nessuna eccezione ---

    def test_db_exception_does_not_propagate(self):
        """get_db solleva eccezione → notify non propaga."""
        with patch(_DB_PATCH, side_effect=Exception("DB down")):
            result = self._call(result="failed")
        assert result is None  # silenzioso

    def test_insert_error_does_not_propagate(self):
        cur = make_mock_cursor()
        cur.execute.side_effect = Exception("INSERT failed")
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            result = self._call(result="failed")
        assert result is None

    # --- Valori None nei parametri ---

    def test_none_failure_phase_does_not_crash(self):
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed", failure_phase=None)
        cur.execute.assert_called()

    def test_none_failure_reason_does_not_crash(self):
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            self._call(result="failed", failure_reason=None)
        cur.execute.assert_called()

    def test_returns_none_always(self):
        """notify_test_result è void."""
        cur = make_mock_cursor(fetchone_result={"id": 1})
        db = make_mock_db(cur)
        with patch(_DB_PATCH, return_value=db):
            result = self._call(result="failed")
        assert result is None
