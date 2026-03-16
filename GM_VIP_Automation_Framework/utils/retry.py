"""
GM VIP Automation Framework – Retry / Poll Utilities
=====================================================
Provides a generic :func:`retry` decorator and a :func:`poll_until` helper
that are used internally by the framework to implement timeout-based polling
(e.g. waiting for the ECU to enter a halted/running state).
"""

from __future__ import annotations

import functools
import time
from typing import Callable, Optional, Tuple, Type, TypeVar, Union

F = TypeVar("F", bound=Callable)


def retry(
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]],
    max_attempts: int = 3,
    delay_s: float = 0.5,
    backoff: float = 1.0,
    logger=None,
) -> Callable[[F], F]:
    """Decorator – retry *func* up to *max_attempts* times on *exceptions*.

    Parameters
    ----------
    exceptions:
        Exception type or tuple of types that trigger a retry.
    max_attempts:
        Maximum number of call attempts (including the first).
    delay_s:
        Initial wait in seconds between attempts.
    backoff:
        Multiplier applied to *delay_s* after each failure (``1.0`` → no back-off).
    logger:
        Optional :class:`logging.Logger` instance for retry log messages.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay_s
            last_exc: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt < max_attempts:
                        if logger:
                            logger.warning(
                                "Attempt %d/%d failed for %s: %s. Retrying in %.2fs…",
                                attempt,
                                max_attempts,
                                func.__qualname__,
                                exc,
                                current_delay,
                            )
                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def poll_until(
    condition: Callable[[], bool],
    timeout_s: float,
    interval_s: float = 0.2,
    description: str = "condition",
    raise_on_timeout: bool = False,
    timeout_exception: Optional[Type[Exception]] = None,
) -> bool:
    """Poll *condition* every *interval_s* seconds until it returns ``True``
    or *timeout_s* elapses.

    Parameters
    ----------
    condition:
        Zero-argument callable that returns ``True`` when the desired state
        has been reached.
    timeout_s:
        Maximum number of seconds to wait.
    interval_s:
        Sleep duration between polls.
    description:
        Human-readable description of what is being waited for (used in the
        :class:`TimeoutError` message).
    raise_on_timeout:
        When ``True`` the helper raises *timeout_exception* (default:
        :class:`TimeoutError`) instead of returning ``False``.
    timeout_exception:
        Exception type to raise on timeout.  Defaults to :class:`TimeoutError`.

    Returns
    -------
    bool
        ``True`` if *condition* became true within *timeout_s*, ``False`` otherwise.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return True
        remaining = deadline - time.monotonic()
        time.sleep(min(interval_s, max(0.0, remaining)))

    if raise_on_timeout:
        exc_cls = timeout_exception or TimeoutError
        raise exc_cls(
            f"Timed out after {timeout_s:.1f}s waiting for {description}."
        )
    return False
