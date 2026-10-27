"""Push error logs carry the exception class name only (#728).

Push library errors can embed the subscription endpoint or tokens in their
message or traceback. Every error path in push_notification_service must log
``type(e).__name__`` only: no ``str(e)``, no ``exc_info``, no traceback.
Delivery behaviour and return values are unchanged. All values are synthetic.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pywebpush import WebPushException

from app.models.push_subscription import PushSubscription
from app.services import push_notification_service as pns
from app.utils.vapid import ensure_vapid_keys

FAKE_ENDPOINT = "https://push.example.invalid/wp/FAKE-ENDPOINT-abc123"
FAKE_TOKEN = "FAKE-TOKEN-zz9xq"
LEAKY_MESSAGE = f"delivery failed for {FAKE_ENDPOINT} auth={FAKE_TOKEN}"
LOGGER = pns.logger.name


class LeakyError(RuntimeError):
    pass


def _record_blob(record) -> str:
    parts = [str(record.msg), repr(record.args), record.getMessage()]
    if record.exc_info:
        import traceback
        parts.append("".join(traceback.format_exception(*record.exc_info)))
    if record.exc_text:
        parts.append(record.exc_text)
    if record.stack_info:
        parts.append(record.stack_info)
    parts.append(repr(sorted(vars(record).items(), key=lambda kv: kv[0])))
    return "\n".join(parts)


def _assert_clean(caplog, expected_class: str):
    records = [r for r in caplog.records if r.name == LOGGER]
    assert records, "expected push service log records"
    for r in records:
        assert r.exc_info is None, r.getMessage()
        blob = _record_blob(r)
        assert FAKE_ENDPOINT not in blob and FAKE_TOKEN not in blob, blob
        assert "FAKE-ENDPOINT" not in blob and "FAKE-TOKEN" not in blob
    assert any(expected_class in _record_blob(r) for r in records
               if r.levelno >= logging.WARNING), "class name must still be logged"


@pytest.fixture
def subscription(db_session):
    ensure_vapid_keys(db_session)
    sub = PushSubscription(endpoint=FAKE_ENDPOINT, p256dh_key="p256dh-synthetic",
                           auth_key="auth-synthetic")
    db_session.add(sub)
    db_session.commit()
    return sub


@pytest.fixture
def capture(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    return caplog


class TestSenderSwallowPath:
    @pytest.mark.asyncio
    async def test_swallowed_error_logs_class_only(self, db_session, capture):
        with patch.object(pns, "format_rich_notification", side_effect=LeakyError(LEAKY_MESSAGE)):
            results = await pns.send_event_notification(
                event_id="evt-synthetic", camera_name="Cam", description="desc", db=db_session)
        assert results == []  # return contract unchanged
        _assert_clean(capture, "LeakyError")


class TestBroadcastExceptionPaths:
    @pytest.mark.asyncio
    async def test_broadcast_event_gather_exception_logs_class_only(
            self, db_session, subscription, capture):
        service = pns.PushNotificationService(db_session)
        with patch.object(service, "_send_to_subscription",
                          new=AsyncMock(side_effect=LeakyError(LEAKY_MESSAGE))):
            results = await service.broadcast_event_notification(title="t", body="b")
        assert len(results) == 1 and results[0].success is False
        assert results[0].error == LEAKY_MESSAGE  # returned value unchanged
        _assert_clean(capture, "LeakyError")

    @pytest.mark.asyncio
    async def test_broadcast_notification_gather_exception_logs_class_only(
            self, db_session, subscription, capture):
        service = pns.PushNotificationService(db_session)
        with patch.object(service, "_send_to_subscription",
                          new=AsyncMock(side_effect=LeakyError(LEAKY_MESSAGE))):
            results = await service.broadcast_notification(title="t", body="b")
        assert len(results) == 1 and results[0].success is False
        _assert_clean(capture, "LeakyError")


class TestPerSubscriptionSend:
    @pytest.mark.asyncio
    @patch.object(pns.asyncio, "sleep", new_callable=AsyncMock)
    @patch.object(pns, "webpush")
    async def test_unexpected_error_logs_class_only(
            self, mock_webpush, _sleep, db_session, subscription, capture):
        mock_webpush.side_effect = LeakyError(LEAKY_MESSAGE)
        service = pns.PushNotificationService(db_session)
        result = await service.send_notification(subscription_id=subscription.id,
                                                 title="t", body="b")
        assert result.success is False and result.error == LEAKY_MESSAGE
        _assert_clean(capture, "LeakyError")

    @pytest.mark.asyncio
    @patch.object(pns.asyncio, "sleep", new_callable=AsyncMock)
    @patch.object(pns, "webpush")
    async def test_webpush_transient_error_logs_class_only(
            self, mock_webpush, _sleep, db_session, subscription, capture):
        response = MagicMock(status_code=503)
        mock_webpush.side_effect = WebPushException(LEAKY_MESSAGE, response=response)
        service = pns.PushNotificationService(db_session)
        result = await service.send_notification(subscription_id=subscription.id,
                                                 title="t", body="b")
        assert result.success is False and result.status_code == 503
        _assert_clean(capture, "WebPushException")


class TestPreferenceAndQuietHoursPaths:
    def test_preference_error_logs_class_only(self, capture):
        db = MagicMock()
        db.query.side_effect = LeakyError(LEAKY_MESSAGE)
        assert pns.should_send_notification(db, "sub-synthetic") == (True, True)
        _assert_clean(capture, "LeakyError")

    def test_quiet_hours_error_logs_class_only(self, capture):
        with patch.object(pns, "datetime") as dt:
            dt.now.side_effect = LeakyError(LEAKY_MESSAGE)
            assert pns.is_within_quiet_hours("22:00", "06:00", "UTC") is False
        _assert_clean(capture, "LeakyError")


FAKE_PERSON = "Zorblat Quenneville"   # synthetic, recognizable-looking name
FAKE_CAMERA = "Gazebo Cam Seven"


class TestTitleNeverLogged:
    @pytest.mark.asyncio
    @patch.object(pns, "webpush")
    async def test_title_with_name_and_camera_not_logged(
            self, mock_webpush, db_session, subscription, capture):
        mock_webpush.return_value = MagicMock()
        service = pns.PushNotificationService(db_session)
        title = f"{FAKE_PERSON} at {FAKE_CAMERA}"
        result = await service.send_notification(subscription_id=subscription.id,
                                                 title=title, body="b")
        assert result.success is True
        records = [r for r in capture.records if r.name == LOGGER]
        assert any(r.getMessage() == "Push notification sent successfully" for r in records)
        assert any(r.getMessage() == "_send_to_subscription starting" for r in records)
        for r in records:
            blob = _record_blob(r)
            assert FAKE_PERSON not in blob and FAKE_CAMERA not in blob, blob
            assert not hasattr(r, "title")


class TestEndpointHost:
    @pytest.mark.parametrize("endpoint,expected", [
        ("https://user:secret@push.example.invalid:8443/wp/FAKE-ENDPOINT-abc", "push.example.invalid"),
        ("https://push.example.invalid/wp/FAKE-ENDPOINT-abc", "push.example.invalid"),
        ("", "N/A"),
        (None, "N/A"),
        ("not a url FAKE-ENDPOINT-abc", "N/A"),
    ])
    def test_endpoint_host(self, endpoint, expected):
        assert pns._endpoint_host(endpoint) == expected

    @pytest.mark.asyncio
    @patch.object(pns, "webpush")
    async def test_debug_log_strips_userinfo_and_port(self, mock_webpush, db_session, capture):
        ensure_vapid_keys(db_session)
        sub = PushSubscription(
            endpoint="https://user:FAKE-TOKEN-zz9xq@push.example.invalid:8443/wp/FAKE-ENDPOINT-abc",
            p256dh_key="p256dh-synthetic", auth_key="auth-synthetic")
        db_session.add(sub)
        db_session.commit()
        mock_webpush.return_value = MagicMock()
        service = pns.PushNotificationService(db_session)
        await service.send_notification(subscription_id=sub.id, title="t", body="b")
        start = [r for r in capture.records if r.getMessage() == "_send_to_subscription starting"]
        assert start and start[0].endpoint_host == "push.example.invalid"
        for r in capture.records:
            blob = _record_blob(r)
            assert "FAKE-TOKEN" not in blob and "8443" not in blob and "FAKE-ENDPOINT" not in blob
