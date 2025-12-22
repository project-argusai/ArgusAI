"""
Summary Service for Activity Summaries (Story P4-4.1)

This module provides the core summary generation functionality for the
Activity Summaries & Digests feature. It processes events for a time period,
groups them by category, and uses AI to generate natural language narratives.

Architecture:
    Event DB → SummaryService.generate_summary()
                    ↓
           Query events for time period
                    ↓
           Group by camera, type, time of day
                    ↓
           Build prompt with aggregated data
                    ↓
           Call AI provider (text-only)
                    ↓
           Store and return summary

Edge Cases:
    - Zero events: Return "No activity" without LLM call (AC7)
    - Single event: Return simple description referencing event (AC8)
    - Many events (50+): Sample intelligently to avoid token limits (AC9)
"""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.services.cost_tracker import get_cost_tracker, CostTracker

logger = logging.getLogger(__name__)

# Constants for performance optimization (AC9, AC12)
MAX_EVENTS_FOR_SUMMARY = 200
MAX_EVENTS_FOR_FULL_DETAIL = 50
SAMPLE_EVENTS_WHEN_LARGE = True

# Story P9-3.5: Default summary prompt for reset functionality
DEFAULT_SUMMARY_PROMPT = """Generate a daily activity summary for {date}.
Summarize the {event_count} events detected across {camera_count} cameras.
Highlight any notable patterns or unusual activity.
Keep the summary concise (2-3 paragraphs)."""


@dataclass
class SummaryStats:
    """Statistical breakdown of events for summary."""
    total_events: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_camera: Dict[str, int] = field(default_factory=dict)
    by_hour: Dict[int, int] = field(default_factory=dict)
    alerts_triggered: int = 0
    doorbell_rings: int = 0
    notable_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SummaryResult:
    """Result of summary generation."""
    summary_text: str
    period_start: datetime
    period_end: datetime
    event_count: int
    generated_at: datetime
    stats: SummaryStats
    ai_cost: Decimal = Decimal("0")
    provider_used: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


class SummaryService:
    """
    Generate natural language summaries of activity events.

    This service provides the core summary generation functionality for Epic P4-4.
    It processes events, groups them by category, and uses AI to generate
    human-readable narrative summaries.

    Attributes:
        DEFAULT_TIMEOUT_SECONDS: Maximum time for LLM call (60s per NFR2)
    """

    DEFAULT_TIMEOUT_SECONDS = 60

    def __init__(self):
        """Initialize SummaryService."""
        self._cost_tracker = get_cost_tracker()
        logger.info(
            "SummaryService initialized",
            extra={"event_type": "summary_service_init"}
        )

    def _get_events_for_summary(
        self,
        db: Session,
        start_time: datetime,
        end_time: datetime,
        camera_ids: Optional[List[str]] = None
    ) -> List[Event]:
        """
        Query events for the summary time period.

        Args:
            db: Database session
            start_time: Period start (inclusive)
            end_time: Period end (inclusive)
            camera_ids: Optional list of camera IDs to filter

        Returns:
            List of Event objects ordered by timestamp
        """
        query = db.query(Event).filter(
            Event.timestamp >= start_time,
            Event.timestamp <= end_time
        )

        if camera_ids:
            query = query.filter(Event.camera_id.in_(camera_ids))

        query = query.order_by(Event.timestamp.asc())
        return query.all()

    def _get_camera_names(
        self,
        db: Session,
        camera_ids: List[str]
    ) -> Dict[str, str]:
        """Get camera names for display in summary."""
        cameras = db.query(Camera).filter(Camera.id.in_(camera_ids)).all()
        return {str(c.id): c.name for c in cameras}

    def _group_events(
        self,
        events: List[Event],
        camera_names: Dict[str, str]
    ) -> SummaryStats:
        """
        Group events by category for summary generation.

        Groups events by:
        - Object type (person, vehicle, package, animal)
        - Camera
        - Hour of day
        - Notable events (alerts, doorbell rings)

        Args:
            events: List of events to group
            camera_names: Mapping of camera ID to name

        Returns:
            SummaryStats with grouped event data
        """
        stats = SummaryStats(total_events=len(events))

        by_type: Dict[str, int] = defaultdict(int)
        by_camera: Dict[str, int] = defaultdict(int)
        by_hour: Dict[int, int] = defaultdict(int)

        for event in events:
            # Group by hour
            hour = event.timestamp.hour
            by_hour[hour] += 1

            # Group by camera
            camera_name = camera_names.get(str(event.camera_id), f"Camera {event.camera_id}")
            by_camera[camera_name] += 1

            # Group by object type
            if event.objects_detected:
                try:
                    objects = json.loads(event.objects_detected)
                    for obj in objects:
                        by_type[obj] += 1
                except (json.JSONDecodeError, TypeError):
                    by_type["unknown"] += 1
            else:
                by_type["unknown"] += 1

            # Track notable events
            if event.alert_triggered:
                stats.alerts_triggered += 1
                stats.notable_events.append({
                    "type": "alert",
                    "time": event.timestamp.strftime("%I:%M %p"),
                    "camera": camera_name,
                    "description": event.description[:100] if event.description else "Alert triggered"
                })

            if event.is_doorbell_ring:
                stats.doorbell_rings += 1
                stats.notable_events.append({
                    "type": "doorbell",
                    "time": event.timestamp.strftime("%I:%M %p"),
                    "camera": camera_name,
                    "description": "Doorbell ring"
                })

        stats.by_type = dict(by_type)
        stats.by_camera = dict(by_camera)
        stats.by_hour = dict(by_hour)

        return stats

    def _sample_events(
        self,
        events: List[Event],
        max_events: int = MAX_EVENTS_FOR_FULL_DETAIL
    ) -> List[Event]:
        """
        Intelligently sample events when there are too many.

        Sampling strategy (AC9):
        1. Keep all alert-triggered events
        2. Keep all doorbell ring events
        3. Keep first and last events
        4. Sample representative events from each hour

        Args:
            events: Full list of events
            max_events: Maximum number of events to keep

        Returns:
            Sampled list of events
        """
        if len(events) <= max_events:
            return events

        # Always keep important events
        important: List[Event] = []
        regular: List[Event] = []

        for event in events:
            if event.alert_triggered or event.is_doorbell_ring:
                important.append(event)
            else:
                regular.append(event)

        # If important events alone exceed limit, take most recent
        if len(important) >= max_events:
            return sorted(important, key=lambda e: e.timestamp)[-max_events:]

        # Calculate how many regular events we can include
        remaining_slots = max_events - len(important)

        if len(regular) <= remaining_slots:
            sampled_regular = regular
        else:
            # Keep first and last, sample middle
            sampled_regular = [regular[0], regular[-1]]
            remaining_slots -= 2

            if remaining_slots > 0:
                # Sample evenly from middle
                middle = regular[1:-1]
                step = max(1, len(middle) // remaining_slots)
                sampled_regular.extend(middle[::step][:remaining_slots])

        # Combine and sort by timestamp
        result = important + sampled_regular
        return sorted(result, key=lambda e: e.timestamp)

    def _get_summary_prompt_from_settings(self, db: Session) -> str:
        """
        Get custom summary prompt from settings (Story P9-3.5).

        Returns the custom prompt if set, otherwise returns the default prompt.

        Args:
            db: Database session

        Returns:
            Summary prompt string
        """
        from app.models.system_setting import SystemSetting

        try:
            setting = db.query(SystemSetting).filter(
                SystemSetting.key == 'summary_prompt'
            ).first()

            if setting and setting.value and setting.value.strip():
                return setting.value.strip()
        except Exception as e:
            logger.warning(f"Failed to read summary_prompt from settings: {e}")

        return DEFAULT_SUMMARY_PROMPT

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt for summary generation.

        Returns narrative-style summary instructions (AC6).
        """
        return (
            "You are summarizing home security camera activity for the homeowner. "
            "Generate a natural, conversational summary that tells the story of what happened. "
            "Focus on: who visited, what was delivered, any unusual activity, and overall patterns. "
            "Use past tense and a friendly, informative tone. Avoid technical jargon and bullet lists. "
            "Write 2-4 sentences that capture the key activity."
        )

    def _build_user_prompt(
        self,
        start_time: datetime,
        end_time: datetime,
        stats: SummaryStats,
        camera_names: Dict[str, str],
        custom_prompt: Optional[str] = None
    ) -> str:
        """
        Build the user prompt with event data for LLM.

        Includes (AC5):
        - Time period context
        - Event counts by category
        - Camera-by-camera breakdown
        - Notable events
        - Time of day patterns

        Story P9-3.5: Supports custom prompt with variable replacement.
        Variables: {date}, {event_count}, {camera_count}

        Args:
            start_time: Period start
            end_time: Period end
            stats: Grouped event statistics
            camera_names: Camera name mapping
            custom_prompt: Optional custom prompt template (Story P9-3.5)

        Returns:
            Formatted prompt string
        """
        # Format time period
        if start_time.date() == end_time.date():
            period = f"on {start_time.strftime('%B %d, %Y')}"
            time_range = f"from {start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')}"
            date_str = start_time.strftime('%B %d, %Y')
        else:
            period = f"from {start_time.strftime('%B %d')} to {end_time.strftime('%B %d, %Y')}"
            time_range = ""
            date_str = f"{start_time.strftime('%B %d')} to {end_time.strftime('%B %d, %Y')}"

        # Build camera list
        cameras = ", ".join(camera_names.values()) if camera_names else "All cameras"
        camera_count = len(camera_names) if camera_names else 0

        # Build category breakdown
        categories = []
        for obj_type, count in sorted(stats.by_type.items(), key=lambda x: -x[1]):
            if count > 0:
                label = obj_type.replace("_", " ").title()
                categories.append(f"- {label}: {count} event{'s' if count != 1 else ''}")
        category_text = "\n".join(categories) if categories else "- No specific categories detected"

        # Build time of day breakdown
        time_periods = {
            "Morning (6am-12pm)": sum(stats.by_hour.get(h, 0) for h in range(6, 12)),
            "Afternoon (12pm-6pm)": sum(stats.by_hour.get(h, 0) for h in range(12, 18)),
            "Evening (6pm-12am)": sum(stats.by_hour.get(h, 0) for h in range(18, 24)),
            "Night (12am-6am)": sum(stats.by_hour.get(h, 0) for h in range(0, 6)),
        }
        active_periods = [f"- {p}: {c} events" for p, c in time_periods.items() if c > 0]
        timeline_text = "\n".join(active_periods) if active_periods else "- No time pattern"

        # Build notable events section
        notable_text = ""
        if stats.notable_events:
            notable_items = []
            for event in stats.notable_events[:5]:  # Limit to 5 notable events
                notable_items.append(f"- {event['type'].title()} at {event['time']} ({event['camera']})")
            notable_text = f"\n\nNotable Events:\n" + "\n".join(notable_items)

        # Story P9-3.5: Build final instruction from custom prompt with variable replacement
        if custom_prompt:
            final_instruction = custom_prompt.format(
                date=date_str,
                event_count=stats.total_events,
                camera_count=camera_count
            )
        else:
            final_instruction = "Generate a 2-4 sentence narrative summary describing what happened."

        prompt = f"""Summarize activity {period} {time_range}:

Cameras: {cameras}
Total Events: {stats.total_events}

By Category:
{category_text}

Timeline:
{timeline_text}{notable_text}

{final_instruction}"""

        return prompt

    def _generate_no_activity_summary(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> str:
        """
        Generate summary for zero events (AC7).

        Returns appropriate "no activity" message without LLM call.
        """
        if start_time.date() == end_time.date():
            date_str = start_time.strftime("%B %d")
            return f"It was a quiet day on {date_str} with no detected activity on any cameras."
        else:
            return f"No activity was detected during this period. All cameras remained quiet."

    def _generate_single_event_summary(
        self,
        event: Event,
        camera_name: str
    ) -> str:
        """
        Generate summary for single event (AC8).

        Returns simple description referencing the event without full LLM call.
        """
        time_str = event.timestamp.strftime("%I:%M %p")

        if event.description:
            return f"There was one event today: {event.description} at {time_str} on {camera_name}."

        # Fallback if no description
        objects = []
        if event.objects_detected:
            try:
                objects = json.loads(event.objects_detected)
            except (json.JSONDecodeError, TypeError):
                pass

        if objects:
            obj_str = ", ".join(objects)
            return f"There was one event today: {obj_str} detected at {time_str} on {camera_name}."

        return f"There was one event today at {time_str} on {camera_name}."

    async def _call_ai_provider(
        self,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    ) -> tuple[str, str, int, int, Decimal]:
        """
        Call AI provider for text generation with fallback chain.

        Uses OpenAI -> Grok -> Claude -> Gemini fallback order.

        Args:
            system_prompt: System instructions
            user_prompt: User message with event data
            timeout_seconds: Maximum time for LLM call

        Returns:
            Tuple of (summary_text, provider_used, input_tokens, output_tokens, cost)

        Raises:
            Exception if all providers fail
        """
        import openai
        import anthropic
        import google.generativeai as genai
        from app.models.system_setting import SystemSetting
        from app.utils.encryption import decrypt_password
        from app.core.database import SessionLocal

        db = SessionLocal()
        try:
            # Load API keys from database
            settings = db.query(SystemSetting).filter(
                SystemSetting.key.in_([
                    'ai_api_key_openai',
                    'ai_api_key_grok',
                    'ai_api_key_claude',
                    'ai_api_key_gemini',
                    'ai_provider_order'
                ])
            ).all()
            keys = {s.key: s.value for s in settings}

            # Get provider order
            provider_order = ['openai', 'grok', 'claude', 'gemini']
            if 'ai_provider_order' in keys and keys['ai_provider_order']:
                try:
                    configured_order = json.loads(keys['ai_provider_order'])
                    if isinstance(configured_order, list):
                        provider_order = configured_order
                except (json.JSONDecodeError, TypeError):
                    pass

            errors = []

            for provider in provider_order:
                key_name = f'ai_api_key_{provider}'
                if key_name not in keys or not keys[key_name]:
                    continue

                try:
                    api_key = decrypt_password(keys[key_name])

                    if provider == 'openai':
                        result = await self._call_openai(api_key, system_prompt, user_prompt, timeout_seconds)
                        return result

                    elif provider == 'grok':
                        result = await self._call_grok(api_key, system_prompt, user_prompt, timeout_seconds)
                        return result

                    elif provider == 'claude':
                        result = await self._call_claude(api_key, system_prompt, user_prompt, timeout_seconds)
                        return result

                    elif provider == 'gemini':
                        result = await self._call_gemini(api_key, system_prompt, user_prompt, timeout_seconds)
                        return result

                except Exception as e:
                    logger.warning(f"Provider {provider} failed: {e}")
                    errors.append(f"{provider}: {str(e)}")
                    continue

            # All providers failed
            raise Exception(f"All AI providers failed. Errors: {'; '.join(errors)}")

        finally:
            db.close()

    async def _call_openai(
        self,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int
    ) -> tuple[str, str, int, int, Decimal]:
        """Call OpenAI for text completion."""
        import openai

        client = openai.AsyncOpenAI(api_key=api_key)

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=300,
            timeout=float(timeout_seconds)
        )

        text = response.choices[0].message.content.strip()
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        cost = self._cost_tracker.calculate_cost("openai", input_tokens, output_tokens)

        logger.info(
            "OpenAI summary generation successful",
            extra={
                "event_type": "summary_ai_success",
                "provider": "openai",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": float(cost)
            }
        )

        return text, "openai", input_tokens, output_tokens, cost

    async def _call_grok(
        self,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int
    ) -> tuple[str, str, int, int, Decimal]:
        """Call xAI Grok for text completion."""
        import openai

        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )

        response = await client.chat.completions.create(
            model="grok-2-vision-1212",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=300,
            timeout=float(timeout_seconds)
        )

        text = response.choices[0].message.content.strip()
        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        cost = self._cost_tracker.calculate_cost("grok", input_tokens, output_tokens)

        logger.info(
            "Grok summary generation successful",
            extra={
                "event_type": "summary_ai_success",
                "provider": "grok",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": float(cost)
            }
        )

        return text, "grok", input_tokens, output_tokens, cost

    async def _call_claude(
        self,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int
    ) -> tuple[str, str, int, int, Decimal]:
        """Call Anthropic Claude for text completion."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)

        response = await client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=300,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            timeout=float(timeout_seconds)
        )

        text = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens if response.usage else 0
        output_tokens = response.usage.output_tokens if response.usage else 0

        cost = self._cost_tracker.calculate_cost("claude", input_tokens, output_tokens)

        logger.info(
            "Claude summary generation successful",
            extra={
                "event_type": "summary_ai_success",
                "provider": "claude",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": float(cost)
            }
        )

        return text, "claude", input_tokens, output_tokens, cost

    async def _call_gemini(
        self,
        api_key: str,
        system_prompt: str,
        user_prompt: str,
        timeout_seconds: int
    ) -> tuple[str, str, int, int, Decimal]:
        """Call Google Gemini for text completion."""
        import google.generativeai as genai
        import asyncio

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        # Gemini doesn't have native async, wrap in executor
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: model.generate_content(full_prompt)
            ),
            timeout=float(timeout_seconds)
        )

        text = response.text.strip()

        # Gemini doesn't return token counts, estimate
        input_tokens = len(full_prompt) // 4  # Rough estimate
        output_tokens = len(text) // 4

        cost = self._cost_tracker.calculate_cost("gemini", input_tokens, output_tokens)

        logger.info(
            "Gemini summary generation successful",
            extra={
                "event_type": "summary_ai_success",
                "provider": "gemini",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": float(cost)
            }
        )

        return text, "gemini", input_tokens, output_tokens, cost

    async def generate_summary(
        self,
        db: Session,
        start_time: datetime,
        end_time: datetime,
        camera_ids: Optional[List[str]] = None
    ) -> SummaryResult:
        """
        Generate a natural language summary for a time period.

        This is the main entry point for summary generation.

        Args:
            db: Database session
            start_time: Period start (inclusive)
            end_time: Period end (inclusive)
            camera_ids: Optional list of camera IDs to include

        Returns:
            SummaryResult with generated summary and metadata

        AC Coverage:
            - AC1: Method signature
            - AC3: Event query
            - AC4: Event grouping
            - AC7: Zero events handling
            - AC8: Single event handling
            - AC9: Large dataset sampling
            - AC10: Statistics included
            - AC11: Cost tracking
        """
        start_gen_time = time.time()
        generated_at = datetime.now(timezone.utc)

        logger.info(
            "Starting summary generation",
            extra={
                "event_type": "summary_generation_start",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "camera_ids": camera_ids
            }
        )

        try:
            # Query events (AC3)
            events = self._get_events_for_summary(db, start_time, end_time, camera_ids)

            # Get camera names for display
            camera_id_set = set(str(e.camera_id) for e in events)
            camera_names = self._get_camera_names(db, list(camera_id_set)) if camera_id_set else {}

            # Handle zero events (AC7)
            if len(events) == 0:
                summary_text = self._generate_no_activity_summary(start_time, end_time)
                return SummaryResult(
                    summary_text=summary_text,
                    period_start=start_time,
                    period_end=end_time,
                    event_count=0,
                    generated_at=generated_at,
                    stats=SummaryStats(),
                    ai_cost=Decimal("0"),
                    provider_used=None,
                    success=True
                )

            # Handle single event (AC8)
            if len(events) == 1:
                event = events[0]
                camera_name = camera_names.get(str(event.camera_id), "Unknown Camera")
                summary_text = self._generate_single_event_summary(event, camera_name)

                stats = self._group_events(events, camera_names)
                return SummaryResult(
                    summary_text=summary_text,
                    period_start=start_time,
                    period_end=end_time,
                    event_count=1,
                    generated_at=generated_at,
                    stats=stats,
                    ai_cost=Decimal("0"),
                    provider_used=None,
                    success=True
                )

            # Sample if too many events (AC9)
            display_events = events
            if len(events) > MAX_EVENTS_FOR_FULL_DETAIL:
                display_events = self._sample_events(events, MAX_EVENTS_FOR_FULL_DETAIL)
                logger.info(
                    f"Sampled {len(display_events)} events from {len(events)} total",
                    extra={
                        "event_type": "summary_event_sampling",
                        "original_count": len(events),
                        "sampled_count": len(display_events)
                    }
                )

            # Group events (AC4)
            stats = self._group_events(events, camera_names)

            # Story P9-3.5: Get custom summary prompt from settings
            custom_prompt = self._get_summary_prompt_from_settings(db)

            # Build prompts (AC5)
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(start_time, end_time, stats, camera_names, custom_prompt)

            # Call AI provider (AC2, AC11)
            summary_text, provider_used, input_tokens, output_tokens, ai_cost = await self._call_ai_provider(
                system_prompt,
                user_prompt,
                timeout_seconds=self.DEFAULT_TIMEOUT_SECONDS
            )

            elapsed_ms = int((time.time() - start_gen_time) * 1000)

            logger.info(
                "Summary generation complete",
                extra={
                    "event_type": "summary_generation_complete",
                    "event_count": len(events),
                    "elapsed_ms": elapsed_ms,
                    "provider": provider_used,
                    "cost_usd": float(ai_cost)
                }
            )

            return SummaryResult(
                summary_text=summary_text,
                period_start=start_time,
                period_end=end_time,
                event_count=len(events),
                generated_at=generated_at,
                stats=stats,
                ai_cost=ai_cost,
                provider_used=provider_used,
                success=True,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )

        except Exception as e:
            elapsed_ms = int((time.time() - start_gen_time) * 1000)
            logger.error(
                f"Summary generation failed: {e}",
                extra={
                    "event_type": "summary_generation_error",
                    "error": str(e),
                    "elapsed_ms": elapsed_ms
                }
            )

            return SummaryResult(
                summary_text=f"Failed to generate summary: {str(e)}",
                period_start=start_time,
                period_end=end_time,
                event_count=0,
                generated_at=generated_at,
                stats=SummaryStats(),
                ai_cost=Decimal("0"),
                provider_used=None,
                success=False,
                error=str(e)
            )


# Singleton instance
_summary_service: Optional[SummaryService] = None


def get_summary_service() -> SummaryService:
    """Get the singleton SummaryService instance."""
    global _summary_service
    if _summary_service is None:
        _summary_service = SummaryService()
    return _summary_service


def reset_summary_service() -> None:
    """Reset the singleton instance (for testing)."""
    global _summary_service
    _summary_service = None
