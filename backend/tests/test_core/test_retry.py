"""Tests for retry utilities.

Story P14-5.2: Create exponential backoff utility
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.retry import (
    RetryConfig,
    RETRY_QUICK,
    RETRY_STANDARD,
    RETRY_PERSISTENT,
    RETRY_AI_PROVIDER,
    RETRY_WEBHOOK,
    RETRY_SNAPSHOT,
    RETRY_DB_OPERATION,
    calculate_delay,
    retry_async,
    retry_sync,
    with_retry,
    with_retry_sync,
)


class TestRetryConfig:
    """Tests for RetryConfig class."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.retryable_exceptions == (Exception,)

    def test_custom_values(self):
        """Config should accept custom values."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=0.5,
            max_delay=10.0,
            exponential_base=3.0,
            jitter=False,
            retryable_exceptions=(ValueError, TypeError),
        )
        assert config.max_attempts == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 10.0
        assert config.exponential_base == 3.0
        assert config.jitter is False
        assert config.retryable_exceptions == (ValueError, TypeError)


class TestPreConfiguredStrategies:
    """Tests for pre-configured retry strategies."""

    def test_retry_quick(self):
        """RETRY_QUICK should have quick settings."""
        assert RETRY_QUICK.max_attempts == 2
        assert RETRY_QUICK.base_delay == 0.5
        assert RETRY_QUICK.max_delay == 2.0

    def test_retry_standard(self):
        """RETRY_STANDARD should have standard settings."""
        assert RETRY_STANDARD.max_attempts == 3
        assert RETRY_STANDARD.base_delay == 1.0
        assert RETRY_STANDARD.max_delay == 10.0

    def test_retry_persistent(self):
        """RETRY_PERSISTENT should have persistent settings."""
        assert RETRY_PERSISTENT.max_attempts == 5
        assert RETRY_PERSISTENT.base_delay == 2.0
        assert RETRY_PERSISTENT.max_delay == 60.0

    def test_retry_ai_provider(self):
        """RETRY_AI_PROVIDER should have AI provider settings."""
        assert RETRY_AI_PROVIDER.max_attempts == 3
        assert ConnectionError in RETRY_AI_PROVIDER.retryable_exceptions
        assert TimeoutError in RETRY_AI_PROVIDER.retryable_exceptions

    def test_retry_webhook(self):
        """RETRY_WEBHOOK should have webhook settings."""
        assert RETRY_WEBHOOK.max_attempts == 4
        assert RETRY_WEBHOOK.base_delay == 1.0
        assert RETRY_WEBHOOK.max_delay == 30.0
        assert ConnectionError in RETRY_WEBHOOK.retryable_exceptions
        assert TimeoutError in RETRY_WEBHOOK.retryable_exceptions

    def test_retry_snapshot(self):
        """RETRY_SNAPSHOT should have snapshot settings (Story P14-5.4)."""
        assert RETRY_SNAPSHOT.max_attempts == 2
        assert RETRY_SNAPSHOT.base_delay == 0.5
        assert RETRY_SNAPSHOT.max_delay == 0.5
        assert RETRY_SNAPSHOT.jitter is False
        assert asyncio.TimeoutError in RETRY_SNAPSHOT.retryable_exceptions
        assert ConnectionError in RETRY_SNAPSHOT.retryable_exceptions

    def test_retry_db_operation(self):
        """RETRY_DB_OPERATION should have database operation settings (Story P14-5.4)."""
        assert RETRY_DB_OPERATION.max_attempts == 4
        assert RETRY_DB_OPERATION.base_delay == 1.0
        assert RETRY_DB_OPERATION.max_delay == 8.0
        # Should retry on general exceptions for DB flexibility
        assert Exception in RETRY_DB_OPERATION.retryable_exceptions


class TestCalculateDelay:
    """Tests for delay calculation."""

    def test_exponential_increase(self):
        """Delay should increase exponentially."""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        assert calculate_delay(0, config) == 1.0
        assert calculate_delay(1, config) == 2.0
        assert calculate_delay(2, config) == 4.0
        assert calculate_delay(3, config) == 8.0

    def test_max_delay_cap(self):
        """Delay should not exceed max_delay."""
        config = RetryConfig(base_delay=1.0, max_delay=5.0, jitter=False)
        assert calculate_delay(10, config) == 5.0

    def test_jitter_adds_variation(self):
        """Jitter should add variation to delays."""
        config = RetryConfig(base_delay=10.0, jitter=True)
        delays = [calculate_delay(0, config) for _ in range(100)]
        # Should have some variation (not all the same)
        assert len(set(delays)) > 1
        # All should be within ±25% of base
        for d in delays:
            assert 7.5 <= d <= 12.5

    def test_no_jitter(self):
        """Without jitter, delay should be consistent."""
        config = RetryConfig(base_delay=10.0, jitter=False)
        delays = [calculate_delay(0, config) for _ in range(10)]
        assert all(d == 10.0 for d in delays)


class TestRetryAsync:
    """Tests for retry_async function."""

    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        """Should succeed on first attempt without retrying."""
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await retry_async(operation, config=RETRY_QUICK)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure(self):
        """Should retry on failure and eventually succeed."""
        attempts = []

        async def operation():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("Failed")
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        result = await retry_async(operation, config=config)
        assert result == "success"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausted(self):
        """Should raise after all retries exhausted."""
        async def always_fails():
            raise ValueError("Always fails")

        config = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        with pytest.raises(ValueError, match="Always fails"):
            await retry_async(always_fails, config=config)

    @pytest.mark.asyncio
    async def test_only_retries_specified_exceptions(self):
        """Should only retry on specified exception types."""
        attempts = []

        async def operation():
            attempts.append(1)
            raise KeyError("Not retryable")

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        with pytest.raises(KeyError):
            await retry_async(operation, config=config)
        # Should not have retried
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        """Should pass arguments to the function."""
        async def operation(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await retry_async(operation, "x", "y", c="z", config=RETRY_QUICK)
        assert result == "x-y-z"

    @pytest.mark.asyncio
    async def test_operation_name_in_logging(self):
        """Should use operation_name in logging."""
        async def my_operation():
            raise ValueError("Failed")

        config = RetryConfig(max_attempts=1, base_delay=0.01)

        with pytest.raises(ValueError):
            await retry_async(
                my_operation,
                config=config,
                operation_name="custom_operation"
            )


class TestRetrySync:
    """Tests for retry_sync function."""

    def test_succeeds_on_first_attempt(self):
        """Should succeed on first attempt."""
        call_count = 0

        def operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = retry_sync(operation, config=RETRY_QUICK)
        assert result == "success"
        assert call_count == 1

    def test_retries_on_failure(self):
        """Should retry on failure."""
        attempts = []

        def operation():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("Failed")
            return "success"

        config = RetryConfig(max_attempts=3, base_delay=0.01, jitter=False)
        result = retry_sync(operation, config=config)
        assert result == "success"
        assert len(attempts) == 2

    def test_raises_after_exhausted(self):
        """Should raise after retries exhausted."""
        def always_fails():
            raise ValueError("Always fails")

        config = RetryConfig(max_attempts=2, base_delay=0.01, jitter=False)
        with pytest.raises(ValueError):
            retry_sync(always_fails, config=config)


class TestWithRetryDecorator:
    """Tests for @with_retry decorator."""

    @pytest.mark.asyncio
    async def test_decorator_basic(self):
        """Decorator should work on async functions."""
        call_count = 0

        @with_retry(config=RETRY_QUICK)
        async def my_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await my_operation()
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_decorator_with_retries(self):
        """Decorator should retry on failure."""
        attempts = []

        @with_retry(config=RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        async def my_operation():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("Failed")
            return "success"

        result = await my_operation()
        assert result == "success"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_decorator_custom_name(self):
        """Decorator should use custom operation name."""
        @with_retry(operation_name="custom_op", config=RETRY_QUICK)
        async def my_operation():
            return "success"

        result = await my_operation()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """Decorator should preserve function name and docstring."""
        @with_retry(config=RETRY_QUICK)
        async def my_documented_function():
            """This is a docstring."""
            return "success"

        assert my_documented_function.__name__ == "my_documented_function"
        assert "docstring" in my_documented_function.__doc__


class TestWithRetrySyncDecorator:
    """Tests for @with_retry_sync decorator."""

    def test_decorator_basic(self):
        """Decorator should work on sync functions."""
        call_count = 0

        @with_retry_sync(config=RETRY_QUICK)
        def my_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = my_operation()
        assert result == "success"
        assert call_count == 1

    def test_decorator_with_retries(self):
        """Decorator should retry on failure."""
        attempts = []

        @with_retry_sync(config=RetryConfig(max_attempts=3, base_delay=0.01, jitter=False))
        def my_operation():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionError("Failed")
            return "success"

        result = my_operation()
        assert result == "success"
        assert len(attempts) == 2
