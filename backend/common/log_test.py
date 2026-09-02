import pytest
from unittest.mock import patch, MagicMock
import logging
import threading
import sys


class MockLogger:
    def __init__(self):
        self.handlers = []
        self.level = None
        for lvl in ["debug", "info", "warning", "error", "critical", "exception"]:
            setattr(self, lvl, lambda *args, **kwargs: None)

    def setLevel(self, level):
        self.level = level

    def addHandler(self, handler):
        self.handlers.append(handler)

    def removeHandler(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)

    def isEnabledFor(self, level):
        return True


class DummyHandler:
    lock = threading.RLock()


@pytest.fixture
def reset_log_module():
    if "common.log" in sys.modules:
        del sys.modules["common.log"]
    yield
    if "common.log" in sys.modules:
        del sys.modules["common.log"]


class TestLogModule:
    def test_create_fixed_logger_with_mock_enabled(self, reset_log_module):
        """Test that MockAzureLogHandler is used when mock_enabled is True"""
        mc = MagicMock()
        mc.mock_enabled = True
        logger = MockLogger()
        logger.level = logging.INFO

        with patch("common.config.mock_enabled", True), \
             patch("common.log.mock_enabled", True), \
             patch("logging.getLogger", return_value=logger):

            import common.log
            from common.log import create_fixed_logger, MockAzureLogHandler

            create_fixed_logger()

            handler_types = [h.__class__.__name__ for h in logger.handlers]
            assert "MockAzureLogHandler" in handler_types
            assert "StreamHandler" in handler_types  # console handler

    def test_azure_exporter_always_mock(self, reset_log_module):
        """Test that log_azure_exporter is always MockAzureExporter (no opencensus)"""
        with patch("common.config.mock_enabled", True), \
             patch("common.log.mock_enabled", True), \
             patch("logging.getLogger", return_value=MagicMock()):

            import common.log
            from common.log import log_azure_exporter, MockAzureExporter

            assert isinstance(log_azure_exporter, MockAzureExporter)

    def test_mock_azure_handler_initialization(self):
        """Test that MockAzureLogHandler properly initializes"""
        from common.log import MockAzureLogHandler
        with patch('logging.StreamHandler.setFormatter'):
            handler = MockAzureLogHandler("test-connection")
            assert handler is not None

    def test_mock_azure_exporter_export_is_noop(self):
        """Test that MockAzureExporter.export is a no-op"""
        from common.log import MockAzureExporter
        exporter = MockAzureExporter()
        result = exporter.export("test", span="test-span")
        assert result is None

    def test_log_azure_exporter_not_azure_exporter(self, reset_log_module):
        """Verify log_azure_exporter is NOT opencensus AzureExporter"""
        with patch("common.config.mock_enabled", True), \
             patch("common.log.mock_enabled", True), \
             patch("logging.getLogger", return_value=MagicMock()):

            import common.log
            from common.log import log_azure_exporter

            # It should be MockAzureExporter, not the opencensus one
            assert log_azure_exporter.__class__.__name__ == "MockAzureExporter"


class TestLogLevelConditionalOutput:
    """The `print(...)` debug lines inside MockAzureLogHandler /
    MockAzureExporter are gated on `log_level <= logging.INFO` so they
    don't spam WARNING-level deployments. These tests cover both
    branches of the gate."""

    def test_mock_azure_handler_prints_when_log_level_is_info(self, monkeypatch):
        """When LOG_LEVEL=INFO (the default), the handler prints its
        'Using MockAzureLogHandler' banner at construction time (line 36
        in log.py).
        """
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        # Force a reload so log_level_name re-reads the env.
        if "common.log" in sys.modules:
            del sys.modules["common.log"]
        with patch("builtins.print") as mock_print:
            import common.log  # noqa: F401  -- imports the module
            from common.log import MockAzureLogHandler
            MockAzureLogHandler("test-conn")
        mock_print.assert_any_call(
            "Using MockAzureLogHandler (OpenTelemetry mode)"
        )

    def test_mock_azure_exporter_prints_when_log_level_is_info(self, monkeypatch):
        """LOG_LEVEL=INFO also makes the exporter announce itself
        ('Using MockAzureExporter')."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        if "common.log" in sys.modules:
            del sys.modules["common.log"]
        with patch("builtins.print") as mock_print:
            import common.log  # noqa: F401  -- imports the module
            from common.log import MockAzureExporter
            MockAzureExporter("test-conn")
        mock_print.assert_any_call(
            "Using MockAzureExporter (OpenTelemetry mode)"
        )

    def test_uvicorn_loggers_are_quieted_at_warning(self, monkeypatch):
        """At LOG_LEVEL=WARNING or above, the module silences uvicorn's
        access log and the websockets protocol log so a noisy INFO
        deployment doesn't drown out the application's own messages.
        """
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        if "common.log" in sys.modules:
            del sys.modules["common.log"]

        uvicorn_access_level = []
        ws_logger_level = []

        class _FakeLevelSetter:
            def __init__(self, name):
                self._name = name
                self.handlers = []
                self.level = 0
                self. propagate = True

            def setLevel(self, level):
                self.level = level
                if self._name == "uvicorn.access":
                    uvicorn_access_level.append(level)
                elif self._name == "uvicorn.protocols.websockets.websockets":
                    ws_logger_level.append(level)
                # else: the application's own logger is also given a
                # level by create_fixed_logger — that call is not part
                # of the suppression gate we're testing, so we drop it.

            def addHandler(self, h):
                self.handlers.append(h)

            def removeHandler(self, h):
                if h in self.handlers:
                    self.handlers.remove(h)

            def isEnabledFor(self, lvl):
                return True

        def fake_getLogger(name=None):
            return _FakeLevelSetter(name or "root")

        with patch("logging.getLogger", side_effect=fake_getLogger):
            import common.log  # noqa: F401

        import logging as _logging
        assert uvicorn_access_level == [_logging.WARNING]
        assert ws_logger_level == [_logging.WARNING]

    def test_uvicorn_loggers_are_NOT_quieted_below_warning(self, monkeypatch):
        """Below WARNING, the silencing block does not run (the gate
        `if log_level >= logging.WARNING` is false)."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        if "common.log" in sys.modules:
            del sys.modules["common.log"]

        calls = []

        class _FakeLevelSetter:
            def __init__(self, name):
                self._name = name
                self.handlers = []
                self.level = 0
                self. propagate = True

            def setLevel(self, level):
                self.level = level
                calls.append((self._name, level))

            def addHandler(self, h):
                self.handlers.append(h)

            def removeHandler(self, h):
                if h in self.handlers:
                    self.handlers.remove(h)

            def isEnabledFor(self, lvl):
                return True

        def fake_getLogger(name=None):
            return _FakeLevelSetter(name or "root")

        with patch("logging.getLogger", side_effect=fake_getLogger):
            import common.log  # noqa: F401

        # No setLevel calls targeted at the uvicorn loggers.
        assert not any(
            name in ("uvicorn.access",
                     "uvicorn.protocols.websockets.websockets")
            for name, _ in calls
        )

    def test_create_fixed_logger_adds_lock_to_unlocked_handlers(self, monkeypatch):
        """`create_fixed_logger()` walks `logger.handlers` and attaches
        an RLock to any handler that lacks one. This is the line-36
        coverage: a handler with `lock is None` gets `handler.lock =
        threading.RLock()` applied, and a handler that already has a
        lock is left alone.

        Importing `common.log` runs `create_fixed_logger()` at module
        load — we therefore build the test handlers fresh AFTER the
        import, so the explicit `create_fixed_logger()` call here is
        the one that actually has to set the missing lock.
        """
        class HandlerWithLock:
            lock = "already-locked"

        class HandlerWithoutLock:
            # No `lock` attribute at all -> getattr(..., None) is None
            pass

        monkeypatch.setenv("LOG_LEVEL", "INFO")
        if "common.log" in sys.modules:
            del sys.modules["common.log"]

        fake_logger = MockLogger()

        with patch("logging.getLogger", return_value=fake_logger):
            import common.log  # noqa: F401
            from common.log import create_fixed_logger

            # Now wire fresh handlers and call create_fixed_logger
            # again — this is the call that has to set line-36.
            handler_with = HandlerWithLock()
            handler_without = HandlerWithoutLock()
            fake_logger.handlers = [handler_with, handler_without]
            create_fixed_logger()

        # HandlerWithLock still has its original lock attribute.
        assert handler_with.lock == "already-locked"
        # HandlerWithoutLock now has an RLock (the line-36 branch).
        import threading
        assert isinstance(handler_without.lock, type(threading.RLock()))