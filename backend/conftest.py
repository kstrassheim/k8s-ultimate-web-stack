import sys
import os
import pytest

# Set MOCK=true globally for all tests before any modules are imported
os.environ["MOCK"] = "true"

# Disable the OpenTelemetry SDK in the test runner.
#
# main.py wires a BatchSpanProcessor + OTLPSpanExporter at import time. With
# no OTel collector reachable, the gRPC channel falls into UNAVAILABLE
# retries during pytest's process teardown and adds ~30s to every run
# (the OTLP exporter backs off 4s / 8s / 16s / 32s). Disabling the SDK
# turns the TracerProvider into a no-op so no spans are ever queued,
# exported, or flushed.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

# Add the project root directory to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))