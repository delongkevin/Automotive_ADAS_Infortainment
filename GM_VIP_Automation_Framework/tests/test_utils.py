"""
Tests for GM_VIP_Automation_Framework.utils module.
No hardware or lauterbach library required.
"""

import logging
import sys
import time
import unittest
from unittest.mock import MagicMock, patch


class TestExceptions(unittest.TestCase):

    def test_exception_hierarchy(self):
        from GM_VIP_Automation_Framework.utils.exceptions import (
            T32FrameworkError,
            T32ConnectionError,
            T32TimeoutError,
            T32CommandError,
            T32SymbolError,
            T32VariableError,
            T32RegisterError,
            T32BreakpointError,
            T32BreakpointNotReachedError,
        )
        self.assertTrue(issubclass(T32ConnectionError, T32FrameworkError))
        self.assertTrue(issubclass(T32TimeoutError, T32FrameworkError))
        self.assertTrue(issubclass(T32CommandError, T32FrameworkError))
        self.assertTrue(issubclass(T32SymbolError, T32FrameworkError))
        self.assertTrue(issubclass(T32VariableError, T32FrameworkError))
        self.assertTrue(issubclass(T32RegisterError, T32FrameworkError))
        self.assertTrue(issubclass(T32BreakpointError, T32FrameworkError))
        self.assertTrue(issubclass(T32BreakpointNotReachedError, T32BreakpointError))

    def test_command_error_message(self):
        from GM_VIP_Automation_Framework.utils.exceptions import T32CommandError
        exc = T32CommandError("GO", -1, "api error")
        self.assertIn("GO", str(exc))
        self.assertIn("-1", str(exc))
        self.assertIn("api error", str(exc))

    def test_symbol_error_message(self):
        from GM_VIP_Automation_Framework.utils.exceptions import T32SymbolError
        exc = T32SymbolError("myFunc", "not found")
        self.assertIn("myFunc", str(exc))

    def test_breakpoint_not_reached_message(self):
        from GM_VIP_Automation_Framework.utils.exceptions import T32BreakpointNotReachedError
        exc = T32BreakpointNotReachedError("myFunc", 5000)
        self.assertIn("myFunc", str(exc))
        self.assertIn("5000", str(exc))


class TestLogger(unittest.TestCase):

    def test_get_logger_returns_logger(self):
        from GM_VIP_Automation_Framework.utils.logger import get_logger
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)

    def test_configure_logger_no_duplicate_handlers(self):
        from GM_VIP_Automation_Framework.utils.logger import configure_logger, _LOGGER_NAME
        import logging
        # Reset any existing handlers first.
        root = logging.getLogger(_LOGGER_NAME)
        root.handlers.clear()
        logger1 = configure_logger()
        handler_count = len(logger1.handlers)
        logger2 = configure_logger()
        # Second call should not add duplicate handlers.
        self.assertEqual(len(logger2.handlers), handler_count)


class TestRetry(unittest.TestCase):

    def test_retry_succeeds_on_first_attempt(self):
        from GM_VIP_Automation_Framework.utils.retry import retry
        call_count = [0]

        @retry(ValueError, max_attempts=3)
        def always_passes():
            call_count[0] += 1
            return "ok"

        result = always_passes()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 1)

    def test_retry_retries_on_exception(self):
        from GM_VIP_Automation_Framework.utils.retry import retry
        call_count = [0]

        @retry(ValueError, max_attempts=3, delay_s=0.01)
        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("transient")
            return "ok"

        result = fails_twice()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count[0], 3)

    def test_retry_exhausts_and_reraises(self):
        from GM_VIP_Automation_Framework.utils.retry import retry

        @retry(ValueError, max_attempts=2, delay_s=0.01)
        def always_fails():
            raise ValueError("permanent")

        with self.assertRaises(ValueError):
            always_fails()

    def test_poll_until_true_immediately(self):
        from GM_VIP_Automation_Framework.utils.retry import poll_until
        result = poll_until(lambda: True, timeout_s=1.0)
        self.assertTrue(result)

    def test_poll_until_timeout_returns_false(self):
        from GM_VIP_Automation_Framework.utils.retry import poll_until
        result = poll_until(lambda: False, timeout_s=0.05, interval_s=0.01)
        self.assertFalse(result)

    def test_poll_until_timeout_raises(self):
        from GM_VIP_Automation_Framework.utils.retry import poll_until
        with self.assertRaises(TimeoutError):
            poll_until(
                lambda: False,
                timeout_s=0.05,
                interval_s=0.01,
                raise_on_timeout=True,
            )

    def test_poll_until_true_after_delay(self):
        from GM_VIP_Automation_Framework.utils.retry import poll_until
        start = time.monotonic()
        attempts = [0]

        def eventually_true():
            attempts[0] += 1
            return attempts[0] >= 3

        result = poll_until(eventually_true, timeout_s=2.0, interval_s=0.01)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
