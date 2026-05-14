import threading
import logging
import os
from common.config import mock_enabled

# Get log level from environment variable, default to INFO
log_level_name = os.environ.get('LOG_LEVEL', 'INFO')
log_level = getattr(logging, log_level_name.upper(), logging.INFO)

class MockAzureLogHandler(logging.StreamHandler):
    """Mock handler that outputs to console instead of Azure"""
    def __init__(self, connection_string=None):
        super().__init__()
        self.setFormatter(logging.Formatter('[MOCK AZURE LOG] %(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        # Only print when log level allows it
        if log_level <= logging.INFO:
            print("Using MockAzureLogHandler (OpenTelemetry mode)")

class MockAzureExporter:
    """Mock exporter that doesn't send data to Azure"""
    def __init__(self, connection_string=None):
        # Only print when log level allows it
        if log_level <= logging.INFO:
            print("Using MockAzureExporter (OpenTelemetry mode)")

    def export(self, *args, **kwargs):
        pass

def create_fixed_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)  # Use the log level from environment variable

    # Fix existing handlers
    for handler in logger.handlers:
        if getattr(handler, 'lock', None) is None:
            handler.lock = threading.RLock()

    # Remove any existing Azure handlers
    for handler in list(logger.handlers):
        if handler.__class__.__name__ == 'AzureLogHandler' or handler.__class__.__name__ == 'MockAzureLogHandler':
            logger.removeHandler(handler)

    # Add appropriate handler based on mock setting
    if mock_enabled:
        mock_handler = MockAzureLogHandler()
        mock_handler.lock = threading.RLock()
        logger.addHandler(mock_handler)

    # Always add a console handler for local debugging
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    console_handler.lock = threading.RLock()
    console_handler.setLevel(log_level)  # Set the handler's level too
    logger.addHandler(console_handler)

    return logger

# Create logger
logger = create_fixed_logger()

# Application Insights exporter (legacy, kept for compatibility)
log_azure_exporter = MockAzureExporter()

# Suppress FastAPI access logs
if log_level >= logging.WARNING:
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.setLevel(logging.WARNING)

    # Suppress WebSocket connection logs
    ws_logger = logging.getLogger("uvicorn.protocols.websockets.websockets")
    ws_logger.setLevel(logging.WARNING)