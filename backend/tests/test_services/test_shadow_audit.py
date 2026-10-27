"""#735 (#691 P1 S1): cloud-audit shadow tables, migration and retention.

``shadow_results``: one row per audited event with a frozen copy of the local
and cloud results, a source (``audit`` or ``fallback``) and the owner's
verdict. ``shadow_daily_summary``: numbers only. Paired text is kept 30 days,
summaries 365 days. Deleting an event removes its pair. The audit cap is
counted from shadow_results rows, so it survives a restart. Stored numbers go
through the numpy-safe helper (#708). Logs carry ids and counts only.
All data here is synthetic.
"""
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.models.camera import Camera
from app.models.event import Event
from app.models.shadow_result import ShadowDailySummary, ShadowResult
from app.services import shadow_audit_service as sas

NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
FAKE_NAME = "Quillon Brackenridge"
FAKE_PLATE = "ZZ9TEST"
FAKE_PATH = "data/thumbnails/2026-06-01/fake-frame.jpg"
LOCAL = {"description": f"{FAKE_NAME} parks car {FAKE_PLATE}", "confidence": np.int64(71),
         "objects": ["person", "vehicle"], "score": np.float32(0.25), "blank": np.bool_(False),
         "boxes": np.array([[1, 2, 3, 4]]), "thumbnail_path": FAKE_PATH}
CLOUD = {"description": "A person parks a car.", "confidence": np.int32(88),
         "objects": ["person", "vehicle"], "score": np.float64(0.5), "blank": np.bool_(False)}


def _uid():
    return str(uuid.uuid4())


def _event(db, when=NOW):
    cam = Camera(id=_uid(), name="Cam S1", type="rtsp", rtsp_url="rtsp://camera.example/s",
                 frame_rate=5, is_enabled=True)
    db.add(cam)
    ev = Event(id=_uid(), camera_id=cam.id, timestamp=when, description="Synthetic.",
               confidence=80, objects_detected='["person"]', alert_triggered=False,
               source_type="protect")
    db.add(ev)
    db.commit()
    return ev


def _pair(db, ev=None, created=NOW, source="audit"):
    ev = ev or _event(db)
    row = sas.record_shadow_result(db, event_id=ev.id, source=source, local_result=LOCAL,
                                   cloud_result=CLOUD, local_provider="local",
                                   cloud_provider="cloud", now=created)
    return ev, row


class TestShadowResultStorage:
    def test_round_trip_is_plain_json(self, db_session):
        _, row = _pair(db_session)
        db_session.expire_all()
        stored = db_session.get(ShadowResult, row.id)
        local = json.loads(stored.local_result)
        cloud = json.loads(stored.cloud_result)
        assert local["confidence"] == 71 and type(local["confidence"]) is int
        assert local["score"] == 0.25 and type(local["score"]) is float
        assert local["blank"] is False and local["boxes"] == [[1, 2, 3, 4]]
        assert cloud["confidence"] == 88 and cloud["score"] == 0.5
        assert stored.source == "audit" and stored.verdict is None

    def test_one_row_per_event(self, db_session):
        ev, first = _pair(db_session)
        _, second = _pair(db_session, ev=ev)
        assert second.id == first.id
        assert db_session.query(ShadowResult).count() == 1

    def test_source_is_validated(self, db_session):
        with pytest.raises(ValueError):
            _pair(db_session, source="other")

    @pytest.mark.parametrize("verdict", ["agree", "disagree", "unsure"])
    def test_verdict_set(self, db_session, verdict):
        ev, _ = _pair(db_session)
        row = sas.set_verdict(db_session, ev.id, verdict, now=NOW)
        assert row.verdict == verdict and row.verdict_at is not None

    @pytest.mark.parametrize("bad", ["local_better", "cloud_better", "same", "both_wrong",
                                     "Agree", "", "nonsense"])
    def test_verdict_rejects_other_values(self, db_session, bad):
        ev, _ = _pair(db_session)
        with pytest.raises(ValueError):
            sas.set_verdict(db_session, ev.id, bad)

    def test_verdict_values_match_api(self):
        from app.models.shadow_result import SHADOW_VERDICTS
        assert SHADOW_VERDICTS == ("agree", "disagree", "unsure")

    def test_verdict_missing_event(self, db_session):
        assert sas.set_verdict(db_session, "missing-event", "agree") is None


class TestDailySummary:
    def test_numbers_only_and_round_trip(self, db_session):
        metrics = {"pairs": np.int64(5), "agree_rate": np.float32(0.75),
                   "by_verdict": {"agree": np.int32(3)}, "hist": np.array([1, 2])}
        row = sas.upsert_daily_summary(db_session, date(2026, 6, 1), "audit", metrics)
        db_session.expire_all()
        loaded = json.loads(db_session.get(ShadowDailySummary, row.id).metrics)
        assert loaded == {"pairs": 5, "agree_rate": 0.75, "by_verdict": {"agree": 3},
                          "hist": [1, 2]}

    @pytest.mark.parametrize("bad", [{"note": "text"}, {"x": [1, "a"]}, {"d": {"n": FAKE_NAME}}])
    def test_rejects_text(self, db_session, bad):
        with pytest.raises(ValueError):
            sas.upsert_daily_summary(db_session, date(2026, 6, 1), "audit", bad)

    def test_upsert_replaces_same_day_and_source(self, db_session):
        sas.upsert_daily_summary(db_session, date(2026, 6, 1), "audit", {"pairs": 1})
        sas.upsert_daily_summary(db_session, date(2026, 6, 1), "audit", {"pairs": 2})
        sas.upsert_daily_summary(db_session, date(2026, 6, 1), "fallback", {"pairs": 9})
        rows = db_session.query(ShadowDailySummary).all()
        assert len(rows) == 2
        assert {json.loads(r.metrics)["pairs"] for r in rows} == {2, 9}


class TestEventDeleteCascade:
    def test_orm_delete_removes_pair(self, db_session):
        ev, _ = _pair(db_session)
        db_session.delete(db_session.get(Event, ev.id))
        db_session.commit()
        assert db_session.query(ShadowResult).count() == 0

    def test_cleanup_child_tables_include_shadow_results(self, db_session):
        from app.services.cleanup_service import _EVENT_CHILD_TABLES, CleanupService
        assert "shadow_results" in _EVENT_CHILD_TABLES
        ev, _ = _pair(db_session)
        keep, _ = _pair(db_session)
        svc = CleanupService(session_factory=lambda: db_session)
        counts = svc._delete_dependents_for_event_ids(db_session, [ev.id])
        db_session.commit()
        assert counts.get("shadow_results") == 1
        assert [r.event_id for r in db_session.query(ShadowResult).all()] == [keep.id]


class TestRetention:
    def test_pairs_30_days_summaries_365_days(self, db_session):
        _, old_pair = _pair(db_session, created=NOW - timedelta(days=31))
        _, edge_pair = _pair(db_session, created=NOW - timedelta(days=29, hours=23))
        _, new_pair = _pair(db_session, created=NOW)
        sas.upsert_daily_summary(db_session, (NOW - timedelta(days=366)).date(), "audit", {"p": 1})
        sas.upsert_daily_summary(db_session, (NOW - timedelta(days=364)).date(), "audit", {"p": 2})
        sas.upsert_daily_summary(db_session, (NOW - timedelta(days=31)).date(), "audit", {"p": 3})
        events_before = db_session.query(Event).count()

        result = sas.purge_expired(db_session, now=NOW)

        assert result == {"shadow_results_redacted": 1, "shadow_results_deleted": 0,
                          "shadow_summaries_deleted": 1}
        rows = {r.id: r for r in db_session.query(ShadowResult).all()}
        assert set(rows) == {old_pair.id, edge_pair.id, new_pair.id}
        assert rows[old_pair.id].local_result is None and rows[old_pair.id].cloud_result is None
        assert rows[edge_pair.id].local_result is not None
        days = sorted(json.loads(r.metrics)["p"] for r in db_session.query(ShadowDailySummary))
        assert days == [2, 3]  # a 31-day-old summary is kept (365-day window)
        assert db_session.query(Event).count() == events_before  # events untouched

    def test_defaults(self):
        assert sas.PAIR_RETENTION_DAYS == 30 and sas.SUMMARY_RETENTION_DAYS == 365

    @pytest.mark.asyncio
    async def test_scheduled_job_runs_and_logs_counts_only(self, db_session, monkeypatch, caplog):
        from app.services import retention_jobs
        _pair(db_session, created=datetime.now(timezone.utc) - timedelta(days=40))
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        caplog.set_level(logging.DEBUG)
        await retention_jobs.scheduled_shadow_retention_job()
        assert db_session.query(ShadowResult).one().local_result is None
        rec = [r for r in caplog.records if getattr(r, "event_type", None) == "shadow_retention"]
        assert rec and rec[0].shadow_results_redacted == 1

    def test_job_registered(self):
        from app.services.retention_jobs import register_retention_jobs

        class Sched:
            def __init__(self):
                self.ids = []

            def add_job(self, fn, **kw):
                self.ids.append(kw["id"])

        s = Sched()
        register_retention_jobs(s)
        assert "daily_shadow_retention" in s.ids


class TestAuditCap:
    def test_count_comes_from_rows_and_survives_restart(self, tmp_path):
        from app.core.database import Base
        url = f"sqlite:///{tmp_path / 'cap.db'}"
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        s1 = sessionmaker(bind=engine)()
        for _ in range(3):
            _pair(s1, created=NOW - timedelta(hours=1))
        _pair(s1, created=NOW - timedelta(hours=1), source="fallback")
        _pair(s1, created=NOW - timedelta(days=2))
        s1.close()
        engine.dispose()  # "restart"

        engine2 = create_engine(url)
        s2 = sessionmaker(bind=engine2)()
        since = NOW - timedelta(days=1)
        assert sas.count_audits_since(s2, since) == 3
        assert sas.count_audits_since(s2, since, source="fallback") == 1
        s2.close()
        engine2.dispose()


class TestLogsCarryNoText:
    def test_no_descriptions_paths_names_or_plates(self, db_session, caplog):
        caplog.set_level(logging.DEBUG)
        ev, _ = _pair(db_session, created=NOW - timedelta(days=40))
        sas.set_verdict(db_session, ev.id, "agree")
        sas.purge_expired(db_session, now=NOW)
        for r in caplog.records:
            blob = f"{r.getMessage()} {r.args!r} {sorted(vars(r).items(), key=lambda kv: kv[0])!r}"
            for bad in (FAKE_NAME, FAKE_PLATE, FAKE_PATH, "parks car", "A person parks"):
                assert bad not in blob, (bad, r.getMessage())


class TestMigration:
    def test_up_down_up(self, tmp_path):
        backend = Path(__file__).resolve().parents[2]
        env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'mig.db'}"}

        def alembic(*args):
            subprocess.run([sys.executable, "-m", "alembic", *args], cwd=backend, env=env,
                           check=True, capture_output=True)

        def tables():
            eng = create_engine(env["DATABASE_URL"])
            names = set(inspect(eng).get_table_names())
            eng.dispose()
            return names

        alembic("upgrade", "head")
        assert {"shadow_results", "shadow_daily_summary"} <= tables()
        alembic("downgrade", "-1")
        assert not ({"shadow_results", "shadow_daily_summary"} & tables())
        alembic("upgrade", "head")
        assert {"shadow_results", "shadow_daily_summary"} <= tables()


class TestGracieReview:
    """Gracie's #742 review (M1, M2, L1) and Terry's verdict-after-summary case."""

    def test_json_safe_maps_non_finite_to_none(self):
        from app.utils.json_safe import json_safe
        out = json_safe({"a": float("nan"), "b": np.float32("inf"), "c": [float("-inf"), 1.5],
                         "d": np.array([np.nan, 2.0]), "e": np.float64(0.5)})
        assert out == {"a": None, "b": None, "c": [None, 1.5], "d": [None, 2.0], "e": 0.5}

    def test_pair_with_nan_round_trips_as_strict_json(self, db_session):
        ev = _event(db_session)
        row = sas.record_shadow_result(db_session, event_id=ev.id, source="audit",
                                       local_result={"score": float("nan")},
                                       cloud_result={"score": np.float32("inf")})
        assert "NaN" not in row.local_result and "Infinity" not in row.cloud_result
        assert json.loads(row.local_result) == {"score": None}

    def test_summary_with_nan_is_strict_json(self, db_session):
        row = sas.upsert_daily_summary(db_session, date(2026, 6, 1), "audit",
                                       {"rate": float("nan"), "n": 1})
        assert json.loads(row.metrics) == {"rate": None, "n": 1}
        assert "NaN" not in row.metrics

    def test_30_day_purge_redacts_text_keeps_row_and_verdict(self, db_session):
        ev, row = _pair(db_session, created=NOW - timedelta(days=31))
        sas.set_verdict(db_session, ev.id, "disagree", now=NOW - timedelta(days=30, hours=12))
        result = sas.purge_expired(db_session, now=NOW)
        db_session.expire_all()
        kept = db_session.get(ShadowResult, row.id)
        assert kept is not None
        assert kept.local_result is None and kept.cloud_result is None
        assert kept.verdict == "disagree" and kept.source == "audit"
        assert kept.verdict_at is not None and kept.created_at is not None
        assert result["shadow_results_redacted"] == 1 and result["shadow_results_deleted"] == 0

    def test_rows_deleted_after_365_days(self, db_session):
        _, old = _pair(db_session, created=NOW - timedelta(days=366))
        _, mid = _pair(db_session, created=NOW - timedelta(days=200))
        result = sas.purge_expired(db_session, now=NOW)
        ids = {r.id for r in db_session.query(ShadowResult).all()}
        assert ids == {mid.id}
        assert result["shadow_results_deleted"] == 1

    def test_redaction_is_idempotent(self, db_session):
        _pair(db_session, created=NOW - timedelta(days=40))
        assert sas.purge_expired(db_session, now=NOW)["shadow_results_redacted"] == 1
        assert sas.purge_expired(db_session, now=NOW)["shadow_results_redacted"] == 0

    @pytest.mark.parametrize("column,value", [("source", "other"), ("verdict", "same")])
    def test_check_constraints(self, db_session, column, value):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        ev, row = _pair(db_session)
        with pytest.raises(IntegrityError):
            db_session.execute(text(f"UPDATE shadow_results SET {column} = :v WHERE id = :id"),
                               {"v": value, "id": row.id})
            db_session.commit()
        db_session.rollback()

    def test_verdict_after_summary_counts_in_later_summary(self, db_session):
        day1 = NOW
        ev, _ = _pair(db_session, created=day1)
        d1 = day1.astimezone().date()
        assert json.loads(sas.recompute_daily_summary(db_session, d1, "audit").metrics)["verdicts_agree"] == 0
        sas.set_verdict(db_session, ev.id, "agree", now=NOW + timedelta(days=1))  # after day 1's run
        # A later recompute of the pair's day picks it up.
        assert json.loads(sas.recompute_daily_summary(db_session, d1, "audit").metrics)["verdicts_agree"] == 1

    def test_changed_verdict_counted_once_as_final_value(self, db_session):
        ev, _ = _pair(db_session, created=NOW)
        sas.set_verdict(db_session, ev.id, "agree", now=NOW + timedelta(days=1))
        days = [(NOW + timedelta(days=k)).astimezone().date() for k in range(4)]
        for d in days[:2]:
            sas.recompute_daily_summary(db_session, d, "audit")
        sas.set_verdict(db_session, ev.id, "disagree", now=NOW + timedelta(days=3))
        # Job-style: only the pair's day and the change day are recomputed;
        # day 1's stored summary is left as it was.
        sas.recompute_daily_summary(db_session, days[0], "audit")
        sas.recompute_daily_summary(db_session, days[3], "audit")
        totals = {"agree": 0, "disagree": 0, "unsure": 0}
        for row in db_session.query(ShadowDailySummary).filter(ShadowDailySummary.source == "audit"):
            m = json.loads(row.metrics)
            for v in totals:
                totals[v] += m.get(f"verdicts_{v}", 0)
        assert totals == {"agree": 0, "disagree": 1, "unsure": 0}

    def test_recompute_keeps_other_metrics(self, db_session):
        d = NOW.astimezone().date()
        sas.upsert_daily_summary(db_session, d, "audit", {"pairs": 3, "sum_objects_jaccard": 2.5})
        _pair(db_session, created=NOW)
        m = json.loads(sas.recompute_daily_summary(db_session, d, "audit").metrics)
        assert m["pairs"] == 3 and m["sum_objects_jaccard"] == 2.5
        assert m["pairs_recorded"] == 1
        assert {"verdicts_agree", "verdicts_disagree", "verdicts_unsure"} <= set(m)

    def test_recompute_works_after_redaction(self, db_session):
        ev, _ = _pair(db_session, created=NOW - timedelta(days=40))
        sas.set_verdict(db_session, ev.id, "unsure", now=NOW - timedelta(days=39))
        sas.purge_expired(db_session, now=NOW)
        d = (NOW - timedelta(days=40)).astimezone().date()
        assert json.loads(sas.recompute_daily_summary(db_session, d, "audit").metrics)["verdicts_unsure"] == 1

    @pytest.mark.asyncio
    async def test_job_recomputes_last_30_days(self, db_session, monkeypatch):
        from app.services import retention_jobs
        ev, _ = _pair(db_session, created=datetime.now(timezone.utc) - timedelta(days=20))
        sas.set_verdict(db_session, ev.id, "agree")
        monkeypatch.setattr("app.core.database.SessionLocal", lambda: db_session)
        monkeypatch.setattr(db_session, "close", lambda: None)
        await retention_jobs.scheduled_shadow_retention_job()
        day = (datetime.now(timezone.utc) - timedelta(days=20)).astimezone().date()
        row = (db_session.query(ShadowDailySummary)
               .filter(ShadowDailySummary.day == day, ShadowDailySummary.source == "audit").one())
        assert json.loads(row.metrics)["verdicts_agree"] == 1
