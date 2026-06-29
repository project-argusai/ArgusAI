"""
Reusable decorators for service patterns.

Provides standardized implementations of common patterns like
singleton services with test reset support.

Story P14-5.1: Create @singleton decorator
"""

from functools import wraps
from typing import TypeVar, Optional, Any
import threading

T = TypeVar('T')

# Registry of every class decorated with @singleton, so tests can reset all
# singleton state between cases (the suite otherwise leaks counters/caches across
# tests, causing order-dependent failures). Populated at import time.
_SINGLETON_CLASSES: list = []


def reset_all_singletons() -> None:
    """Reset every registered @singleton AND SingletonMeta instance.

    For use by an autouse test fixture so each test starts from a clean slate.
    Safe to call in production code paths too (it only clears cached instances).
    """
    for cls in list(_SINGLETON_CLASSES):
        reset = getattr(cls, "_reset_instance", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                pass
    # SingletonMeta-based singletons keep their instances in a shared dict.
    for meta_cls in list(SingletonMeta._instances.keys()):
        try:
            SingletonMeta._reset_instance(meta_cls)
        except Exception:
            pass


def singleton(cls: type[T]) -> type[T]:
    """
    Decorator to make a class a singleton.

    Thread-safe lazy initialization with test reset support.

    Usage:
        @singleton
        class MyService:
            def __init__(self):
                self.data = []

        # Get singleton instance
        service = MyService()

        # Reset for testing
        MyService._reset_instance()

    Example migration:
        # Before:
        _my_service: Optional[MyService] = None

        def get_my_service() -> MyService:
            global _my_service
            if _my_service is None:
                _my_service = MyService()
            return _my_service

        def reset_my_service() -> None:
            global _my_service
            _my_service = None

        # After:
        @singleton
        class MyService:
            pass

        # Usage:
        service = MyService()  # Always same instance
        MyService._reset_instance()  # For testing
    """
    # Store original __init__
    original_init = cls.__init__

    # Track instance and lock at class level
    cls._singleton_instance: Optional[Any] = None
    cls._singleton_lock = threading.Lock()
    cls._singleton_initialized = False

    @wraps(original_init)
    def new_init(self, *args, **kwargs):
        # Only initialize once
        if not cls._singleton_initialized:
            original_init(self, *args, **kwargs)
            cls._singleton_initialized = True

    original_new = cls.__new__ if hasattr(cls, '__new__') else object.__new__

    def new_new(klass, *args, **kwargs):
        if klass._singleton_instance is None:
            with klass._singleton_lock:
                if klass._singleton_instance is None:
                    # Create instance without passing args to object.__new__
                    if original_new is object.__new__:
                        klass._singleton_instance = original_new(klass)
                    else:
                        klass._singleton_instance = original_new(klass, *args, **kwargs)
        return klass._singleton_instance

    @classmethod
    def reset_instance(klass) -> None:
        """Reset the singleton instance (for testing)."""
        with klass._singleton_lock:
            if klass._singleton_instance is not None:
                # Clean up if instance has cleanup method
                if hasattr(klass._singleton_instance, 'cleanup'):
                    try:
                        klass._singleton_instance.cleanup()
                    except Exception:
                        pass
            klass._singleton_instance = None
            klass._singleton_initialized = False

    @classmethod
    def get_instance(klass) -> Optional[T]:
        """Get current instance without creating."""
        return klass._singleton_instance

    cls.__init__ = new_init
    cls.__new__ = new_new
    cls._reset_instance = reset_instance
    cls._get_instance = get_instance

    _SINGLETON_CLASSES.append(cls)

    return cls


class SingletonMeta(type):
    """
    Thread-safe singleton metaclass.

    Alternative to the @singleton decorator for cases where
    metaclass usage is preferred.

    Usage:
        class MyService(metaclass=SingletonMeta):
            pass

        # Always returns same instance
        service1 = MyService()
        service2 = MyService()
        assert service1 is service2

        # Reset for testing
        MyService._reset_instance()
    """
    _instances: dict = {}
    _lock: threading.Lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[cls] = instance
        return cls._instances[cls]

    def _reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        with cls._lock:
            if cls in cls._instances:
                instance = cls._instances[cls]
                if hasattr(instance, 'cleanup'):
                    try:
                        instance.cleanup()
                    except Exception:
                        pass
                del cls._instances[cls]

    def _get_instance(cls):
        """Get current instance without creating."""
        return cls._instances.get(cls)
