"""
Feedback API endpoints - Story P4-5.2, P4-5.4

Provides REST API for:
- GET /feedback/stats - Get aggregate feedback statistics with filtering
- GET /feedback/prompt-insights - Get AI prompt improvement suggestions (P4-5.4)
- POST /feedback/prompt-insights/apply - Apply a suggestion to the prompt (P4-5.4)
- GET /feedback/ab-test/results - Get A/B test results (P4-5.4)
- GET /feedback/prompt-history - Get prompt evolution history (P4-5.4)
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from typing import Optional
from datetime import date, datetime, timezone, timedelta
import logging
import json
import uuid

from app.core.database import get_db
from app.models.event_feedback import EventFeedback
from app.models.event import Event
from app.models.camera import Camera
from app.models.prompt_history import PromptHistory
from app.models.system_setting import SystemSetting
from app.models.summary_feedback import SummaryFeedback  # Story P9-3.6
from app.schemas.feedback import (
    FeedbackStatsResponse,
    CameraFeedbackStats,
    DailyFeedbackStats,
    CorrectionSummary,
    SummaryFeedbackStats,  # Story P9-3.6
)
from app.schemas.prompt_insight import (
    PromptInsightsResponse,
    PromptSuggestion as PromptSuggestionSchema,
    CameraInsight as CameraInsightSchema,
    ApplySuggestionRequest,
    ApplySuggestionResponse,
    ABTestResultsResponse,
    ABTestAccuracyStats,
    PromptHistoryResponse,
    PromptHistoryEntry,
)
from app.services.feedback_analysis_service import (
    FeedbackAnalysisService,
    CorrectionCategory,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.get("/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    camera_id: Optional[str] = Query(
        None,
        description="Filter by camera UUID to get per-camera accuracy"
    ),
    start_date: Optional[date] = Query(
        None,
        description="Filter feedback created on or after this date (YYYY-MM-DD)"
    ),
    end_date: Optional[date] = Query(
        None,
        description="Filter feedback created on or before this date (YYYY-MM-DD)"
    ),
    db: Session = Depends(get_db)
):
    """
    Get aggregate feedback statistics for AI description accuracy monitoring.

    Returns overall accuracy metrics, per-camera breakdown, daily trends,
    and common correction patterns.

    **Query Parameters:**
    - `camera_id`: Optional filter to get stats for a specific camera
    - `start_date`: Optional filter for feedback on or after this date
    - `end_date`: Optional filter for feedback on or before this date

    **Response Fields:**
    - `total_count`: Total number of feedback submissions
    - `helpful_count`: Number of helpful ratings
    - `not_helpful_count`: Number of not helpful ratings
    - `accuracy_rate`: Percentage of helpful ratings (helpful / total * 100)
    - `feedback_by_camera`: Per-camera breakdown with accuracy rates
    - `daily_trend`: Daily feedback counts for the last 30 days (or specified range)
    - `top_corrections`: Most common correction patterns (top 10)

    **Performance:**
    Optimized for <200ms response time with 10,000+ feedback records.

    **Examples:**
    ```
    GET /api/v1/feedback/stats
    GET /api/v1/feedback/stats?camera_id=abc123
    GET /api/v1/feedback/stats?start_date=2025-12-01&end_date=2025-12-31
    ```
    """
    try:
        # Build base filter conditions
        filters = []

        if camera_id:
            filters.append(EventFeedback.camera_id == camera_id)

        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            filters.append(EventFeedback.created_at >= start_datetime)

        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            filters.append(EventFeedback.created_at <= end_datetime)

        # 1. Calculate overall aggregate statistics
        aggregate_query = db.query(
            func.count(EventFeedback.id).label('total'),
            func.sum(case((EventFeedback.rating == 'helpful', 1), else_=0)).label('helpful'),
            func.sum(case((EventFeedback.rating == 'not_helpful', 1), else_=0)).label('not_helpful'),
        )

        if filters:
            aggregate_query = aggregate_query.filter(and_(*filters))

        stats = aggregate_query.first()

        total_count = stats.total or 0
        helpful_count = stats.helpful or 0
        not_helpful_count = stats.not_helpful or 0
        accuracy_rate = (helpful_count / total_count * 100) if total_count > 0 else 0.0

        # 2. Calculate per-camera breakdown
        feedback_by_camera = {}

        if not camera_id:  # Only calculate if not filtering by single camera
            camera_query = db.query(
                EventFeedback.camera_id,
                Camera.name.label('camera_name'),
                func.count(EventFeedback.id).label('total'),
                func.sum(case((EventFeedback.rating == 'helpful', 1), else_=0)).label('helpful'),
                func.sum(case((EventFeedback.rating == 'not_helpful', 1), else_=0)).label('not_helpful'),
            ).outerjoin(
                Camera, EventFeedback.camera_id == Camera.id
            ).filter(
                EventFeedback.camera_id.isnot(None)
            )

            if filters:
                camera_query = camera_query.filter(and_(*filters))

            camera_query = camera_query.group_by(
                EventFeedback.camera_id, Camera.name
            )

            camera_results = camera_query.all()

            for row in camera_results:
                cam_total = row.total or 0
                cam_helpful = row.helpful or 0
                cam_not_helpful = row.not_helpful or 0
                cam_accuracy = (cam_helpful / cam_total * 100) if cam_total > 0 else 0.0

                feedback_by_camera[row.camera_id] = CameraFeedbackStats(
                    camera_id=row.camera_id,
                    camera_name=row.camera_name or f"Camera {row.camera_id[:8]}",
                    helpful_count=cam_helpful,
                    not_helpful_count=cam_not_helpful,
                    accuracy_rate=round(cam_accuracy, 1)
                )
        else:
            # When filtering by camera_id, include that camera's stats
            camera = db.query(Camera).filter(Camera.id == camera_id).first()
            camera_name = camera.name if camera else f"Camera {camera_id[:8]}"

            feedback_by_camera[camera_id] = CameraFeedbackStats(
                camera_id=camera_id,
                camera_name=camera_name,
                helpful_count=helpful_count,
                not_helpful_count=not_helpful_count,
                accuracy_rate=round(accuracy_rate, 1)
            )

        # 3. Calculate daily trend (last 30 days or specified range)
        daily_trend = []

        # Determine date range for trend
        if start_date and end_date:
            trend_start = start_date
            trend_end = end_date
        elif start_date:
            trend_start = start_date
            trend_end = date.today()
        elif end_date:
            trend_start = end_date - timedelta(days=30)
            trend_end = end_date
        else:
            trend_end = date.today()
            trend_start = trend_end - timedelta(days=30)

        trend_start_dt = datetime.combine(trend_start, datetime.min.time()).replace(tzinfo=timezone.utc)
        trend_end_dt = datetime.combine(trend_end, datetime.max.time()).replace(tzinfo=timezone.utc)

        trend_filters = [
            EventFeedback.created_at >= trend_start_dt,
            EventFeedback.created_at <= trend_end_dt,
        ]

        if camera_id:
            trend_filters.append(EventFeedback.camera_id == camera_id)

        # Use func.date for SQLite compatibility
        daily_query = db.query(
            func.date(EventFeedback.created_at).label('date'),
            func.sum(case((EventFeedback.rating == 'helpful', 1), else_=0)).label('helpful_count'),
            func.sum(case((EventFeedback.rating == 'not_helpful', 1), else_=0)).label('not_helpful_count'),
        ).filter(
            and_(*trend_filters)
        ).group_by(
            func.date(EventFeedback.created_at)
        ).order_by(
            func.date(EventFeedback.created_at)
        )

        daily_results = daily_query.all()

        for row in daily_results:
            # Handle both string dates (SQLite) and date objects
            if isinstance(row.date, str):
                day = datetime.strptime(row.date, '%Y-%m-%d').date()
            else:
                day = row.date

            daily_trend.append(DailyFeedbackStats(
                date=day,
                helpful_count=row.helpful_count or 0,
                not_helpful_count=row.not_helpful_count or 0
            ))

        # 4. Get top corrections (most common correction patterns)
        top_corrections = []

        correction_query = db.query(
            EventFeedback.correction,
            func.count(EventFeedback.id).label('count')
        ).filter(
            EventFeedback.correction.isnot(None),
            EventFeedback.correction != ''
        )

        if filters:
            correction_query = correction_query.filter(and_(*filters))

        correction_query = correction_query.group_by(
            EventFeedback.correction
        ).order_by(
            func.count(EventFeedback.id).desc()
        ).limit(10)

        correction_results = correction_query.all()

        for row in correction_results:
            top_corrections.append(CorrectionSummary(
                correction_text=row.correction,
                count=row.count
            ))

        # 5. Story P9-3.6: Calculate summary feedback statistics
        summary_feedback_stats = None
        try:
            summary_filters = []

            if start_date:
                summary_filters.append(SummaryFeedback.created_at >= start_datetime)

            if end_date:
                summary_filters.append(SummaryFeedback.created_at <= end_datetime)

            summary_query = db.query(
                func.count(SummaryFeedback.id).label('total'),
                func.sum(case((SummaryFeedback.rating == 'positive', 1), else_=0)).label('positive'),
                func.sum(case((SummaryFeedback.rating == 'negative', 1), else_=0)).label('negative'),
            )

            if summary_filters:
                summary_query = summary_query.filter(and_(*summary_filters))

            summary_stats = summary_query.first()

            summary_total = summary_stats.total or 0
            summary_positive = summary_stats.positive or 0
            summary_negative = summary_stats.negative or 0

            if summary_total > 0:
                summary_accuracy = (summary_positive / summary_total * 100)
                summary_feedback_stats = SummaryFeedbackStats(
                    total_count=summary_total,
                    positive_count=summary_positive,
                    negative_count=summary_negative,
                    accuracy_rate=round(summary_accuracy, 1)
                )
        except Exception as e:
            logger.warning(f"Failed to calculate summary feedback stats: {e}")
            # Continue without summary stats if query fails

        logger.info(
            f"Feedback stats retrieved: total={total_count}, helpful={helpful_count}, "
            f"accuracy={accuracy_rate:.1f}%, cameras={len(feedback_by_camera)}, "
            f"summary_feedback={'yes' if summary_feedback_stats else 'no'}, "
            f"filters={{camera_id={camera_id}, start_date={start_date}, end_date={end_date}}}"
        )

        return FeedbackStatsResponse(
            total_count=total_count,
            helpful_count=helpful_count,
            not_helpful_count=not_helpful_count,
            accuracy_rate=round(accuracy_rate, 1),
            feedback_by_camera=feedback_by_camera,
            daily_trend=daily_trend,
            top_corrections=top_corrections,
            summary_feedback=summary_feedback_stats  # Story P9-3.6
        )

    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}", exc_info=True)
        raise


# ==============================================================================
# Story P4-5.4: Prompt Insights and A/B Testing Endpoints
# ==============================================================================


@router.get("/prompt-insights", response_model=PromptInsightsResponse)
async def get_prompt_insights(
    camera_id: Optional[str] = Query(
        None,
        description="Filter insights for a specific camera"
    ),
    db: Session = Depends(get_db)
):
    """
    Get AI prompt improvement suggestions based on user feedback analysis.

    Analyzes feedback corrections to identify patterns and generate
    actionable suggestions for improving AI description prompts.

    **Minimum Samples:**
    Requires at least 10 feedback corrections before generating suggestions.

    **Response Fields:**
    - `suggestions`: Global prompt improvement suggestions
    - `camera_insights`: Per-camera analysis with specific suggestions for low-accuracy cameras
    - `sample_count`: Total feedback corrections analyzed
    - `confidence`: Overall confidence in the analysis (0.0 to 1.0)
    - `min_samples_met`: Whether the 10-sample threshold was met

    **Examples:**
    ```
    GET /api/v1/feedback/prompt-insights
    GET /api/v1/feedback/prompt-insights?camera_id=abc123
    ```
    """
    try:
        service = FeedbackAnalysisService(db)
        result = service.analyze_correction_patterns(camera_id=camera_id)

        # Convert dataclass results to Pydantic schemas
        suggestions = [
            PromptSuggestionSchema(
                id=s.id,
                category=s.category.value,
                suggestion_text=s.suggestion_text,
                example_corrections=s.example_corrections,
                confidence=s.confidence,
                impact_score=s.impact_score,
                camera_id=s.camera_id
            )
            for s in result.suggestions
        ]

        camera_insights = {}
        for cam_id, insight in result.camera_insights.items():
            cam_suggestions = [
                PromptSuggestionSchema(
                    id=s.id,
                    category=s.category.value,
                    suggestion_text=s.suggestion_text,
                    example_corrections=s.example_corrections,
                    confidence=s.confidence,
                    impact_score=s.impact_score,
                    camera_id=s.camera_id
                )
                for s in insight.suggestions
            ]
            camera_insights[cam_id] = CameraInsightSchema(
                camera_id=insight.camera_id,
                camera_name=insight.camera_name,
                accuracy_rate=insight.accuracy_rate,
                sample_count=insight.sample_count,
                top_categories=[c.value for c in insight.top_categories],
                suggestions=cam_suggestions
            )

        logger.info(
            f"Prompt insights generated: {len(suggestions)} suggestions, "
            f"{len(camera_insights)} cameras, sample_count={result.sample_count}"
        )

        return PromptInsightsResponse(
            suggestions=suggestions,
            camera_insights=camera_insights,
            sample_count=result.sample_count,
            confidence=result.confidence,
            min_samples_met=result.min_samples_met
        )

    except Exception as e:
        logger.error(f"Failed to get prompt insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/prompt-insights/apply", response_model=ApplySuggestionResponse)
async def apply_prompt_suggestion(
    request: ApplySuggestionRequest,
    db: Session = Depends(get_db)
):
    """
    Apply a prompt improvement suggestion to the AI description prompt.

    Updates the system's description prompt with the suggestion text
    and creates a prompt history record for tracking.

    **Request Body:**
    - `suggestion_id`: ID of the suggestion to apply
    - `camera_id`: Optional camera ID for camera-specific prompt

    **Response:**
    - `success`: Whether the suggestion was applied
    - `new_prompt`: The updated prompt text
    - `prompt_version`: Version number of the new prompt
    - `message`: Status message
    """
    try:
        # Get current prompt
        current_prompt_setting = db.query(SystemSetting).filter(
            SystemSetting.key == 'settings_description_prompt'
        ).first()

        current_prompt = ""
        if current_prompt_setting:
            current_prompt = current_prompt_setting.value or ""

        # For now, we regenerate the suggestion based on feedback analysis
        # In production, you'd look up the suggestion by ID from a suggestions cache
        service = FeedbackAnalysisService(db)
        result = service.analyze_correction_patterns(camera_id=request.camera_id)

        # Find the suggestion by ID
        suggestion = None
        for s in result.suggestions:
            if s.id == request.suggestion_id:
                suggestion = s
                break

        # Also check camera-specific suggestions
        if not suggestion:
            for cam_insight in result.camera_insights.values():
                for s in cam_insight.suggestions:
                    if s.id == request.suggestion_id:
                        suggestion = s
                        break
                if suggestion:
                    break

        if not suggestion:
            raise HTTPException(
                status_code=404,
                detail=f"Suggestion {request.suggestion_id} not found"
            )

        # Calculate current accuracy for history tracking
        total_feedback = db.query(EventFeedback).count()
        helpful_feedback = db.query(EventFeedback).filter(
            EventFeedback.rating == 'helpful'
        ).count()
        accuracy_before = (helpful_feedback / total_feedback * 100) if total_feedback > 0 else 0.0

        # Append suggestion to current prompt
        if current_prompt:
            new_prompt = f"{current_prompt}\n\n{suggestion.suggestion_text}"
        else:
            new_prompt = suggestion.suggestion_text

        # Get next version number
        max_version = db.query(func.max(PromptHistory.prompt_version)).scalar() or 0
        new_version = max_version + 1

        # Handle camera-specific prompts
        if request.camera_id:
            # Update camera's prompt_override
            camera = db.query(Camera).filter(Camera.id == request.camera_id).first()
            if not camera:
                raise HTTPException(status_code=404, detail="Camera not found")

            camera.prompt_override = new_prompt
        else:
            # Update global prompt setting
            if current_prompt_setting:
                current_prompt_setting.value = new_prompt
            else:
                db.add(SystemSetting(
                    key='settings_description_prompt',
                    value=new_prompt,
                    description='Custom AI description prompt'
                ))

        # Create history record
        history_entry = PromptHistory(
            id=str(uuid.uuid4()),
            prompt_version=new_version,
            prompt_text=new_prompt,
            source='suggestion',
            applied_suggestions=json.dumps([request.suggestion_id]),
            accuracy_before=round(accuracy_before, 1),
            camera_id=request.camera_id
        )
        db.add(history_entry)
        db.commit()

        logger.info(
            f"Applied suggestion {request.suggestion_id}: "
            f"version={new_version}, camera_id={request.camera_id}"
        )

        return ApplySuggestionResponse(
            success=True,
            new_prompt=new_prompt,
            prompt_version=new_version,
            message=f"Suggestion applied successfully. Prompt version {new_version} created."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply suggestion: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ab-test/results", response_model=ABTestResultsResponse)
async def get_ab_test_results(
    start_date: Optional[date] = Query(
        None,
        description="Filter events from this date"
    ),
    end_date: Optional[date] = Query(
        None,
        description="Filter events until this date"
    ),
    db: Session = Depends(get_db)
):
    """
    Get A/B test results comparing control vs experiment prompts.

    Analyzes feedback on events tagged with prompt_variant to determine
    which prompt performs better.

    **Query Parameters:**
    - `start_date`: Optional start date filter
    - `end_date`: Optional end date filter

    **Response:**
    - `control`: Accuracy statistics for control group
    - `experiment`: Accuracy statistics for experiment group
    - `winner`: Which variant is winning ('control', 'experiment', or None)
    - `confidence`: Statistical confidence in the result
    - `is_significant`: Whether the difference is statistically significant
    - `message`: Summary message
    """
    try:
        # Build date filters
        filters = []
        if start_date:
            start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            filters.append(Event.timestamp >= start_dt)
        if end_date:
            end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            filters.append(Event.timestamp <= end_dt)

        # Get control group stats
        control_query = db.query(
            func.count(Event.id).label('event_count')
        ).filter(
            Event.prompt_variant == 'control',
            *filters
        )
        control_events = control_query.scalar() or 0

        control_feedback_query = db.query(
            func.count(EventFeedback.id).label('total'),
            func.sum(case((EventFeedback.rating == 'helpful', 1), else_=0)).label('helpful'),
            func.sum(case((EventFeedback.rating == 'not_helpful', 1), else_=0)).label('not_helpful'),
        ).join(
            Event, Event.id == EventFeedback.event_id
        ).filter(
            Event.prompt_variant == 'control',
            *filters
        )
        control_stats = control_feedback_query.first()

        # Get experiment group stats
        experiment_query = db.query(
            func.count(Event.id).label('event_count')
        ).filter(
            Event.prompt_variant == 'experiment',
            *filters
        )
        experiment_events = experiment_query.scalar() or 0

        experiment_feedback_query = db.query(
            func.count(EventFeedback.id).label('total'),
            func.sum(case((EventFeedback.rating == 'helpful', 1), else_=0)).label('helpful'),
            func.sum(case((EventFeedback.rating == 'not_helpful', 1), else_=0)).label('not_helpful'),
        ).join(
            Event, Event.id == EventFeedback.event_id
        ).filter(
            Event.prompt_variant == 'experiment',
            *filters
        )
        experiment_stats = experiment_feedback_query.first()

        # Calculate accuracy rates
        control_helpful = control_stats.helpful or 0
        control_not_helpful = control_stats.not_helpful or 0
        control_total = control_helpful + control_not_helpful
        control_accuracy = (control_helpful / control_total * 100) if control_total > 0 else 0.0

        experiment_helpful = experiment_stats.helpful or 0
        experiment_not_helpful = experiment_stats.not_helpful or 0
        experiment_total = experiment_helpful + experiment_not_helpful
        experiment_accuracy = (experiment_helpful / experiment_total * 100) if experiment_total > 0 else 0.0

        # Determine winner and significance
        min_samples = 20  # Minimum samples for significance
        winner = None
        confidence = 0.0
        is_significant = False

        if control_total >= min_samples and experiment_total >= min_samples:
            diff = abs(control_accuracy - experiment_accuracy)
            if diff > 5.0:  # Require 5% difference for significance
                is_significant = True
                winner = 'control' if control_accuracy > experiment_accuracy else 'experiment'
                # Simple confidence calculation based on sample size and difference
                confidence = min(0.95, 0.5 + (diff / 100) + (min(control_total, experiment_total) / 200))
            else:
                confidence = 0.3 + (min(control_total, experiment_total) / 200)

        # Generate message
        if control_total == 0 and experiment_total == 0:
            message = "No A/B test data available. Enable A/B testing in settings to start collecting data."
        elif not is_significant:
            message = f"Insufficient data for significance. Control: {control_total} samples, Experiment: {experiment_total} samples."
        else:
            winning_accuracy = control_accuracy if winner == 'control' else experiment_accuracy
            losing_accuracy = experiment_accuracy if winner == 'control' else control_accuracy
            message = f"{winner.title()} prompt wins with {winning_accuracy:.1f}% accuracy vs {losing_accuracy:.1f}%."

        logger.info(
            f"A/B test results: control={control_accuracy:.1f}% ({control_total}), "
            f"experiment={experiment_accuracy:.1f}% ({experiment_total}), winner={winner}"
        )

        return ABTestResultsResponse(
            control=ABTestAccuracyStats(
                variant='control',
                event_count=control_events,
                helpful_count=control_helpful,
                not_helpful_count=control_not_helpful,
                accuracy_rate=round(control_accuracy, 1)
            ),
            experiment=ABTestAccuracyStats(
                variant='experiment',
                event_count=experiment_events,
                helpful_count=experiment_helpful,
                not_helpful_count=experiment_not_helpful,
                accuracy_rate=round(experiment_accuracy, 1)
            ),
            winner=winner,
            confidence=round(confidence, 2),
            is_significant=is_significant,
            message=message
        )

    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompt-history", response_model=PromptHistoryResponse)
async def get_prompt_history(
    camera_id: Optional[str] = Query(
        None,
        description="Filter history for a specific camera"
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of entries to return"
    ),
    db: Session = Depends(get_db)
):
    """
    Get prompt evolution history.

    Returns the history of prompt changes, including which suggestions
    were applied and accuracy metrics before/after.

    **Query Parameters:**
    - `camera_id`: Optional filter for camera-specific prompts
    - `limit`: Maximum entries to return (default 20)

    **Response:**
    - `entries`: List of prompt history entries (newest first)
    - `current_version`: Current active prompt version
    - `total_count`: Total number of prompt versions
    """
    try:
        query = db.query(PromptHistory)

        if camera_id:
            query = query.filter(PromptHistory.camera_id == camera_id)
        else:
            # Global prompts only (no camera_id)
            query = query.filter(PromptHistory.camera_id.is_(None))

        # Get total count
        total_count = query.count()

        # Get entries ordered by version descending
        entries = query.order_by(
            PromptHistory.prompt_version.desc()
        ).limit(limit).all()

        # Convert to response schema
        entry_list = [
            PromptHistoryEntry(
                id=e.id,
                prompt_version=e.prompt_version,
                prompt_text=e.prompt_text,
                source=e.source,
                applied_suggestions=json.loads(e.applied_suggestions) if e.applied_suggestions else None,
                accuracy_before=e.accuracy_before,
                accuracy_after=e.accuracy_after,
                camera_id=e.camera_id,
                created_at=e.created_at
            )
            for e in entries
        ]

        current_version = entries[0].prompt_version if entries else 0

        return PromptHistoryResponse(
            entries=entry_list,
            current_version=current_version,
            total_count=total_count
        )

    except Exception as e:
        logger.error(f"Failed to get prompt history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
