import psutil
from fastapi import FastAPI, APIRouter, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path, PurePosixPath
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

@app.middleware("http")
async def security_headers(request, call_next):
    """Add defensive browser headers to every HTTP response.

    Keep this policy at the application boundary as well as at the ingress so
    a change to controller defaults cannot silently weaken it.  ``setdefault``
    also lets a more specific proxy-owned value win if one is already present.
    """
    response = await call_next(request)
    response.headers.setdefault(
        "Content-Security-Policy",
        # `blob:` in img-src is required for the navbar profile photo
        # (frontend/src/components/EntraProfile.jsx) — getProfilePhoto fetches
        # the bytes via https://graph.microsoft.com (allowed by connect-src)
        # and hands the <img> a URL.createObjectURL() result, which is a
        # `blob:` URL. `blob:` is its own CSP source expression and is NOT
        # covered by 'self', `data:`, or by listing graph.microsoft.com
        # (that origin governs the fetch, not the object URL the fetch
        # result is wrapped in). It only permits rendering object URLs the
        # page itself minted from data it already fetched under connect-src;
        # it does not widen the set of origins the app may talk to.
        # See issue #143.
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' https://login.microsoftonline.com https://graph.microsoft.com; frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

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


@app.get("/ready")
@app.head("/ready")
async def ready():
    """Readiness probe: 200 once the backend can actually serve traffic.

    Distinct from /health (liveness) on purpose — liveness only proves the
    Python process is alive; readiness must show that every dependency the
    app needs to handle a request is reachable. With MongoDB down the API
    is effectively broken, so we go 503 here and let kubelet keep the pod out
    of the Service endpoints until the DB is back. Unlike liveness, this
    does NOT restart the pod.
    """
    if fgl_service.health_check():
        return {"status": "ready"}
    return Response(
        status_code=503,
        content='{"status":"not_ready","detail":"mongodb unreachable"}',
        media_type="application/json",
    )

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


# Extensions that name a static asset rather than a client-side route (issue
# #141). A miss on one of these is a broken reference and must surface as 404
# instead of being papered over with the SPA shell. SPA routes ("/dashboard",
# "/chat") carry no suffix and are unaffected.
#
# ``.html`` is deliberately absent: index.html is a real file and is served
# through the base-injecting renderer below, not as a plain asset.
NON_SPA_SUFFIXES = frozenset({
    ".js", ".mjs", ".css", ".map", ".json", ".webmanifest",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".txt", ".xml", ".wasm",
})

# Content types for the assets the Vite build emits. Leaving these to
# Starlette's filename guesser worked, but spelling them out keeps the served
# type auditable in one place and pins the two that matter for a PWA install:
# a manifest served as anything but application/manifest+json, and icons that
# must arrive as real images (issue #141).
_STATIC_MEDIA_TYPES = {
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".html": "text/html",
    ".json": "application/json",
    ".map": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/vnd.microsoft.icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
}


@frontend_router.get("/{path:path}")
async def frontend_handler(path: str, request: Request):
    if path.startswith("api/") or path.startswith("future-gadget-lab/"):
        raise HTTPException(status_code=404, detail="API path not found")

    # Whitelist lookup: user input is only used as a dict key. The served path
    # is taken from the dict value, which was constructed at startup from
    # trusted filesystem enumeration — not from user input.
    fp = _dist_files.get(path)

    # Only real SPA routes fall back to index.html. A request that names a
    # static asset must 404 when the asset is missing: answering it with the
    # HTML shell at HTTP 200 turns a broken reference into a silent, invisible
    # failure. That is how the manifest's wrong icon paths
    # ("public/android-chrome-192x192.png", pointing at a public/ subdirectory
    # Vite never emits) went unnoticed — Edge asked for a PNG and got HTML,
    # with no error anywhere to show for it (issue #141).
    if fp is None and path and PurePosixPath(path).suffix.lower() in NON_SPA_SUFFIXES:
        raise HTTPException(status_code=404, detail="Not found")

    # Unknown path = SPA fallback, and index.html itself, both get the runtime
    # base injected and must not be cached (or browsers keep a stale bundle).
    if fp is None or fp == _index_html:
        return _render_index(_resolve_base(request))

    media_type = _STATIC_MEDIA_TYPES.get(PurePosixPath(path).suffix.lower())

    return FileResponse(fp, media_type=media_type)

app.include_router(frontend_router, prefix="")

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)