"""
Centralized retry/backoff utilities.

Provides consistent retry behavior across all services with
configurable strategies and proper logging.

Story P14-5.2: Create exponential backoff utility
"""

import asyncio
import logging
import random
from functools import wraps
from typing import Callable, TypeVar, Sequence, Optional, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Sequence[type[Exception]] = (Exception,),
    ):
        """
        Initialize retry configuration.

        Args:
            max_attempts: Maximum number of attempts (including first)
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries
            exponential_base: Base for exponential backoff
            jitter: Whether to add random jitter to delays
            retryable_exceptions: Exception types that trigger retry
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = tuple(retryable_exceptions)


# Pre-configured strategies for common use cases
RETRY_QUICK = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=2.0,
)

RETRY_STANDARD = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
)

RETRY_PERSISTENT = RetryConfig(
    max_attempts=5,
    base_delay=2.0,
    max_delay=60.0,
)

RETRY_AI_PROVIDER = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)

RETRY_WEBHOOK = RetryConfig(
    max_attempts=4,
    base_delay=1.0,
    max_delay=30.0,
    retryable_exceptions=(ConnectionError, TimeoutError, OSError),
)

RETRY_SNAPSHOT = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=0.5,
    jitter=False,
    retryable_exceptions=(asyncio.TimeoutError, ConnectionError, OSError),
)

RETRY_DB_OPERATION = RetryConfig(
    max_attempts=4,
    base_delay=1.0,
    max_delay=8.0,
    retryable_exceptions=(Exception,),  # DB errors vary by driver
)


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """
    Calculate delay for a given attempt number.

    Args:
        attempt: Zero-based attempt number
        config: Retry configuration

    Returns:
        Delay in seconds
    """
    delay = min(
        config.base_delay * (config.exponential_base ** attempt),
        config.max_delay
    )

    if config.jitter:
        # Add ±25% jitter to prevent thundering herd
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


async def retry_async(
    func: Callable[..., T],
    *args,
    config: RetryConfig = RETRY_STANDARD,
    operation_name: Optional[str] = None,
    **kwargs,
) -> T:
    """
    Execute an async function with retry logic.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        config: Retry configuration
        operation_name: Name for logging (defaults to func name)
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail

    Example:
        async def fetch_data():
            response = await client.get(url)
            return response.json()

        # With default config
        data = await retry_async(fetch_data)

        # With custom config
        data = await retry_async(
            fetch_data,
            config=RETRY_PERSISTENT,
            operation_name="fetch_user_data"
        )
    """
    op_name = operation_name or getattr(func, '__name__', 'operation')
    last_exception: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = calculate_delay(attempt, config)
                logger.warning(
                    f"{op_name} failed (attempt {attempt + 1}/{config.max_attempts}), "
                    f"retrying in {delay:.1f}s: {e}",
                    extra={
                        "event_type": "retry_attempt",
                        "operation": op_name,
                        "attempt": attempt + 1,
                        "max_attempts": config.max_attempts,
                        "delay_seconds": delay,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"{op_name} failed after {config.max_attempts} attempts: {e}",
                    extra={
                        "event_type": "retry_exhausted",
                        "operation": op_name,
                        "attempts": config.max_attempts,
                        "final_error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"{op_name} failed with no exception captured")


def retry_sync(
    func: Callable[..., T],
    *args,
    config: RetryConfig = RETRY_STANDARD,
    operation_name: Optional[str] = None,
    **kwargs,
) -> T:
    """
    Execute a synchronous function with retry logic.

    Args:
        func: Sync function to execute
        *args: Positional arguments for func
        config: Retry configuration
        operation_name: Name for logging (defaults to func name)
        **kwargs: Keyword arguments for func

    Returns:
        Result of successful function call

    Raises:
        Last exception if all retries fail
    """
    import time

    op_name = operation_name or getattr(func, '__name__', 'operation')
    last_exception: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt < config.max_attempts - 1:
                delay = calculate_delay(attempt, config)
                logger.warning(
                    f"{op_name} failed (attempt {attempt + 1}/{config.max_attempts}), "
                    f"retrying in {delay:.1f}s: {e}",
                    extra={
                        "event_type": "retry_attempt",
                        "operation": op_name,
                        "attempt": attempt + 1,
                        "max_attempts": config.max_attempts,
                        "delay_seconds": delay,
                        "error": str(e),
                    }
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"{op_name} failed after {config.max_attempts} attempts: {e}",
                    extra={
                        "event_type": "retry_exhausted",
                        "operation": op_name,
                        "attempts": config.max_attempts,
                        "final_error": str(e),
                    }
                )

    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"{op_name} failed with no exception captured")


def with_retry(
    config: RetryConfig = RETRY_STANDARD,
    operation_name: Optional[str] = None,
):
    """
    Decorator to add retry behavior to async functions.

    Usage:
        @with_retry(config=RETRY_AI_PROVIDER)
        async def call_ai_api(prompt: str) -> str:
            ...

        @with_retry(operation_name="download_clip")
        async def download(url: str) -> bytes:
            ...

    Args:
        config: Retry configuration
        operation_name: Name for logging (defaults to function name)

    Returns:
        Decorated function with retry behavior
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation_name or func.__name__

        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_async(
                func, *args,
                config=config,
                operation_name=op_name,
                **kwargs
            )
        return wrapper
    return decorator


def with_retry_sync(
    config: RetryConfig = RETRY_STANDARD,
    operation_name: Optional[str] = None,
):
    """
    Decorator to add retry behavior to synchronous functions.

    Usage:
        @with_retry_sync(config=RETRY_STANDARD)
        def fetch_data() -> dict:
            ...

    Args:
        config: Retry configuration
        operation_name: Name for logging (defaults to function name)

    Returns:
        Decorated function with retry behavior
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            return retry_sync(
                func, *args,
                config=config,
                operation_name=op_name,
                **kwargs
            )
        return wrapper
    return decorator
