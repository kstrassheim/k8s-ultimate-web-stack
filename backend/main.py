import psutil
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
import datetime
import json
import re

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
_index_text = _index_html.read_text(encoding="utf-8") if _index_html.is_file() else ""

# A deploy prefix is a path of plain "/segment" parts. X-Forwarded-Prefix is
# set by the nginx subpath ingress, but it is also forwarded from the client by
# the Cloudflare tunnel — i.e. attacker-reachable — and it gets reflected into
# the page, so anything that doesn't match collapses to root (no XSS surface).
_PREFIX_RE = re.compile(r"^(?:/[A-Za-z0-9_-]+)+$")
_NO_STORE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _resolve_base(request: Request) -> str:
    """Public base path for this request, with trailing slash. "/" at a domain
    root (tunnel, no prefix header); "/ultimate-web-stack-dev/" behind the
    nginx subpath ingress."""
    raw = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    return raw + "/" if raw and _PREFIX_RE.match(raw) else "/"


def _render_index(base: str) -> HTMLResponse:
    """index.html with an absolute <base href> + window.__APP_BASE__ injected as
    the first thing in <head>, so the relative ./asset URLs (Vite base="./")
    and the SPA's router/API base all resolve against the actual mount point."""
    inject = (
        f'<base href="{base}">'
        f'<script>window.__APP_BASE__={json.dumps(base)};</script>'
    )
    html = _index_text.replace("<head>", "<head>\n    " + inject, 1)
    return HTMLResponse(html, headers=_NO_STORE)


@frontend_router.get("/{path:path}")
async def frontend_handler(path: str, request: Request):
    if path.startswith("api/") or path.startswith("future-gadget-lab/"):
        raise HTTPException(status_code=404, detail="API path not found")

    # Whitelist lookup: user input is only used as a dict key. The served path
    # is taken from the dict value, which was constructed at startup from
    # trusted filesystem enumeration — not from user input.
    fp = _dist_files.get(path)

    # Unknown path = SPA fallback, and index.html itself, both get the runtime
    # base injected and must not be cached (or browsers keep a stale bundle).
    if fp is None or fp == _index_html:
        return _render_index(_resolve_base(request))

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