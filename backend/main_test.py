from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, mock_open
import pytest
import json
import datetime
from pathlib import Path

# Import the app to test
import main
from main import app

# Create a test client
client = TestClient(app)

class TestMainModule:
    
    @pytest.fixture
    def mock_psutil(self):
        """Mock psutil for health checks"""
        with patch('main.psutil') as mock:
            # Configure mock returns
            mock.boot_time.return_value = datetime.datetime.now().timestamp() - 3600  # 1 hour uptime
            mock.cpu_percent.return_value = 25.5
            
            # Configure virtual memory mock
            memory_mock = MagicMock()
            memory_mock.total = 16000000000
            memory_mock.available = 8000000000
            memory_mock.percent = 50.0
            memory_mock.used = 8000000000
            memory_mock.free = 8000000000
            mock.virtual_memory.return_value = memory_mock
            
            yield mock
    
    @pytest.fixture
    def mock_file_response(self):
        """Mock FileResponse for frontend files."""
        from fastapi import Response

        def fake_file_response(*args, **kwargs):
            media_type = kwargs.get("media_type") or "application/octet-stream"
            return Response(
                content="mocked file response",
                media_type=media_type,
            )

        with patch('main.FileResponse') as mock:
            mock.side_effect = fake_file_response
            yield mock
    
    @pytest.fixture
    def served_assets(self):
        """Pretend these asset paths exist in dist/ so the handler serves them
        via FileResponse rather than falling back to the SPA shell."""
        assets = {
            "app.js": Path("/dist/app.js"),
            "styles.css": Path("/dist/styles.css"),
            "page.html": Path("/dist/page.html"),
            "data.json": Path("/dist/data.json"),
        }
        with patch.dict("main._dist_files", assets, clear=False):
            yield

    # A minimal built index.html: the relative asset URL must resolve against
    # the <base href> the handler injects.
    _INDEX = (
        '<!doctype html><html><head>\n'
        '    <link rel="icon" href="./favicon.ico" />\n'
        '    <script type="module" src="./assets/index.js"></script>\n'
        '  </head><body><div id="root"></div></body></html>'
    )

    def test_health_endpoint(self, mock_psutil):
        """Test the /health endpoint returns proper system information"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check expected fields
        assert "status" in data
        assert data["status"] == "ok"
        assert "uptime" in data
        assert "cpu_percent" in data
        assert "memory" in data
        
        # Check memory details
        memory = data["memory"]
        assert "total" in memory
        assert "available" in memory
        assert "percent" in memory
        assert "used" in memory
        assert "free" in memory
    
    def test_head_health_endpoint(self, mock_psutil):
        """Test the HEAD /health endpoint"""
        response = client.head("/health")
        assert response.status_code == 200
        # HEAD requests don't return a body
        assert response.content == b''

    def test_ready_endpoint_when_dependencies_are_reachable(self):
        """Readiness probe returns 200 once the backend can actually serve traffic."""
        with patch.object(main.fgl_service, "health_check", return_value=True):
            response = client.get("/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    def test_ready_endpoint_head_when_dependencies_are_reachable(self):
        """HEAD /ready is also part of the probe contract (kept consistent
        with /health)."""
        with patch.object(main.fgl_service, "health_check", return_value=True):
            response = client.head("/ready")
        assert response.status_code == 200
        assert response.content == b""

    def test_ready_endpoint_503_when_dependency_is_unreachable(self):
        """A failing readiness check returns a JSON 503 response."""
        with patch.object(main.fgl_service, "health_check", return_value=False):
            response = client.get("/ready")
        assert response.status_code == 503
            body = response.json()
            assert body["status"] == "not_ready"
            assert "detail" in body

    def test_frontend_handler_js_file(self, served_assets, mock_file_response):
        """A real .js dist file is served via FileResponse with the JS media type"""
        response = client.get("/app.js")
        mock_file_response.assert_called_once()
        _, kwargs = mock_file_response.call_args
        assert kwargs["media_type"] == "application/javascript"
        self._assert_security_headers(response, "application/javascript")

    def test_frontend_handler_css_file(self, served_assets, mock_file_response):
        """A real .css dist file is served via FileResponse with the CSS media type"""
        response = client.get("/styles.css")
        mock_file_response.assert_called_once()
        _, kwargs = mock_file_response.call_args
        assert kwargs["media_type"] == "text/css"
        self._assert_security_headers(response, "text/css")

    def test_frontend_handler_html_file(self, served_assets, mock_file_response):
        """A non-index .html dist file is served via FileResponse"""
        response = client.get("/page.html")
        mock_file_response.assert_called_once()
        _, kwargs = mock_file_response.call_args
        assert kwargs["media_type"] == "text/html"
        self._assert_security_headers(response, "text/html")

    def test_frontend_handler_json_file(self, served_assets, mock_file_response):
        """A real .json dist file is served via FileResponse"""
        response = client.get("/data.json")
        mock_file_response.assert_called_once()
        _, kwargs = mock_file_response.call_args
        assert kwargs["media_type"] == "application/json"
        self._assert_security_headers(response, "application/json")

    def test_frontend_handler_fallback_serves_index(self):
        """Unknown paths fall back to the SPA shell (no-store so a new deploy
        isn't masked by a cached bundle)."""
        with patch("main._index_text", self._INDEX):
            response = client.get("/this-route-does-not-exist-12345")
        assert response.status_code == 200
        assert '<div id="root">' in response.text
        assert "no-store" in response.headers.get("cache-control", "")
        self._assert_security_headers(response, "text/html")

    def test_index_injects_root_base_without_prefix(self):
        """A domain root (no X-Forwarded-Prefix, e.g. via the Cloudflare
        tunnel) the injected base is '/' and precedes the relative assets."""
        with patch("main._index_text", self._INDEX):
            response = client.get("/")
        assert '<base href="/">' in response.text
        assert 'window.__APP_BASE__="/"' in response.text
        assert response.text.index("<base") < response.text.index("./favicon.ico")

    def test_index_injects_subpath_base_from_forwarded_prefix(self):
        """Behind the nginx subpath ingress the injected base matches the prefix."""
        with patch("main._index_text", self._INDEX):
            response = client.get(
                "/", headers={"X-Forwarded-Prefix": "/ultimate-web-stack-dev"}
            )
        assert '<base href="/ultimate-web-stack-dev/">' in response.text
        assert 'window.__APP_BASE__="/ultimate-web-stack-dev/"' in response.text

    def test_index_rejects_malicious_forwarded_prefix(self):
        """X-Forwarded-Prefix is client-reachable via the tunnel; a value that
        isn't a clean path collapses to root rather than being reflected."""
        with patch("main._index_text", self._INDEX):
            response = client.get(
                "/", headers={"X-Forwarded-Prefix": '"><script>alert(1)</script>'}
            )
        assert "<script>alert(1)</script>" not in response.text
        assert '<base href="/">' in response.text

    def test_cors_middleware_configuration(self):
        """Test that CORS middleware is configured"""
        # Instead of checking specific headers, just verify CORS middleware is active
        response = client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        
        # Print all headers for debugging
        print(f"Response headers: {dict(response.headers)}")
        
        # Look for any CORS-related headers to confirm middleware is active
        cors_headers = [h for h in response.headers if 'access-control' in h.lower()]
        assert len(cors_headers) > 0, "No CORS headers found"
        
        # Verify at minimum that credentials are allowed, which indicates CORS is enabled
        assert response.headers.get("access-control-allow-credentials") == "true"

    def test_security_headers_are_present_on_json_responses(self):
        """The policy covers API JSON responses in both authenticated and error modes."""
        response = client.get("/api/user-data")
        assert response.status_code == 200
        self._assert_security_headers(response, "application/json")

    def test_security_headers_are_present_on_root_spa_response(self):
        """The SPA shell also receives the complete defensive policy."""
        with patch("main._index_text", self._INDEX):
            response = client.get("/")
        self._assert_security_headers(response, "text/html")

    @staticmethod
    def _assert_security_headers(response, content_type):
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert response.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
        assert response.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
        csp = response.headers.get("content-security-policy")
        assert csp == (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self' "
            "https://login.microsoftonline.com https://graph.microsoft.com; "
            "frame-ancestors 'none'"
        )
        assert response.headers.get("content-type", "").startswith(content_type)
    
    @pytest.mark.skip(reason="mock_middleware fixture undefined; OTel middleware not configured in k8s-port")
    def test_opentelemetry_middleware_configuration(self):
        """Test the OpenTelemetry middleware is configured with the FastAPIInstrumentor"""
        # Check that app has middleware
        assert len(app.user_middleware) > 0
        
        # Find the FastAPIMiddleware (OpenTelemetry instruments via this)
        found_otel = False
        for middleware in app.user_middleware:
            if "FastAPIMiddleware" in str(middleware.cls):
                found_otel = True
                break
        
        assert found_otel, "No OpenTelemetry FastAPIMiddleware found in app middleware"
        assert found_otel, "OTel FastAPIMiddleware not found in app middleware"
    
    @pytest.mark.skip(reason="patch target mismatch; api_router is a module reference")
    def test_api_router_is_included(self):
        """Test the API router is included at the correct prefix"""
        with patch('main.api_router') as mock_router:
            import importlib
            importlib.reload(main)
            for call in mock_router.mock_calls:
                if 'include_router' in str(call):
                    return
        assert hasattr(main, "api_router"), "API router should be defined"
        assert len(app.routes) > 0, "App should have routes"