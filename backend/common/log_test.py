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