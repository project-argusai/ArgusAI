"""Update-push outcome logging (#725).

Every update push logs one structured ``outcome``: sent, no_recipients,
not_delivered or error. Send-once is unchanged: the claim
(``update_pushed_at``) stays set and nothing is ever re-sent. Log fields
carry ids, counts, outcome and the exception class name only, never
recipient tokens, endpoints, device ids, notification text or exception text.
All ids and strings here are synthetic.
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.incident import Incident
from app.services import incident_notifications as inn
from app.services.push_notification_service import (
    NotificationResult,
    PushSendResults,
    classify_push_outcome,
)
from tests.test_services.test_incident_notifications import (
    SEND,
    TestUpdatePush,
    _incident,
)

SECRET_ENDPOINT = "https://push.example.invalid/endpoint/SECRET-TOKEN-123"
SECRET_ERROR = "boom-with-SECRET-TOKEN-123"
LATE_TEXT = "Late camera text."
LOG_NAME = "app.services.incident_notifications"


def _sub_result(success, sub_id="sub-SECRET-TOKEN-123"):
    return NotificationResult(subscription_id=sub_id, success=success,
                              error=None if success else SECRET_ERROR, status_code=None)


def _outcome_record(caplog):
    records = [r for r in caplog.records if r.name == LOG_NAME
               and getattr(r, "event_type", None) == "incident_update_push"]
    assert len(records) == 1, [r.getMessage() for r in caplog.records]
    return records[0]


def _assert_log_is_clean(caplog):
    blob = " ".join(
        f"{r.getMessage()} {sorted(r.__dict__.items(), key=lambda kv: kv[0])}"
        for r in caplog.records if r.name == LOG_NAME
    )
    for forbidden in ("SECRET", "TOKEN", "endpoint", SECRET_ENDPOINT, SECRET_ERROR, LATE_TEXT,
                      "Combined text.", "Per-camera text.", "First camera text."):
        assert forbidden not in blob, forbidden


async def _run(db_session, caplog, sender, status="done"):
    gid, members = await TestUpdatePush()._setup(db_session)
    inc = _incident(db_session, gid, members, status=status)
    caplog.set_level(logging.DEBUG, logger=LOG_NAME)
    caplog.clear()
    with patch(SEND, new=sender) as send:
        first = await inn.maybe_send_update_push(db_session, inc)
        second = await inn.maybe_send_update_push(db_session, inc)
    db_session.expire_all()
    return gid, first, second, send


def _assert_send_once(db_session, gid, second, send):
    assert second is False
    assert send.await_count == 1
    assert db_session.get(Incident, gid).update_pushed_at is not None


class TestUpdatePushOutcome:
    @pytest.mark.asyncio
    async def test_no_subscribers_is_no_recipients(self, db_session, caplog):
        gid, first, second, send = await _run(db_session, caplog, AsyncMock(return_value=[]))
        rec = _outcome_record(caplog)
        assert rec.outcome == "no_recipients" and first is False
        assert not hasattr(rec, "error_type")
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    async def test_swallowed_service_error_is_error_never_sent(self, db_session, caplog):
        swallowed = PushSendResults(error_type="OperationalError")
        gid, first, second, send = await _run(db_session, caplog, AsyncMock(return_value=swallowed))
        rec = _outcome_record(caplog)
        assert rec.outcome == "error" and rec.error_type == "OperationalError"
        assert first is False and rec.levelno == logging.WARNING
        assert "Incident update push outcome" == rec.getMessage()
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    async def test_all_failed_is_not_delivered(self, db_session, caplog):
        results = [_sub_result(False, "sub-a"), _sub_result(False, "sub-b")]
        gid, first, second, send = await _run(db_session, caplog, AsyncMock(return_value=results))
        rec = _outcome_record(caplog)
        assert rec.outcome == "not_delivered" and rec.results_count == 2 and first is False
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    async def test_sender_raises_is_error_with_type_only(self, db_session, caplog):
        sender = AsyncMock(side_effect=RuntimeError(SECRET_ERROR))
        gid, first, second, send = await _run(db_session, caplog, sender)
        rec = _outcome_record(caplog)
        assert rec.outcome == "error" and rec.error_type == "RuntimeError" and first is False
        assert rec.exc_info is None
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    async def test_none_result_is_no_recipients_not_sent(self, db_session, caplog):
        """Documented choice: None breaks the list contract and reports no
        delivery, so it is no_recipients (never sent) and is not retried."""
        gid, first, second, send = await _run(db_session, caplog, AsyncMock(return_value=None))
        rec = _outcome_record(caplog)
        assert rec.outcome == "no_recipients" and first is False
        assert not hasattr(rec, "results_count")
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_is_sent(self, db_session, caplog):
        results = [_sub_result(True, "sub-a"), _sub_result(False, "sub-b")]
        gid, first, second, send = await _run(db_session, caplog, AsyncMock(return_value=results))
        rec = _outcome_record(caplog)
        assert rec.outcome == "sent" and rec.results_count == 2 and first is True
        assert rec.levelno == logging.INFO
        _assert_send_once(db_session, gid, second, send)
        assert send.await_args.kwargs["description"] == "Combined text."
        _assert_log_is_clean(caplog)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["fallback", "failed"])
    async def test_fallback_and_failed_send_late_joiner_text_once(self, db_session, caplog, status):
        results = [_sub_result(True)]
        gid, first, second, send = await _run(
            db_session, caplog, AsyncMock(return_value=results), status=status)
        assert first is True and _outcome_record(caplog).outcome == "sent"
        assert send.await_args.kwargs["description"] == LATE_TEXT
        _assert_send_once(db_session, gid, second, send)
        _assert_log_is_clean(caplog)


class TestClassifyPushOutcome:
    def test_matrix(self):
        assert classify_push_outcome([]) == "no_recipients"
        assert classify_push_outcome(None) == "no_recipients"
        assert classify_push_outcome(PushSendResults(error_type="ValueError")) == "error"
        assert classify_push_outcome([_sub_result(False)]) == "not_delivered"
        assert classify_push_outcome([_sub_result(False), _sub_result(True)]) == "sent"
        assert classify_push_outcome(SimpleNamespace()) == "sent"  # opaque, no failure reported


class TestSendEventNotificationContract:
    """The service keeps returning a plain list; only an empty swallowed
    error is distinguishable."""

    @pytest.mark.asyncio
    async def test_no_subscribers_returns_plain_empty_list(self, db_session):
        from app.services.push_notification_service import send_event_notification
        results = await send_event_notification(
            event_id="evt-1", camera_name="Cam", description="desc", db=db_session)
        assert results == [] and isinstance(results, list)
        assert getattr(results, "error_type", None) is None
        assert classify_push_outcome(results) == "no_recipients"

    @pytest.mark.asyncio
    async def test_swallowed_internal_error_is_empty_list_with_error_type(self, db_session):
        from app.services import push_notification_service as pns
        with patch.object(pns, "format_rich_notification",
                          side_effect=ValueError("secret detail not for logs")):
            results = await pns.send_event_notification(
                event_id="evt-2", camera_name="Cam", description="desc", db=db_session)
        assert results == [] and isinstance(results, list)
        assert results.error_type == "ValueError"
        assert "secret detail" not in repr(results.error_type)
        assert classify_push_outcome(results) == "error"
