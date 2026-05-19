"""
AI Processing Coordinator

Orchestrates the processing of a single event through the AI pipeline.

Extracted from EventProcessor as part of Phase B (#443) to further
reduce the size and responsibility of the main EventProcessor class.

This coordinator owns the high-level flow:
- Cost cap checks
- Context / embedding generation
- AI description generation
- Storage
- Post-processing (alerts, notifications, entity updates, etc.)

Individual steps are still delegated to focused helper methods (many of which
remain on EventProcessor during the transition).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Optional, TYPE_CHECKING, Callable, Awaitable, Any, Dict, List

import numpy as np

from app.core.database import SessionLocal

if TYPE_CHECKING:
    from app.services.ai_service import AIService
    from app.services.event_processor import ProcessingEvent, Event
    from app.services.metrics import ProcessingMetrics

logger = logging.getLogger(__name__)


class AIProcessingCoordinator:
    """
    Coordinates the end-to-end processing of one queued event.

    The goal is to eventually own the entire `_process_event` flow
    so that EventProcessor only needs to:
    - Manage the queue
    - Manage the worker pool
    - Own high-level lifecycle
    """

    def __init__(
        self,
        ai_service: "AIService",
        metrics: "ProcessingMetrics",
        context_prompt_service: Any,
        cost_alert_service: Any,
        embedding_service: Any,
        mqtt_service: Any,
        homekit_service: Any = None,
        face_embedding_service: Any = None,
        vehicle_embedding_service: Any = None,
        entity_service: Any = None,
        ai_semaphore: Optional[asyncio.Semaphore] = None,
    ):
        self.ai_service = ai_service
        self.metrics = metrics
        self.context_prompt_service = context_prompt_service
        self.cost_alert_service = cost_alert_service
        self.embedding_service = embedding_service
        self.mqtt_service = mqtt_service
        self.homekit_service = homekit_service
        self.face_embedding_service = face_embedding_service
        self.vehicle_embedding_service = vehicle_embedding_service
        self.entity_service = entity_service
        self.ai_semaphore = ai_semaphore or asyncio.Semaphore(8)

        # Lightweight in-memory counters for the debug/stats endpoint
        self._total_processed = 0
        self._success_count = 0
        self._fallback_count = 0
        self._context_used_count = 0
        self._ocr_used_count = 0
        self._low_confidence_count = 0
        self._regenerated_count = 0

        # Ring buffer for recent activity
        self._recent_activity: deque[Dict] = deque(maxlen=50)

        # Hot cameras / top entities caches
        self._camera_activity: Dict[str, Dict] = {}
        self._entity_activity: Dict[str, Dict] = {}

        # Dirty sets for periodic persistence (to avoid DB write on every event)
        self._dirty_cameras: set = set()
        self._dirty_entities: set = set()

        # Load persisted hot activity (if tables exist)
        self._load_activity_caches()

        # Pub/sub for live streaming
        self._event_subscribers: List[asyncio.Queue] = []

    def get_processing_stats(self) -> dict:
        """Return current lightweight runtime stats for observability and debugging.

        This is intended for the /system/debug/ai-processing-stats endpoint
        and internal monitoring. Prometheus metrics remain the primary source
        for long-term observability.
        """
        total = self._total_processed
        success_rate = round(self._success_count / max(total, 1), 4)

        return {
            "total_processed": total,
            "success_count": self._success_count,
            "success_rate": success_rate,
            "fallback_count": self._fallback_count,
            "context_used_count": self._context_used_count,
            "ocr_used_count": self._ocr_used_count,
            "low_confidence_count": self._low_confidence_count,
            "regenerated_count": self._regenerated_count,
            "current_in_flight": self.ai_semaphore._value if hasattr(self.ai_semaphore, "_value") else None,
        }

    def get_recent_activity(self, limit: int = 20) -> List[Dict]:
        """Return the most recent processing events (ring buffer) with rich coordinator-owned fields.

        === 2026 Data Audit (for AI Cost & Token Trends surface) ===

        The following economics/usage fields are reliably populated on **successful** processing:

        Core trend fields (best for cost/token analysis):
        - provider (ai_result.provider)
        - ai_cost (ai_result.cost_estimate)
        - tokens_used (ai_result.tokens_used)
        - ai_response_time_ms (ai_result.response_time_ms)
        - prompt_variant (ai_result.prompt_variant)
        - ocr_used (ai_result.ocr_used)
        - ai_fallback_used (ai_result.ai_fallback_used)
        - ai_confidence (ai_result.ai_confidence)
        - low_confidence, vague_reason, regenerated

        Supporting fields:
        - context_used + context_stats
        - post_processing_summary (rich JSON)
        - entity_early / entity_final details

        Gaps / Limitations:
        - Cost-cap skips (analysis_skipped=True): No AI call occurred → no cost/tokens/provider data. Only has analysis_skipped_reason.
        - General failures: Very minimal (only error message + regenerated flag).
        - post_processing_summary exists in recent_item and on the Event row (after storage), but is not part of the initial event_data dict.
        - All cost/token fields are NULL on legacy events (pre-extraction) and on skipped/failure rows.

        For time-series cost/token trends, the best data source is successful Event rows filtered by timestamp + provider.
        The recent ring buffer is useful for live views but too small (maxlen=50) for long-term trends.

        ========================================================
        """

        # === 2026 Context Usage Audit (for new "Context Usage Patterns" surface) ===
        #
        # Fields captured today:
        #
        # On the Event table (persisted):
        #   - context_included (Boolean, NOT NULL, default=False)
        #   - context_stats (Text/JSON, nullable)
        #     Stored shape: {
        #       "entity_context_included": bool,
        #       "similar_events_count": int,
        #       "time_pattern_included": bool,
        #       "context_gather_time_ms": float
        #     }
        #
        # In the recent activity ring buffer (in-memory):
        #   - "context_used": bool
        #   - "context_stats": the object above (not serialized)
        #
        # Additional signals available at processing time (but not all persisted):
        #   - context_result.entity_context_included
        #   - context_result.similar_events_count
        #   - context_result.time_pattern_included
        #   - context_result.context_gather_time_ms
        #   - context_result.mcp_context_included / mcp_feedback_included / etc.  (MCP integration)
        #
        # What is reliably populated on success paths:
        #   - context_included is correctly set based on whether the final prompt used context.
        #   - The four main context_stats fields above are captured.
        #
        # Gaps / Limitations:
        #   - MCP context fields (mcp_*) are computed by ContextEnhancedPromptService but are **not** stored
        #     in the Event row or recent_item.
        #   - No historical breakdown of *which* context components were used across many events.
        #   - context_stats is only populated on successful processing paths (not on cost-cap skips).
        #   - No aggregated views or trend endpoints exist yet for context usage over time.
        #   - The recent ring buffer only holds ~50 events — insufficient for long-term pattern analysis.
        #
        # Best data for future context usage trends:
        #   - Query the `events` table on `context_included` + parsed `context_stats`.
        #   - The `_context_used_count` counter in the coordinator only gives a global total, not time-series.
        #
        # ============================================================
        return list(self._recent_activity)[-limit:]

    def get_ai_cost_trends(
        self,
        days_back: int = 30,
        bucket: str = "day",   # "day" or "hour"
    ) -> List[Dict]:
        """
        Returns aggregated AI cost & token usage trends.

        This is the first small method for the new "AI Cost & Token Trends"
        surface. It pulls from the events table (where the rich economics
        fields live after the extraction).

        Args:
            days_back: How many days of history to include (default 30)
            bucket: Time granularity - "day" or "hour"

        Returns:
            List of dicts sorted by bucket (oldest first):
            [
                {
                    "bucket": "2026-05-01" or "2026-05-01 14:00",
                    "calls": 87,
                    "total_cost": 0.412,
                    "total_tokens": 78200,
                    "avg_response_time_ms": 1240,
                },
                ...
            ]
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import func
        from app.core.database import get_db_session
        from app.models.event import Event as DBEvent

        if bucket not in ("day", "hour"):
            bucket = "day"

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        with get_db_session() as db:
            # Base query for events that actually had AI economics data
            query = (
                db.query(DBEvent)
                .filter(DBEvent.timestamp >= start)
                .filter(DBEvent.timestamp <= end)
                .filter(DBEvent.ai_cost.isnot(None))
            )

            if bucket == "day":
                # Group by date
                rows = (
                    query.with_entities(
                        func.date(DBEvent.timestamp).label("bucket"),
                        func.count(DBEvent.id).label("calls"),
                        func.sum(DBEvent.ai_cost).label("total_cost"),
                        func.sum(DBEvent.tokens_used).label("total_tokens"),
                        func.avg(DBEvent.ai_response_time_ms).label("avg_response_time_ms"),
                    )
                    .group_by(func.date(DBEvent.timestamp))
                    .order_by(func.date(DBEvent.timestamp))
                    .all()
                )
            else:
                # Group by hour (YYYY-MM-DD HH:00)
                rows = (
                    query.with_entities(
                        func.strftime("%Y-%m-%d %H:00", DBEvent.timestamp).label("bucket"),
                        func.count(DBEvent.id).label("calls"),
                        func.sum(DBEvent.ai_cost).label("total_cost"),
                        func.sum(DBEvent.tokens_used).label("total_tokens"),
                        func.avg(DBEvent.ai_response_time_ms).label("avg_response_time_ms"),
                    )
                    .group_by(func.strftime("%Y-%m-%d %H:00", DBEvent.timestamp))
                    .order_by(func.strftime("%Y-%m-%d %H:00", DBEvent.timestamp))
                    .all()
                )

            result = []
            for row in rows:
                result.append({
                    "bucket": str(row.bucket),
                    "calls": int(row.calls or 0),
                    "total_cost": round(float(row.total_cost or 0), 6),
                    "total_tokens": int(row.total_tokens or 0),
                    "avg_response_time_ms": round(float(row.avg_response_time_ms or 0), 1) if row.avg_response_time_ms else None,
                })

            return result

    def get_context_usage_stats(self, days_back: int = 30) -> Dict:
        """Return basic aggregates about how often and how effectively context was used.

        This is the first small method for the "Context Usage Patterns" surface.
        """
        from datetime import datetime, timedelta, timezone
        from app.core.database import get_db_session
        from app.models.event import Event as DBEvent
        import json

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        with get_db_session() as db:
            base = db.query(DBEvent).filter(
                DBEvent.timestamp >= start,
                DBEvent.timestamp <= end
            )

            total = base.count()
            context_used = base.filter(DBEvent.context_included == True).count()

            # Fetch context_stats only for events that used context (to compute breakdown + avg time)
            stats_rows = (
                base.filter(DBEvent.context_included == True)
                .with_entities(DBEvent.context_stats)
                .all()
            )

            entity_ctx = 0
            similar = 0
            time_pat = 0
            gather_times = []

            for (ctx_json,) in stats_rows:
                if not ctx_json:
                    continue
                try:
                    data = json.loads(ctx_json)
                    if data.get("entity_context_included"):
                        entity_ctx += 1
                    if data.get("similar_events_count", 0) > 0:
                        similar += 1
                    if data.get("time_pattern_included"):
                        time_pat += 1
                    gt = data.get("context_gather_time_ms")
                    if isinstance(gt, (int, float)):
                        gather_times.append(gt)
                except Exception:
                    continue

            avg_gather = round(sum(gather_times) / len(gather_times), 2) if gather_times else None

            return {
                "period_days": days_back,
                "total_events": total,
                "context_used_count": context_used,
                "context_used_percent": round((context_used / total * 100), 2) if total > 0 else 0.0,
                "avg_gather_time_ms": avg_gather,
                "context_breakdown": {
                    "entity_context": entity_ctx,
                    "similar_events": similar,
                    "time_pattern": time_pat,
                },
            }

    # ------------------------------------------------------------------
    # Hot cameras / Top entities cache (for dashboard widgets)
    # ------------------------------------------------------------------

    def _update_activity_caches(self, record: Dict) -> None:
        """Update the in-memory hot cameras and top entities caches (and persist)."""
        if not record.get("success"):
            return

        now = record.get("timestamp", time.time())
        camera_id = record.get("camera_id")

        # Hot cameras
        if camera_id:
            if camera_id not in self._camera_activity:
                self._camera_activity[camera_id] = {"count": 0, "last_seen": 0}
            self._camera_activity[camera_id]["count"] += 1
            self._camera_activity[camera_id]["last_seen"] = now

        # Top recent entities (prefer final link, fall back to early)
        entity_info = record.get("entity_final") or record.get("entity_early") or {}
        entity_id = entity_info.get("entity_id") or entity_info.get("id")

        if entity_id:
            if entity_id not in self._entity_activity:
                self._entity_activity[entity_id] = {
                    "count": 0,
                    "last_seen": 0,
                    "name": entity_info.get("entity_name") or entity_info.get("name"),
                    "type": entity_info.get("entity_type") or entity_info.get("type"),
                }
            self._entity_activity[entity_id]["count"] += 1
            self._entity_activity[entity_id]["last_seen"] = now
            # Keep latest name/type if available
            if entity_info.get("entity_name") or entity_info.get("name"):
                self._entity_activity[entity_id]["name"] = entity_info.get("entity_name") or entity_info.get("name")
            if entity_info.get("entity_type") or entity_info.get("type"):
                self._entity_activity[entity_id]["type"] = entity_info.get("entity_type") or entity_info.get("type")

        # Mark as dirty for periodic flush (much more efficient than per-event writes)
        if camera_id:
            self._dirty_cameras.add(camera_id)
        if entity_id:
            self._dirty_entities.add(entity_id)

    def get_hot_cameras(self, limit: int = 10) -> List[Dict]:
        """Return the hottest cameras based on recent activity (exponential time decay)."""
        if not self._camera_activity:
            return []

        now = time.time()
        half_life = 2 * 3600  # 2 hours half-life (tunable)
        scored = []
        for cam_id, data in self._camera_activity.items():
            age = max(now - data["last_seen"], 1)
            decay = 2 ** (-age / half_life)
            score = data["count"] * decay
            scored.append({
                "camera_id": cam_id,
                "count": data["count"],
                "last_seen": data["last_seen"],
                "score": round(score, 2)
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def get_top_recent_entities(self, limit: int = 10) -> List[Dict]:
        """Return the most active entities based on recent activity (exponential time decay)."""
        if not self._entity_activity:
            return []

        now = time.time()
        half_life = 2 * 3600  # 2 hours half-life
        scored = []
        for ent_id, data in self._entity_activity.items():
            age = max(now - data["last_seen"], 1)
            decay = 2 ** (-age / half_life)
            score = data["count"] * decay
            scored.append({
                "entity_id": ent_id,
                "name": data.get("name"),
                "type": data.get("type"),
                "count": data["count"],
                "last_seen": data["last_seen"],
                "score": round(score, 2)
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _load_activity_caches(self) -> None:
        """Load hot camera and entity activity from the database (best effort)."""
        try:
            from app.models.hot_activity import HotCameraActivity, HotEntityActivity

            with SessionLocal() as db:
                for row in db.query(HotCameraActivity).all():
                    self._camera_activity[row.camera_id] = {
                        "count": row.count,
                        "last_seen": row.last_seen,
                    }

                for row in db.query(HotEntityActivity).all():
                    self._entity_activity[row.entity_id] = {
                        "count": row.count,
                        "last_seen": row.last_seen,
                        "name": row.name,
                        "type": row.type,
                    }
        except Exception:
            # Tables may not exist yet (migration pending) or other transient error
            logger.debug("Could not load persisted hot activity caches yet.")

    def flush_hot_activity(self) -> None:
        """Public method to flush any dirty hot activity to the database.
        Called on shutdown and by the periodic APScheduler job.
        """
        self._flush_dirty_activity_caches()

    def _flush_dirty_activity_caches(self) -> None:
        """Flush only the dirty entries to the database (called periodically by APScheduler)."""
        if not self._dirty_cameras and not self._dirty_entities:
            return

        try:
            from app.models.hot_activity import HotCameraActivity, HotEntityActivity

            with SessionLocal() as db:
                for cam_id in list(self._dirty_cameras):
                    if cam_id in self._camera_activity:
                        data = self._camera_activity[cam_id]
                        db.merge(HotCameraActivity(
                            camera_id=cam_id,
                            count=data["count"],
                            last_seen=data["last_seen"],
                        ))
                self._dirty_cameras.clear()

                for ent_id in list(self._dirty_entities):
                    if ent_id in self._entity_activity:
                        data = self._entity_activity[ent_id]
                        db.merge(HotEntityActivity(
                            entity_id=ent_id,
                            name=data.get("name"),
                            type=data.get("type"),
                            count=data["count"],
                            last_seen=data["last_seen"],
                        ))
                self._dirty_entities.clear()

                db.commit()
        except Exception as e:
            logger.warning(f"Failed to flush hot activity caches: {e}")

    def register_hot_activity_flush_job(self, scheduler) -> None:
        """Register a periodic job to flush dirty hot activity caches (call once at startup).

        The flush interval is read from the SystemSetting 'hot_activity_flush_interval_seconds'
        (default: 45). This allows operators to tune write pressure vs. durability.
        """
        from apscheduler.triggers.interval import IntervalTrigger
        from app.core.database import get_db_session
        from app.models.system_setting import SystemSetting

        interval_seconds = self._read_flush_interval()
        self._current_flush_interval = interval_seconds

        scheduler.add_job(
            self._flush_dirty_activity_caches,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id="hot_activity_flush",
            name="Flush dirty hot camera/entity activity to DB",
            replace_existing=True,
        )
        logger.info(f"Registered periodic hot activity flush job (every {interval_seconds}s)")

    def reconfigure_hot_activity_flush(self, scheduler) -> None:
        """Check the current SystemSetting and re-schedule the flush job if the interval changed.

        Intended to be called periodically (e.g. every minute) so operators can change the
        setting without restarting the application.
        """
        from apscheduler.triggers.interval import IntervalTrigger
        from app.core.database import get_db_session
        from app.models.system_setting import SystemSetting

        new_interval = self._read_flush_interval()

        if new_interval == getattr(self, "_current_flush_interval", None):
            return  # No change

        logger.info(
            f"Hot activity flush interval changed from {getattr(self, '_current_flush_interval', 'unknown')}s "
            f"to {new_interval}s — rescheduling job"
        )

        # Remove existing job (if present)
        try:
            scheduler.remove_job("hot_activity_flush")
        except Exception:
            pass  # Job may not exist yet or already removed

        # Re-register with new interval
        scheduler.add_job(
            self._flush_dirty_activity_caches,
            trigger=IntervalTrigger(seconds=new_interval),
            id="hot_activity_flush",
            name="Flush dirty hot camera/entity activity to DB",
            replace_existing=True,
        )

        self._current_flush_interval = new_interval

    def _read_flush_interval(self) -> int:
        """Read the current flush interval from SystemSetting (with safe default)."""
        from app.core.database import get_db_session
        from app.models.system_setting import SystemSetting

        interval_seconds = 45
        try:
            with get_db_session() as db:
                setting = db.query(SystemSetting).filter(
                    SystemSetting.key == "hot_activity_flush_interval_seconds"
                ).first()
                if setting and setting.value:
                    interval_seconds = max(10, int(setting.value))
        except Exception:
            pass
        return interval_seconds

    # ------------------------------------------------------------------
    # Hot list push support for WebSocket clients
    # ------------------------------------------------------------------

    def _publish_hot_update(self) -> None:
        """Push current hot cameras and top entities to all WebSocket subscribers."""
        if not self._event_subscribers:
            return

        hot_update = {
            "type": "hot_update",
            "hot_cameras": self.get_hot_cameras(limit=10),
            "top_recent_entities": self.get_top_recent_entities(limit=10),
            "timestamp": time.time(),
        }

        for queue in self._event_subscribers[:]:
            try:
                queue.put_nowait(hot_update)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(hot_update)
                except Exception:
                    pass
            except Exception:
                try:
                    self._event_subscribers.remove(queue)
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    # WebSocket / bidirectional streaming support
    # ------------------------------------------------------------------

    async def subscribe_to_new_events_ws(self) -> asyncio.Queue:
        """Subscribe for WebSocket clients.

        Same underlying mechanism as the SSE stream, but returned as a queue
        so the WebSocket handler can apply client-specific filtering.
        """
        return await self.subscribe_to_new_events()

    async def subscribe_to_new_events(self) -> asyncio.Queue:
        """Subscribe to newly processed events (for SSE / live feed).

        Returns an asyncio.Queue that will receive rich event records as they
        are processed by this coordinator.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._event_subscribers.append(queue)
        return queue

    def _publish_new_event(self, record: Dict) -> None:
        """Publish a processed event record to all current subscribers."""
        for queue in self._event_subscribers[:]:  # copy to avoid mutation during iteration
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                # Drop the oldest item if the subscriber is slow
                try:
                    queue.get_nowait()
                    queue.put_nowait(record)
                except Exception:
                    pass
            except Exception:
                # Remove broken subscriber
                try:
                    self._event_subscribers.remove(queue)
                except ValueError:
                    pass

    async def process_event(self, event: ProcessingEvent, worker_id: int) -> bool:
        """
        Process a single event through the pipeline.

        This method now owns the orchestration (moved from EventProcessor._process_event).
        Small helper methods are still called via the context.
        """
        start_time = time.time()
        success = False
        fallback_used = False
        context_used = False
        ocr_used = False
        low_confidence = False
        regenerated = False

        try:
            # Story P3-7.3: Check cost caps before AI analysis
            handled = await self._handle_cost_cap_skip(event)
            if handled:
                return handled

            # Generate thumbnail
            thumbnail_base64 = self._generate_thumbnail(event.frame)

            # Early embedding + entity matching for context (Story P4-3.4)
            embedding_vector = None
            entity_result = None
            final_entity_link_result = None
            pre_generated_event_id = str(uuid.uuid4())

            try:
                embedding_vector, entity_result = await self._generate_and_match_entity(thumbnail_base64)

                # Do the final persistent entity link early so the initial store already has rich final entity data
                if embedding_vector:
                    final_entity_link_result = await self._link_entity_to_event(
                        event=event,
                        event_id=pre_generated_event_id,
                        embedding_vector=embedding_vector
                    )
            except Exception as context_error:
                logger.debug(
                    f"Early context generation failed (will skip): {context_error}",
                    extra={"camera_id": event.camera_id}
                )

            # Build context-enhanced prompt (Story P4-3.4)
            context_enhanced_prompt = None
            context_result = None

            try:
                context_service = self.context_prompt_service

                base_prompt = (
                    "Describe what you see in this image. Include: "
                    "WHO (people, their appearance, clothing), "
                    "WHAT (objects, vehicles, packages), "
                    "WHERE (location in frame), "
                    "and ACTIONS (what is happening). "
                    "Be specific and detailed."
                )

                temp_event_id = str(uuid.uuid4())

                with SessionLocal() as context_db:
                    context_result = await context_service.build_context_enhanced_prompt(
                        db=context_db,
                        event_id=temp_event_id,
                        base_prompt=base_prompt,
                        camera_id=event.camera_id,
                        event_time=event.timestamp,
                        matched_entity=entity_result,
                    )

                if context_result and context_result.context_included:
                    context_enhanced_prompt = context_result.prompt
                    logger.info(
                        f"Context-enhanced prompt built for camera {event.camera_name}",
                        extra={
                            "camera_id": event.camera_id,
                            "entity_context": context_result.entity_context_included,
                            "similar_events": context_result.similar_events_count,
                            "time_pattern": context_result.time_pattern_included,
                            "context_gather_time_ms": round(context_result.context_gather_time_ms, 2),
                        }
                    )

            except Exception as context_error:
                logger.warning(
                    f"Context building failed (proceeding without context): {context_error}",
                    extra={"camera_id": event.camera_id, "error": str(context_error)}
                )

            # Generate AI description (with context if available)
            ai_result = await self._generate_ai_description(
                event=event,
                worker_id=worker_id,
                context_enhanced_prompt=context_enhanced_prompt,
                thumbnail_base64=thumbnail_base64,
            )

            if ai_result is None:
                return False

            logger.debug(
                f"Worker {worker_id}: AI description generated",
                extra={
                    "camera_id": event.camera_id,
                    "confidence": ai_result.confidence,
                    "provider": ai_result.provider,
                    "response_time_ms": ai_result.response_time_ms
                }
            )

            # Story P7-2.1: Extract delivery carrier from AI description
            delivery_carrier = None
            try:
                delivery_carrier = extract_carrier(ai_result.description)
                if delivery_carrier:
                    logger.info(
                        f"Delivery carrier detected for camera {event.camera_name}: {delivery_carrier}",
                        extra={"camera_id": event.camera_id, "carrier": delivery_carrier},
                    )
            except Exception as carrier_error:
                logger.warning(
                    f"Carrier extraction failed for camera {event.camera_name}: {carrier_error}",
                    extra={"camera_id": event.camera_id, "error": str(carrier_error)}
                )

            # Prepare bounding box annotation data
            has_annotations = False
            bounding_boxes_json = None
            if ai_result.bounding_boxes:
                import json
                has_annotations = True
                bounding_boxes_json = json.dumps(ai_result.bounding_boxes)

            # Store the successfully processed event (now using pre-generated ID + final entity link result)
            event_id = await self._store_processed_event(
                event=event,
                ai_result=ai_result,
                thumbnail_base64=thumbnail_base64,
                delivery_carrier=delivery_carrier,
                has_annotations=has_annotations,
                bounding_boxes_json=bounding_boxes_json,
                context_result=context_result,
                entity_match_result=entity_result,
                final_entity_link_result=final_entity_link_result,
                pre_generated_event_id=pre_generated_event_id,
            )

            if not event_id:
                return False

            # Cost alerts
            try:
                cost_alert_service = self.cost_alert_service
                with SessionLocal() as db:
                    alerts = await cost_alert_service.check_and_notify(db)
                    if alerts:
                        logger.info(f"Cost alerts triggered: {len(alerts)} notifications sent")
            except Exception as alert_error:
                logger.warning(f"Failed to check cost alerts: {alert_error}")

            # Push notifications
            await self._send_push_notification(
                event=event,
                event_id=event_id,
                ai_result=ai_result,
                thumbnail_base64=thumbnail_base64,
            )

            # MQTT
            await self._publish_mqtt_event(event=event, event_id=event_id)

            # Camera status sensors
            await self._publish_camera_status_sensors(event=event, event_id=event_id, ai_result=ai_result)

            # Store embedding
            await self._store_embedding(event_id=event_id, embedding_vector=embedding_vector, camera_id=event.camera_id)

            # Determine smart_detection_type and objects for post-processing helpers
            smart_detection_type = getattr(event, 'smart_detection_type', None) or \
                                   (event.detected_objects[0].lower() if event.detected_objects else None)
            objects_detected = event.detected_objects or []
            objects_json = json.dumps(objects_detected) if objects_detected else None

            # Build expected post-processing summary (what we will attempt)
            # Post-processing helpers
            homekit_result = await self._run_homekit_triggers(
                event=event, event_id=event_id, smart_detection_type=smart_detection_type
            )

            post_processing_summary = {
                "homekit": homekit_result,
                "face_embedding_attempted": bool(thumbnail_base64),
                "vehicle_embedding_attempted": bool(thumbnail_base64) and any("vehicle" in str(o).lower() for o in objects_detected),
                "entity_alerts_attempted": any(o.lower() in ("person", "vehicle") for o in objects_detected),
                "mqtt_attempted": True,
                "push_attempted": True,
                "camera_status_attempted": True,
                "audio_enrichment_attempted": True,
                "embedding_stored": bool(embedding_vector),
            }
            # Final entity link is now performed early (before the initial store) using the
            # pre-generated event ID. The later call has been removed as it is redundant.
            await self._process_face_embeddings(
                event=event, event_id=event_id, thumbnail_base64=thumbnail_base64
            )
            await self._process_vehicle_embeddings(
                event=event, event_id=event_id, objects_json=objects_json,
                thumbnail_base64=thumbnail_base64, ai_result=ai_result,
                smart_detection_type=smart_detection_type
            )
            await self._process_entity_alerts(
                event=event, event_id=event_id, ai_result=ai_result, objects_detected=objects_detected
            )

            # Audio enrichment (fire and forget)
            try:
                asyncio.create_task(
                    self._enrich_event_with_audio(event_id, event.camera_id)
                )
            except Exception as audio_error:
                logger.warning(f"Failed to create audio enrichment task: {audio_error}")
                post_processing_summary["audio_enrichment_attempted"] = False

            # Persist post-processing summary + final entity link details
            if event_id:
                try:
                    with SessionLocal() as update_db:
                        ev = update_db.query(Event).filter(Event.id == event_id).first()
                        if ev:
                            import json as json_lib
                            if post_processing_summary:
                                ev.post_processing_summary = json_lib.dumps(post_processing_summary)
                            if final_link_result:
                                ev.final_entity_similarity_score = getattr(final_link_result, 'similarity_score', None)
                                ev.final_entity_occurrence_count = getattr(final_link_result, 'occurrence_count', None)
                                ev.final_entity_is_new = getattr(final_link_result, 'is_new', None)
                                ev.final_entity_id = getattr(final_link_result, 'entity_id', None)
                                ev.final_entity_type = getattr(final_link_result, 'entity_type', None)
                                ev.final_entity_name = getattr(final_link_result, 'name', None)
                            update_db.commit()
                except Exception as summary_err:
                    logger.warning(
                        f"Failed to persist post-processing / final entity data for event {event_id}: {summary_err}"
                    )

            logger.info(
                f"Event processed successfully for camera {event.camera_name}",
                extra={
                    "camera_id": event.camera_id,
                    "description": ai_result.description[:100],
                    "confidence": ai_result.confidence,
                    "ai_provider": ai_result.provider
                }
            )

            success = True

            # Best-effort capture of flags for metrics
            context_used = bool(context_result and getattr(context_result, "context_included", False)) if 'context_result' in locals() else False
            fallback_used = getattr(ai_result, "ai_fallback_used", False) if 'ai_result' in locals() else False
            ocr_used = getattr(ai_result, "ocr_used", False) if 'ai_result' in locals() else False
            low_conf = bool(low_confidence) if 'low_confidence' in locals() else False
            regen = regenerated  # from parameter / outer scope

            from app.core import metrics as prom
            prom.ai_processing_total.labels(
                success="true",
                fallback_used=str(fallback_used).lower(),
                context_used=str(context_used).lower(),
                ocr_used=str(ocr_used).lower(),
                low_confidence=str(low_conf).lower(),
                regenerated=str(regen).lower(),
            ).inc()

            duration = time.time() - start_time
            prom.ai_processing_duration_seconds.observe(duration)

            # Update lightweight stats counters
            self._total_processed += 1
            self._success_count += 1
            if fallback_used:
                self._fallback_count += 1
            if context_used:
                self._context_used_count += 1
            if ocr_used:
                self._ocr_used_count += 1
            if low_conf:
                self._low_confidence_count += 1
            if regen:
                self._regenerated_count += 1

            # Record rich recent activity for live view / snapshot
            recent_item = {
                "timestamp": time.time(),
                "camera_id": event.camera_id,
                "success": True,
                "provider": getattr(ai_result, "provider", None),
                "ai_fallback_used": getattr(ai_result, "ai_fallback_used", False),
                "tokens_used": getattr(ai_result, "tokens_used", None),
                "ai_cost": getattr(ai_result, "cost_estimate", None),
                "ai_response_time_ms": getattr(ai_result, "response_time_ms", None),
                "ai_confidence": getattr(ai_result, "ai_confidence", None),
                "prompt_variant": getattr(ai_result, "prompt_variant", None),
                "ocr_used": getattr(ai_result, "ocr_used", False),
                "low_confidence": low_conf,
                "vague_reason": vague_reason,
                "context_used": context_used,
                "context_stats": context_stats,
                "regenerated": regen,
                "entity_early": {
                    "similarity_score": getattr(entity_result, "similarity_score", None) if entity_result else None,
                    "occurrence_count": getattr(entity_result, "occurrence_count", None) if entity_result else None,
                    "is_new": getattr(entity_result, "is_new", None) if entity_result else None,
                },
                "entity_final": {
                    "entity_id": getattr(final_link_result, "entity_id", None) if final_link_result else None,
                    "entity_type": getattr(final_link_result, "entity_type", None) if final_link_result else None,
                    "entity_name": getattr(final_link_result, "name", None) if final_link_result else None,
                    "similarity_score": getattr(final_link_result, "similarity_score", None) if final_link_result else None,
                    "occurrence_count": getattr(final_link_result, "occurrence_count", None) if final_link_result else None,
                    "is_new": getattr(final_link_result, "is_new", None) if final_link_result else None,
                },
                "post_processing_summary": post_processing_summary,
            }
            self._recent_activity.append(recent_item)
            self._update_activity_caches(recent_item)
            self._publish_new_event(recent_item)

            # Push hot list updates to WebSocket clients
            self._publish_hot_update()

            return True

        except Exception as e:
            logger.error(
                f"Event processing failed: {e}",
                exc_info=True,
                extra={
                    "camera_id": event.camera_id,
                    "camera_name": event.camera_name,
                    "worker_id": worker_id
                }
            )
            self.metrics.increment_error("processing_exception")

            from app.core import metrics as prom
            prom.ai_processing_total.labels(
                success="false",
                fallback_used="false",
                context_used="false",
                ocr_used="false",
                low_confidence="false",
                regenerated=str(regenerated).lower() if 'regenerated' in locals() else "false",
            ).inc()

            duration = time.time() - start_time
            prom.ai_processing_duration_seconds.observe(duration)

            # Count the failure for the lightweight stats
            self._total_processed += 1

            # Record failure in recent activity (richer for debugging)
            failure_item = {
                "timestamp": time.time(),
                "camera_id": event.camera_id,
                "success": False,
                "error": str(e)[:300] if 'e' in locals() else "unknown",
                "regenerated": getattr(self, 'regenerated', False) if 'regenerated' in locals() else False,
            }
            self._recent_activity.append(failure_item)

            return False

    async def _handle_cost_cap_skip(self, event: ProcessingEvent) -> bool:
        """
        Check cost caps before AI analysis.

        If analysis should be skipped due to cost caps, stores a minimal event
        and returns True. Otherwise returns False so normal processing can continue.

        Story P3-7.3
        """
        from app.services.service_container import container
        from app.core.database import get_db_session

        cost_cap_service = container.cost_cap_service
        with get_db_session() as db:
            can_analyze, skip_reason = cost_cap_service.can_analyze(db)

        if can_analyze:
            return False

        logger.info(
            f"AI analysis skipped for camera {event.camera_name} due to {skip_reason}",
            extra={"camera_id": event.camera_id, "skip_reason": skip_reason}
        )
        self.metrics.increment_error(f"cost_cap_{skip_reason}")

        # Store event without AI description, with skip reason
        thumbnail_base64 = self._generate_thumbnail(event.frame)
        event_data = {
            "camera_id": event.camera_id,
            "timestamp": event.timestamp.isoformat(),
            "description": f"AI analysis paused - {skip_reason.replace('_', ' ')}",
            "confidence": 0,
            "objects_detected": event.detected_objects,
            "thumbnail_base64": thumbnail_base64,
            "alert_triggered": False,
            "provider_used": None,
            "description_retry_needed": True,
            "analysis_skipped_reason": skip_reason,
        }

        success = await self.store_processed_event(event_data)

        # Record in recent activity so the /ai-processing-recent surface (and snapshots/streams)
        # shows cost-cap skips with the new rich coordinator-owned signal.
        recent_skip_item = {
            "timestamp": time.time(),
            "camera_id": event.camera_id,
            "success": False,
            "analysis_skipped": True,
            "analysis_skipped_reason": skip_reason,
            "description": event_data.get("description"),
        }
        self._recent_activity.append(recent_skip_item)

        return success

    async def _generate_ai_description(
        self,
        event: ProcessingEvent,
        worker_id: int,
        context_enhanced_prompt: Optional[str],
        thumbnail_base64: Optional[str],
    ) -> Optional[Any]:
        """
        Call the AI service to generate a description, with OCR and concurrency control.

        Returns the AIResult on success, or None if all providers failed
        (in which case a retry event has already been stored).
        """
        # Story P9-3.2: Extract OCR from frame overlay if enabled
        ocr_result = None
        try:
            from app.models.system_setting import SystemSetting
            from app.services.ocr_service import extract_overlay_text, is_ocr_available

            with SessionLocal() as ocr_db:
                setting = ocr_db.query(SystemSetting).filter(
                    SystemSetting.key == 'settings_attempt_ocr_extraction'
                ).first()
                if setting and setting.value.lower() == 'true' and is_ocr_available():
                    try:
                        ocr_result = extract_overlay_text(event.frame)
                    except Exception as ocr_err:
                        logger.warning(f"OCR extraction failed: {ocr_err}")
        except Exception as ocr_setup_err:
            logger.debug(f"OCR setup failed (non-critical): {ocr_setup_err}")

        # Limit concurrent AI calls (Phase A.5)
        async with self.ai_semaphore:
            ai_concurrent_in_flight.inc()
            try:
                ai_result = await self.ai_service.generate_description(
                    frame=event.frame,
                    camera_name=event.camera_name,
                    timestamp=event.timestamp.isoformat(),
                    detected_objects=event.detected_objects,
                    sla_timeout_ms=5000,
                    custom_prompt=context_enhanced_prompt,
                    ocr_result=ocr_result,
                )
            finally:
                ai_concurrent_in_flight.dec()

        # Record whether OCR was actually used (attempted + produced text)
        ocr_used = ocr_result is not None and bool(str(ocr_result).strip())
        setattr(ai_result, 'ocr_used', ocr_used)

        # Simple fallback detection (primary provider is currently OpenAI)
        ai_fallback_used = False
        if ai_result.success:
            ai_fallback_used = ai_result.provider.lower() != "openai"
        setattr(ai_result, 'ai_fallback_used', ai_fallback_used)

        if not ai_result.success:
            logger.warning(
                f"All AI providers failed for camera {event.camera_name}, storing event for retry",
                extra={"camera_id": event.camera_id, "error": "All AI providers down"}
            )
            self.metrics.increment_error("ai_service_failed")

            event_data = {
                "camera_id": event.camera_id,
                "timestamp": event.timestamp.isoformat(),
                "description": "[AI description pending - providers unavailable]",
                "confidence": 0,
                "objects_detected": event.detected_objects,
                "thumbnail_base64": thumbnail_base64,
                "alert_triggered": False,
                "provider_used": None,
                "description_retry_needed": True,
            }

            # Use the store helper from the context for the retry case
            success = await self._store_event_with_retry(event_data, max_retries=3)
            if success:
                logger.info(
                    f"Event stored for retry: camera {event.camera_name}",
                    extra={"camera_id": event.camera_id, "description_retry_needed": True}
                )
            return None

        return ai_result

    async def _store_processed_event(
        self,
        event: ProcessingEvent,
        ai_result: Any,
        thumbnail_base64: Optional[str],
        delivery_carrier: Optional[str] = None,
        has_annotations: bool = False,
        bounding_boxes_json: Optional[str] = None,
        context_result: Any = None,
        entity_match_result: Any = None,
        final_entity_link_result: Any = None,
        pre_generated_event_id: Optional[str] = None,
        regenerated: bool = False,
    ) -> Optional[str]:
        """Build the rich event payload and store it after successful AI processing."""
        import json

        context_included = False
        context_stats = None
        if context_result:
            context_included = bool(getattr(context_result, "context_included", False))
            context_stats = {
                "entity_context_included": getattr(context_result, "entity_context_included", False),
                "similar_events_count": getattr(context_result, "similar_events_count", 0),
                "time_pattern_included": getattr(context_result, "time_pattern_included", False),
                "context_gather_time_ms": round(getattr(context_result, "context_gather_time_ms", 0.0), 2),
            }

        # Compute low confidence / vagueness flags (Story P3-6.1 / P3-6.2)
        # This logic is now owned by the coordinator for the main processing path
        ai_conf = getattr(ai_result, "ai_confidence", None)
        low_confidence = False
        vague_reason = None

        try:
            from app.services.vagueness_detector import VaguenessDetector
            vague_result = VaguenessDetector().is_vague(ai_result.description)
            low_confidence = (ai_conf is not None and ai_conf < 50) or vague_result.is_vague
            vague_reason = vague_result.reason if vague_result.is_vague else None
        except Exception as vague_err:
            logger.warning(f"Vagueness detection failed during storage: {vague_err}")

        event_data = {
            "camera_id": event.camera_id,
            "timestamp": event.timestamp.isoformat(),
            "description": ai_result.description,
            "confidence": ai_result.confidence,
            "objects_detected": ai_result.objects_detected,
            "thumbnail_base64": thumbnail_base64,
            "alert_triggered": False,
            "provider_used": ai_result.provider,
            "description_retry_needed": False,
            "ai_cost": ai_result.cost_estimate,
            "ai_response_time_ms": getattr(ai_result, "response_time_ms", None),
            "tokens_used": getattr(ai_result, "tokens_used", None),
            "ai_confidence": ai_conf,
            "prompt_variant": getattr(ai_result, "prompt_variant", None),
            "ocr_used": getattr(ai_result, "ocr_used", False),
            "ai_fallback_used": getattr(ai_result, "ai_fallback_used", False),
            "low_confidence": low_confidence,
            "vague_reason": vague_reason,
            "delivery_carrier": delivery_carrier,
            "has_annotations": has_annotations,
            "bounding_boxes": bounding_boxes_json,
            "context_included": context_included,
            "context_stats": json.dumps(context_stats) if context_stats else None,
            # Early context match (used for prompt enrichment)
            "entity_similarity_score": getattr(entity_match_result, 'similarity_score', None) if entity_match_result else None,
            "entity_occurrence_count": getattr(entity_match_result, 'occurrence_count', None) if entity_match_result else None,
            "entity_is_new": getattr(entity_match_result, 'is_new', None) if entity_match_result else None,
            # Final persistent link — now included at initial store time thanks to pre-generated ID
            "final_entity_similarity_score": getattr(final_entity_link_result, 'similarity_score', None) if final_entity_link_result else getattr(entity_match_result, 'similarity_score', None),
            "final_entity_occurrence_count": getattr(final_entity_link_result, 'occurrence_count', None) if final_entity_link_result else getattr(entity_match_result, 'occurrence_count', None),
            "final_entity_is_new": getattr(final_entity_link_result, 'is_new', None) if final_entity_link_result else getattr(entity_match_result, 'is_new', None),
            "final_entity_id": getattr(final_entity_link_result, 'entity_id', None) if final_entity_link_result else getattr(entity_match_result, 'entity_id', None),
            "final_entity_type": getattr(final_entity_link_result, 'entity_type', None) if final_entity_link_result else getattr(entity_match_result, 'entity_type', None),
            "final_entity_name": getattr(final_entity_link_result, 'name', None) if final_entity_link_result else getattr(entity_match_result, 'name', None),
            "regenerated": regenerated,
        }

        logger.info(f"Storing event for camera {event.camera_name}: {ai_result.description[:50]}...")
        event_id = await self._store_event_with_retry(event_data, max_retries=3)

        if not event_id:
            logger.error(
                f"Failed to store event for camera {event.camera_name}",
                extra={"camera_id": event.camera_id}
            )
            self.metrics.increment_error("event_storage_failed")

        return event_id

    def _generate_thumbnail(self, frame: np.ndarray, max_width: int = 320, max_height: int = 180) -> Optional[str]:
        """
        Generate a base64-encoded JPEG thumbnail from a frame.

        Args:
            frame: OpenCV frame (numpy array in BGR format)
            max_width: Maximum thumbnail width (default 320px)
            max_height: Maximum thumbnail height (default 180px)

        Returns:
            Base64-encoded JPEG string with data URI prefix, or None on error
        """
        try:
            import cv2
            import base64

            if frame is None:
                logger.warning("Cannot generate thumbnail: frame is None")
                return None

            # Calculate aspect-preserving resize
            height, width = frame.shape[:2]
            scale = min(max_width / width, max_height / height)

            if scale < 1:
                new_width = int(width * scale)
                new_height = int(height * scale)
                resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
            else:
                resized = frame

            # Encode as JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
            success, buffer = cv2.imencode('.jpg', resized, encode_params)

            if not success:
                logger.warning("Failed to encode thumbnail as JPEG")
                return None

            # Convert to base64 with data URI prefix
            b64_str = base64.b64encode(buffer).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"

        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}", exc_info=True)
            return None

    async def _send_push_notification(
        self,
        event: ProcessingEvent,
        event_id: str,
        ai_result: Any,
        thumbnail_base64: Optional[str],
    ) -> None:
        """Fire-and-forget push notification for a processed event."""
        try:
            from app.services.push_notification_service import send_event_notification

            push_thumbnail_url = None
            if thumbnail_base64:
                date_str = event.timestamp.strftime("%Y-%m-%d")
                push_thumbnail_url = f"/api/v1/thumbnails/{date_str}/{event_id}.jpg"

            smart_detection_type = event.metadata.get("smart_detection_type")
            if not smart_detection_type and event.detected_objects:
                obj = event.detected_objects[0].lower() if event.detected_objects else None
                if obj in ("person", "vehicle", "package", "animal"):
                    smart_detection_type = obj

            asyncio.create_task(
                send_event_notification(
                    event_id=event_id,
                    camera_name=event.camera_name,
                    description=ai_result.description,
                    thumbnail_url=push_thumbnail_url,
                    camera_id=event.camera_id,
                    smart_detection_type=smart_detection_type,
                )
            )
            logger.debug(
                f"Push notification task created for event {event_id}",
                extra={"event_id": event_id, "camera_name": event.camera_name}
            )
        except Exception as push_error:
            logger.warning(
                f"Failed to create push notification task: {push_error}",
                extra={"error": str(push_error)}
            )

    async def _process_vehicle_embeddings(
        self,
        event: ProcessingEvent,
        event_id: str,
        objects_json: Optional[str],
        thumbnail_base64: Optional[str],
        ai_result: Any,
        smart_detection_type: Optional[str],
    ) -> None:
        """Privacy-gated vehicle embedding processing (fire-and-forget)."""
        try:
            if self.vehicle_embedding_service and thumbnail_base64:
                asyncio.create_task(
                    self.vehicle_embedding_service.process_vehicle_embedding(
                        event_id=event_id,
                        thumbnail_base64=thumbnail_base64,
                        event_description=ai_result.description
                    )
                )
                logger.debug(
                    f"Vehicle embeddings task created for event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id}
                )
        except Exception as vehicle_error:
            logger.warning(
                f"Failed to create vehicle embeddings task: {vehicle_error}",
                extra={"error": str(vehicle_error), "event_id": event_id}
            )

    async def _process_face_embeddings(
        self, event: ProcessingEvent, event_id: str, thumbnail_base64: Optional[str]
    ) -> None:
        """Privacy-gated face processing (fire-and-forget)."""
        try:
            if self.face_embedding_service and thumbnail_base64:
                asyncio.create_task(
                    self.face_embedding_service.process_face_embedding(
                        event_id=event_id,
                        thumbnail_base64=thumbnail_base64
                    )
                )
                logger.debug(
                    f"Face processing task created for event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id}
                )
        except Exception as face_error:
            logger.warning(
                f"Failed to create face processing task: {face_error}",
                extra={"error": str(face_error), "event_id": event_id}
            )

    async def _process_entity_alerts(
        self,
        event: ProcessingEvent,
        event_id: str,
        ai_result: Any,
        objects_detected: Optional[List[str]],
    ) -> None:
        """Privacy-gated entity alert processing (fire-and-forget)."""
        try:
            if self.entity_service:
                has_person_or_vehicle = False
                if objects_detected:
                    has_person_or_vehicle = any(o.lower() in ("person", "vehicle") for o in objects_detected)

                if has_person_or_vehicle:
                    asyncio.create_task(
                        self.entity_service.execute_entity_alerts(
                            event_id=event_id,
                            description=ai_result.description,
                            has_person_or_vehicle=True
                        )
                    )
                    logger.debug(
                        f"Entity alert task created for event {event_id}",
                        extra={"event_id": event_id, "camera_id": event.camera_id}
                    )
        except Exception as entity_alert_error:
            logger.warning(
                f"Failed to create entity alert task: {entity_alert_error}",
                extra={"error": str(entity_alert_error), "event_id": event_id}
            )

    async def _enrich_event_with_audio(
        self,
        event_id: str,
        camera_id: str,
    ) -> None:
        """
        Enrich a stored event with audio detection information (Story P6-3.2).

        This is a fire-and-forget async task. Errors are logged but not propagated.
        Uses its own database session since the caller's session may be closed.
        """
        try:
            from app.services.audio_event_handler import get_audio_event_handler
            from app.models.event import Event

            audio_handler = get_audio_event_handler()

            # Use own session since caller's may be closed
            with get_db_session() as db:
                # Get the stored event
                event = db.query(Event).filter(Event.id == event_id).first()
                if event is None:
                    logger.warning(
                        f"Event {event_id} not found for audio enrichment",
                        extra={"event_id": event_id, "camera_id": camera_id}
                    )
                    return

                # Enrich event with audio information
                enriched = await audio_handler.enrich_event_with_audio(
                    db=db,
                    event=event,
                    camera_id=camera_id,
                    audio_duration_seconds=2.0,
                )

                if enriched:
                    logger.info(
                        f"Event {event_id} enriched with audio",
                        extra={
                            "event_type": "audio_enrichment_complete",
                            "event_id": event_id,
                            "camera_id": camera_id,
                            "audio_event_type": event.audio_event_type,
                            "audio_confidence": event.audio_confidence,
                        }
                    )
                else:
                    logger.debug(
                        f"No audio events detected for event {event_id}",
                        extra={"event_id": event_id, "camera_id": camera_id}
                    )

        except Exception as e:
            # Audio enrichment errors must not propagate
            logger.warning(
                f"Audio enrichment failed for event {event_id}: {e}",
                extra={
                    "event_type": "audio_enrichment_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )

    async def _run_homekit_triggers(
        self, event: ProcessingEvent, event_id: str, smart_detection_type: Optional[str]
    ) -> dict:
        """Trigger appropriate HomeKit sensors based on detection type.

        Returns a dict indicating which specific triggers were successfully fired.
        """
        triggered = {
            "motion": False,
            "occupancy": False,
            "vehicle": False,
            "animal": False,
            "package": False,
        }

        try:
            homekit_service = self.homekit_service
            if not homekit_service or not homekit_service.is_running:
                return triggered

            # Always trigger motion
            try:
                success = homekit_service.trigger_motion(event.camera_id, event_id=event_id)
                if success:
                    triggered["motion"] = True
                    logger.info(
                        f"HomeKit motion triggered for event",
                        extra={
                            "event_type": "homekit_motion_triggered",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )
                else:
                    logger.debug(
                        f"HomeKit motion trigger returned False (no sensor for camera)",
                        extra={
                            "event_type": "homekit_motion_no_sensor",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )
            except Exception as e:
                logger.warning(
                    f"HomeKit motion trigger failed for event {event_id}: {e}",
                    extra={
                        "event_type": "homekit_motion_error",
                        "event_id": event_id,
                        "camera_id": event.camera_id
                    }
                )

            # Person → occupancy
            if smart_detection_type == "person":
                try:
                    success = homekit_service.trigger_occupancy(event.camera_id, event_id=event_id)
                    if success:
                        triggered["occupancy"] = True
                        logger.info(
                            f"HomeKit occupancy triggered for person detection",
                            extra={
                                "event_type": "homekit_occupancy_triggered",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                    else:
                        logger.debug(
                            f"HomeKit occupancy trigger returned False (no sensor for camera)",
                            extra={
                                "event_type": "homekit_occupancy_no_sensor",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"HomeKit occupancy trigger failed for event {event_id}: {e}",
                        extra={
                            "event_type": "homekit_occupancy_error",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )

            # Vehicle
            if smart_detection_type == "vehicle":
                try:
                    success = homekit_service.trigger_vehicle(event.camera_id, event_id=event_id)
                    if success:
                        triggered["vehicle"] = True
                        logger.info(
                            f"HomeKit vehicle triggered for vehicle detection",
                            extra={
                                "event_type": "homekit_vehicle_triggered",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                    else:
                        logger.debug(
                            f"HomeKit vehicle trigger returned False (no sensor for camera)",
                            extra={
                                "event_type": "homekit_vehicle_no_sensor",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"HomeKit vehicle trigger failed for event {event_id}: {e}",
                        extra={
                            "event_type": "homekit_vehicle_error",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )

            # Animal
            if smart_detection_type == "animal":
                try:
                    success = homekit_service.trigger_animal(event.camera_id, event_id=event_id)
                    if success:
                        triggered["animal"] = True
                        logger.info(
                            f"HomeKit animal triggered for animal detection",
                            extra={
                                "event_type": "homekit_animal_triggered",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                    else:
                        logger.debug(
                            f"HomeKit animal trigger returned False (no sensor for camera)",
                            extra={
                                "event_type": "homekit_animal_no_sensor",
                                "event_id": event_id,
                                "camera_id": event.camera_id
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"HomeKit animal trigger failed for event {event_id}: {e}",
                        extra={
                            "event_type": "homekit_animal_error",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )

            # Package (with carrier info)
            if smart_detection_type == "package":
                delivery_carrier = getattr(event, 'delivery_carrier', None)
                try:
                    success = homekit_service.trigger_package(
                        event.camera_id, event_id=event_id, delivery_carrier=delivery_carrier
                    )
                    if success:
                        triggered["package"] = True
                        logger.info(
                            f"HomeKit package triggered for package detection"
                            + (f" (carrier: {delivery_carrier})" if delivery_carrier else ""),
                            extra={
                                "event_type": "homekit_package_triggered",
                                "event_id": event_id,
                                "camera_id": event.camera_id,
                                "delivery_carrier": delivery_carrier
                            }
                        )
                    else:
                        logger.debug(
                            f"HomeKit package trigger returned False (no sensor for camera)",
                            extra={
                                "event_type": "homekit_package_no_sensor",
                                "event_id": event_id,
                                "camera_id": event.camera_id,
                                "delivery_carrier": delivery_carrier
                            }
                        )
                except Exception as e:
                    logger.warning(
                        f"HomeKit package trigger failed for event {event_id}: {e}",
                        extra={
                            "event_type": "homekit_package_error",
                            "event_id": event_id,
                            "camera_id": event.camera_id
                        }
                    )
        except Exception as homekit_error:
            logger.warning(
                f"Failed to trigger HomeKit sensors: {homekit_error}",
                extra={"error": str(homekit_error), "event_id": event_id}
            )

        return triggered

    async def _link_entity_to_event(
        self, event: ProcessingEvent, event_id: str, embedding_vector: Optional[bytes]
    ) -> Optional[Any]:
        """Match or create entity and link it to the event.
        Returns the final match result (or None if no embedding)."""
        if not embedding_vector:
            logger.debug(
                f"Skipping entity matching - no embedding available for event {event_id}",
                extra={"event_id": event_id}
            )
            return None

        try:
            from app.services.service_container import container

            entity_service = container.entity_service

            # Determine entity type
            entity_type = "unknown"
            if hasattr(event, 'smart_detection_type') and event.smart_detection_type in ("person", "vehicle"):
                entity_type = event.smart_detection_type
            elif event.detected_objects:
                objects_list = event.detected_objects if isinstance(event.detected_objects, list) else json.loads(event.detected_objects)
                if "person" in [o.lower() for o in objects_list]:
                    entity_type = "person"
                elif "vehicle" in [o.lower() for o in objects_list]:
                    entity_type = "vehicle"

            with SessionLocal() as entity_db:
                final_entity_result = await entity_service.match_or_create_entity(
                    db=entity_db,
                    event_id=event_id,
                    embedding=embedding_vector,
                    entity_type=entity_type,
                    threshold=0.75,
                )

            logger.info(
                f"Entity {'created' if final_entity_result.is_new else 'matched'} for event {event_id}",
                extra={
                    "event_id": event_id,
                    "entity_id": final_entity_result.entity_id,
                    "entity_type": final_entity_result.entity_type,
                    "is_new": final_entity_result.is_new,
                    "similarity_score": final_entity_result.similarity_score,
                    "occurrence_count": final_entity_result.occurrence_count,
                }
            )
            return final_entity_result
        except Exception as entity_error:
            logger.warning(
                f"Entity linking failed for event {event_id}: {entity_error}",
                extra={"error": str(entity_error), "event_id": event_id}
            )
            return None

    async def _publish_mqtt_event(self, event: ProcessingEvent, event_id: str) -> None:
        """Publish the event to MQTT (Home Assistant / external integrations)."""
        try:
            from app.services.mqtt_service import get_mqtt_service, serialize_event_for_mqtt

            mqtt_service = self.mqtt_service

            if not mqtt_service.is_connected:
                return

            with SessionLocal() as mqtt_db:
                stored_event = mqtt_db.query(Event).filter(Event.id == event_id).first()
                if not stored_event:
                    return

                api_base_url = mqtt_service.get_api_base_url()
                mqtt_payload = serialize_event_for_mqtt(
                    stored_event, event.camera_name, api_base_url=api_base_url
                )
                topic = mqtt_service.get_event_topic(event.camera_id)

                asyncio.create_task(
                    self.publish_event_to_mqtt(mqtt_service, topic, mqtt_payload, event_id)
                )

                logger.debug(
                    f"MQTT publish task created for event {event_id}",
                    extra={
                        "event_id": event_id,
                        "topic": topic,
                        "camera_id": event.camera_id
                    }
                )
        except Exception as mqtt_error:
            logger.warning(
                f"Failed to create MQTT publish task: {mqtt_error}",
                extra={"error": str(mqtt_error), "event_id": event_id}
            )

    async def _generate_early_embedding(self, thumbnail_base64: Optional[str]) -> Optional[bytes]:
        """
        Generate an embedding vector from a thumbnail for early entity matching.

        This is done *before* the AI description so we can provide entity context
        to the vision model (Story P4-3.4).

        Returns the raw embedding bytes, or None on failure.
        """
        if not thumbnail_base64:
            return None

        try:
            import base64 as b64

            embedding_service = self.embedding_service

            # Strip data URI prefix if present
            b64_str = thumbnail_base64
            if b64_str.startswith("data:"):
                comma_idx = b64_str.find(",")
                if comma_idx != -1:
                    b64_str = b64_str[comma_idx + 1:]

            embedding_bytes = b64.b64decode(b64_str)

            # Generate embedding
            embedding_vector = await embedding_service.generate_embedding(embedding_bytes)

            logger.debug(
                f"Early embedding generated (dim={len(embedding_vector) if embedding_vector else 0})",
                extra={"embedding_dim": len(embedding_vector) if embedding_vector else 0}
            )

            return embedding_vector

        except Exception as e:
            logger.debug(f"Early embedding generation failed: {e}")
            return None

    async def _generate_and_match_entity(
        self, thumbnail_base64: Optional[str]
    ) -> tuple[Optional[bytes], Optional[Any]]:
        """
        Generate embedding from thumbnail and attempt to match an existing entity.

        Returns (embedding_vector, entity_result) where either or both can be None.
        """
        embedding_vector = await self._generate_early_embedding(thumbnail_base64)
        if not embedding_vector:
            return None, None

        try:
            entity_service = self.embedding_service  # wait, actually entity_service for match

            # Note: the match is on entity_service, embedding on embedding_service
            # In practice, the context has embedding_service, but the match_entity_only is on entity_service.
            # For accuracy, use container for entity_service here, or add to context.
            from app.services.service_container import container
            entity_service = container.entity_service

            with SessionLocal() as entity_db:
                entity_result = await entity_service.match_entity_only(
                    db=entity_db,
                    embedding=embedding_vector,
                    threshold=0.75,
                )

            if entity_result:
                logger.debug(
                    f"Entity matched for context",
                    extra={
                        "entity_id": entity_result.entity_id,
                        "entity_name": entity_result.name,
                        "similarity_score": entity_result.similarity_score,
                    }
                )
            else:
                logger.debug("No entity match for context")

            return embedding_vector, entity_result

        except Exception as e:
            logger.debug(f"Entity matching for context failed: {e}")
            return embedding_vector, None

    async def _store_embedding(self, event_id: str, embedding_vector: Optional[bytes], camera_id: str) -> None:
        """Store the early embedding for the event (for future context and entity matching)."""
        try:
            if embedding_vector:
                embedding_service = self.embedding_service
                with SessionLocal() as embed_db:
                    await embedding_service.store_embedding(
                        db=embed_db,
                        event_id=event_id,
                        embedding=embedding_vector,
                    )

                logger.debug(
                    f"Embedding stored for event {event_id}",
                    extra={
                        "event_id": event_id,
                        "camera_id": camera_id,
                        "embedding_dim": len(embedding_vector),
                    }
                )
            else:
                logger.debug(
                    f"No embedding available for event {event_id} (will be generated later if needed)",
                    extra={"event_id": event_id}
                )

        except Exception as embedding_error:
            # Graceful fallback - embedding failures must not block event creation
            logger.warning(
                f"Embedding storage failed for event {event_id}: {embedding_error}",
                extra={
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error": str(embedding_error),
                }
            )
