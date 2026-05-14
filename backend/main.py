import psutil
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
import datetime

from os import environ as os_environ
from dotenv import load_dotenv
load_dotenv()

from api.api import api_router
from api.future_gadget_api import future_gadget_api_router
from common.config import origins

mock_enabled = os_environ.get("MOCK", "false").lower() == "true"

app = FastAPI()

# CORS — origins from terraform config
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# OpenTelemetry instrumentation
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    resource = Resource.create({"service.name": "future-gadget-lab"})
    provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
except Exception as e:
    print(f"OpenTelemetry setup failed: {e}")

# Register API Routers
app.include_router(api_router, prefix="/api")
app.include_router(future_gadget_api_router, prefix="/future-gadget-lab")

# Generate test data on startup if DB is empty
from db.future_gadget_lab_data_service import generate_test_data
from api.future_gadget_api import fgl_service

try:
    if not fgl_service.get_all_experiments() and not fgl_service.get_all_divergence_readings():
        test_data = generate_test_data(fgl_service)
        print("=== Generated Future Gadget Lab Test Data ===")
        print(f"Created {len(test_data['experiments'])} experiments")
        print(f"Created {len(test_data['divergence_readings'])} divergence readings")
        print("===========================================")
except Exception as e:
    print(f"Warning: test data seeding check failed: {e}")

@app.get("/health")
@app.head("/health")
async def health():
    boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot_time
    cpu_percent = __import__("psutil").cpu_percent(interval=1)
    memory_info = __import__("psutil").virtual_memory()
    return {
        "status": "ok",
        "uptime": str(uptime),
        "cpu_percent": cpu_percent,
        "memory": {
            "total": memory_info.total,
            "available": memory_info.available,
            "percent": memory_info.percent,
            "used": memory_info.used,
            "free": memory_info.free,
        },
    }

# Frontend Router
dist = Path("./dist").resolve()
frontend_router = APIRouter()


def _enumerate_dist_files(root: Path) -> dict:
    """At startup, walk dist/ and map each relative path string to its absolute
    Path. The handler only serves files from this map — turning user input
    into a dict key lookup rather than a filesystem path construction.
    This is the canonical whitelist sanitizer for path-traversal."""
    out = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            out[rel] = p
    return out


_dist_files = _enumerate_dist_files(dist)
_index_html = dist / "index.html"


@frontend_router.get("/{path:path}")
async def frontend_handler(path: str):
    if path.startswith("api/") or path.startswith("future-gadget-lab/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="API path not found")

    # Whitelist lookup: user input is only used as a dict key. The served path
    # is taken from the dict value, which was constructed at startup from
    # trusted filesystem enumeration — not from user input.
    fp = _dist_files.get(path, _index_html)

    media_type = None
    if path.endswith(".js"):
        media_type = "application/javascript"
    elif path.endswith(".css"):
        media_type = "text/css"
    elif path.endswith(".html"):
        media_type = "text/html"
    elif path.endswith(".json"):
        media_type = "application/json"

    return FileResponse(fp, media_type=media_type)

app.include_router(frontend_router, prefix="")

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)