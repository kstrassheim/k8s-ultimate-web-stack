import pytest
from unittest.mock import patch, MagicMock
import sys
import importlib
import requests

# First, we'll create a mock for the log module entirely
class MockLogger:
    def __init__(self):
        for level in ['debug', 'info', 'warning', 'error', 'critical']:
            setattr(self, level, MagicMock())
    
    def isEnabledFor(self, level):
        return True

# Create a mock for the config module
class MockConfig:
    def __init__(self):
        self.tfconfig = MockTFConfig()
        self.mock_enabled = False

class MockTFConfig:
    def __init__(self):
        self._getitem_mock = MagicMock(return_value={"value": "mock-value"})
    
    def __getitem__(self, key):
        return self._getitem_mock(key)

# Define test fixtures for consistent environment
@pytest.fixture
def setup_mocks(monkeypatch):
    """Setup mocks for the entire test session"""
    # Create our mocks
    mock_logger = MockLogger()
    mock_config = MockConfig()
    
    # Create mock modules with our mock objects
    mock_log_module = MagicMock()
    mock_log_module.logger = mock_logger
    mock_log_module.create_fixed_logger = MagicMock(return_value=mock_logger)
    mock_log_module.AzureLogHandler = MagicMock()
    
    mock_config_module = MagicMock()
    mock_config_module.tfconfig = mock_config.tfconfig
    mock_config_module.mock_enabled = mock_config.mock_enabled
    
    # Insert our mocks into sys.modules
    monkeypatch.setitem(sys.modules, 'common.log', mock_log_module)
    monkeypatch.setitem(sys.modules, 'common.config', mock_config_module)
    
    # Return the mocks so tests can configure them
    return {
        'logger': mock_logger,
        'tfconfig': mock_config.tfconfig,
        'mock_enabled': mock_config_module,
        'log_module': mock_log_module,
        'config_module': mock_config_module
    }

# Test class
class TestAuthSchemeSelection:
    
    @pytest.fixture
    def reset_auth_module(self):
        """Reset the auth module between tests"""
        if 'common.auth' in sys.modules:
            del sys.modules['common.auth']
        yield
        if 'common.auth' in sys.modules:
            del sys.modules['common.auth']
    
    def test_production_environment_uses_real_scheme(self, setup_mocks, reset_auth_module):
        """Test that production environment uses the real Azure scheme"""
        # Configure the mocks
        mock_tfconfig = setup_mocks['tfconfig']
        mock_config_module = setup_mocks['config_module']
        
        # Configure tfconfig for this test
        mock_values = {
            "env": {"value": "prod"},
            "client_id": {"value": "test-client-id"},
            "tenant_id": {"value": "test-tenant-id"},
            "oauth2_permission_scope_uri": {"value": "test-scope-uri"},
            "oauth2_permission_scope": {"value": "test-scope"}
        }
        mock_tfconfig._getitem_mock.side_effect = lambda key: mock_values.get(key, {"value": "default"})
        mock_config_module.mock_enabled = False
        
        # Mock the Azure authentication class
        with patch('fastapi_azure_auth.auth.SingleTenantAzureAuthorizationCodeBearer') as mock_azure_scheme:
            # Import the module to trigger the conditional
            import common.auth
            
            # Verify the real scheme was created with correct parameters
            mock_azure_scheme.assert_called_once_with(
                app_client_id="test-client-id",
                tenant_id="test-tenant-id",
                scopes={"test-scope-uri": "test-scope"},
                allow_guest_users=True
            )
    
    def test_dev_environment_with_mocking_enabled_uses_mock_scheme(self, setup_mocks, reset_auth_module):
        """Test that dev environment with mocking enabled uses the mock scheme"""
        
        # Configure the mocks
        mock_tfconfig = setup_mocks['tfconfig']
        mock_config_module = setup_mocks['config_module']
        mock_logger = setup_mocks['logger']
        
        # Configure tfconfig for this test
        mock_values = {
            "env": {"value": "dev"},
            "oauth2_permission_scope": {"value": "test-scope"}
        }
        mock_tfconfig._getitem_mock.side_effect = lambda key: mock_values.get(key, {"value": "default"})
        mock_config_module.mock_enabled = True
        
        # Mock the MockAzureAuthScheme class
        mock_scheme_instance = MagicMock()
        mock_scheme_class = MagicMock(return_value=mock_scheme_instance)
        
        # Apply the mocks - ensure we cleanly reload
        with patch('mock.MockAzureAuthScheme.MockAzureAuthScheme', mock_scheme_class):
            
            # Import the module to trigger the conditional - no reload
            import common.auth
            
            # Verify the mock scheme was created
            mock_scheme_class.assert_called_once_with(mock_logger)
            
            # Verify the logger was called
            mock_logger.info.assert_called_with("MOCK environment is enabled")
            
            # Verify the azure_scheme is our mock instance
            assert common.auth.azure_scheme == mock_scheme_instance
    
    def test_dev_environment_with_mocking_disabled_uses_real_scheme(self, setup_mocks, reset_auth_module):
        """Test that dev environment with mocking disabled uses the real scheme"""
        
        # Configure the mocks
        mock_tfconfig = setup_mocks['tfconfig']
        mock_config_module = setup_mocks['config_module']
        
        # Configure tfconfig for this test
        mock_values = {
            "env": {"value": "dev"},
            "client_id": {"value": "test-client-id"},
            "tenant_id": {"value": "test-tenant-id"},
            "oauth2_permission_scope_uri": {"value": "test-scope-uri"},
            "oauth2_permission_scope": {"value": "test-scope"}
        }
        mock_tfconfig._getitem_mock.side_effect = lambda key: mock_values.get(key, {"value": "default"})
        mock_config_module.mock_enabled = False
        
        # Create a mock instance
        mock_instance = MagicMock()
        mock_azure_scheme = MagicMock(return_value=mock_instance)
        
        # Apply the mocks
        with patch('fastapi_azure_auth.auth.SingleTenantAzureAuthorizationCodeBearer', mock_azure_scheme):
            
            # Import the module to trigger the conditional - no reload
            import common.auth
            
            # Verify the real scheme was created
            mock_azure_scheme.assert_called_once()
    
    def test_scopes_are_correctly_defined(self, setup_mocks, reset_auth_module):
        """Test that scopes are correctly defined from config"""
        
        # Configure the mocks
        mock_tfconfig = setup_mocks['tfconfig']
        
        # Configure tfconfig for this test
        mock_values = {
            "env": {"value": "dev"},
            "oauth2_permission_scope": {"value": "test-scope"}
        }
        mock_tfconfig._getitem_mock.side_effect = lambda key: mock_values.get(key, {"value": "default"})
        
        # Import the module to trigger the conditional
        import common.auth
        importlib.reload(common.auth)
        
        # Verify scopes are defined correctly
        assert common.auth.scopes == ["test-scope"]


# ---------------------------------------------------------------------------
# Tests for the JWKS hardening added by issue #114:
#   * timeout on `requests.get` (Bandit B113 + DoS amplification)
#   * JWKS caching so the upstream is fetched at most once per minute per
#     process under repeated authenticated calls
#   * issuer pinning so a JWT minted by another tenant (whose `kid`
#     resolves in the JWKS) cannot be accepted as long as `aud` matches
# ---------------------------------------------------------------------------

# Test tenant + client + kid used by every JWKS test
_TEST_TENANT_ID = "11111111-1111-1111-1111-111111111111"
_TEST_ISSUER = f"https://login.microsoftonline.com/{_TEST_TENANT_ID}/v2.0"
_TEST_CLIENT_ID = "test-client-id"
_TEST_KID = "test-key-id"


def _generate_test_jwks():
    """Generate an RSA keypair plus a JWKS dict containing its public key.

    Returns ``(private_pem_bytes, jwks_dict)``. Both are deterministic
    per call — callers must not share the private key across tests where
    isolation matters.
    """
    import base64
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    def _b64url_uint(n):
        n_bytes = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
        return base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": _TEST_KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return private_pem, {"keys": [jwk]}


def _sign_test_token(private_pem, *, issuer, audience=_TEST_CLIENT_ID,
                     kid=_TEST_KID, expires_in=300, extra_claims=None):
    """Sign a JWT with the given claims using the supplied RSA private key."""
    import time
    from jose import jwt

    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": "test-user",
        "name": "Test User",
        "roles": ["User"],
        "iat": now,
        "exp": now + expires_in,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, private_pem, algorithm="RS256",
                      headers={"kid": kid})


def _build_real_env(monkeypatch):
    """Wire ``common.auth`` to the real-Azure verify_token branch.

    Returns the imported ``common.auth`` module. The caller is
    responsible for clearing the JWKS cache around the test (the
    cache is module-local and shared across calls within a process).
    """
    # Configure tfconfig for a prod tenant
    mock_tfconfig = MockTFConfig()
    mock_values = {
        "env": {"value": "prod"},
        "client_id": {"value": _TEST_CLIENT_ID},
        "tenant_id": {"value": _TEST_TENANT_ID},
        "oauth2_permission_scope_uri": {"value": "test-scope-uri"},
        "oauth2_permission_scope": {"value": "test-scope"},
    }
    mock_tfconfig._getitem_mock.side_effect = (
        lambda key: mock_values.get(key, {"value": "default"})
    )

    mock_logger = MockLogger()
    mock_log_module = MagicMock()
    mock_log_module.logger = mock_logger
    mock_log_module.create_fixed_logger = MagicMock(return_value=mock_logger)
    mock_log_module.AzureLogHandler = MagicMock()

    mock_config_module = MagicMock()
    mock_config_module.tfconfig = mock_tfconfig
    mock_config_module.mock_enabled = False

    monkeypatch.setitem(sys.modules, "common.log", mock_log_module)
    monkeypatch.setitem(sys.modules, "common.config", mock_config_module)

    # Drop any prior import so the module-level branch runs fresh
    # under our mocked config.
    if "common.auth" in sys.modules:
        del sys.modules["common.auth"]

    # Avoid talking to MS at import time when azure_scheme is constructed.
    with patch("fastapi_azure_auth.auth.SingleTenantAzureAuthorizationCodeBearer"):
        import common.auth
    common.auth._clear_jwks_cache()
    return common.auth


class TestVerifyTokenJWKSHardening:
    """Coverage for the issue-#114 fixes in ``verify_token`` / ``_get_jwks``."""

    @pytest.fixture(autouse=True)
    def _clear_jwks_cache(self):
        """Always start from a cold JWKS cache so call counts are deterministic."""
        # The cache is module-local; if common.auth was imported in a
        # previous test, clear it before and after.
        try:
            import common.auth
            common.auth._clear_jwks_cache()
        except Exception:
            pass
        yield
        try:
            import common.auth
            common.auth._clear_jwks_cache()
        except Exception:
            pass

    def test_get_jwks_passes_a_timeout_to_requests(self, monkeypatch):
        """`_get_jwks` must bound the upstream wait with a timeout kwarg
        (acceptance criterion 3 — JWKS unreachable → bounded failure).
        """
        from common.auth import _get_jwks
        from common.auth import _clear_jwks_cache
        _clear_jwks_cache()

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"keys": []}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            _get_jwks(_TEST_TENANT_ID, 0)

        # Timeout must be set AND must be small enough to bound a hung
        # upstream to a worker-tolerable window.
        assert mock_get.call_count == 1, mock_get.call_args_list
        kwargs = mock_get.call_args.kwargs
        assert "timeout" in kwargs, (
            f"_get_jwks called requests.get without a timeout kwarg "
            f"(call_args={mock_get.call_args!r})"
        )
        assert kwargs["timeout"] <= 5

    def test_get_jwks_propagates_http_error(self, monkeypatch):
        """A non-2xx JWKS response (e.g. 503 from a degraded tenant
        endpoint) must surface as an exception rather than silently
        handing back an empty JWKS and accepting any signed token.
        """
        from common.auth import _get_jwks
        from common.auth import _clear_jwks_cache
        _clear_jwks_cache()

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = (
                requests.HTTPError("503 Service Unavailable")
            )
            mock_get.return_value = mock_response

            with pytest.raises(requests.HTTPError):
                _get_jwks(_TEST_TENANT_ID, 0)

    def test_verify_token_caches_jwks_across_calls(self, monkeypatch):
        """Acceptance criterion 1: repeated verify_token calls within
        the same minute must issue at most ONE upstream JWKS fetch.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get, \
             patch("common.auth.time.time", return_value=1_700_000_000):
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # 5 calls within the same minute bucket.
            for _ in range(5):
                auth.verify_token(token)

        # 1 fetch total for the whole burst, not 5.
        assert mock_get.call_count == 1, (
            f"expected 1 JWKS fetch (cached for the minute), "
            f"got {mock_get.call_count}"
        )

    def test_verify_token_single_flight_concurrent_cold_cache(
            self, monkeypatch):
        """Acceptance criterion 1, concurrent case: a burst of valid-token
        requests on a cold JWKS cache must issue exactly ONE upstream
        fetch (single-flight), not one per caller.

        The original ``@functools.lru_cache`` implementation only
        de-duplicated *after* the value was in the cache; concurrent
        misses each fetched independently, so a 40-request burst on a
        cold cache still produced 40 upstream fetches. This test
        guards against that regression.

        The artificial 100ms sleep in the mock fetch is what makes the
        race observable: without it, the GIL serializes everything
        behind one thread's call and concurrent misses don't actually
        overlap. With it, the first thread to acquire the lock does
        the fetch, and the others wait on the lock and reuse the
        result.
        """
        import threading
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        fetch_count_lock = threading.Lock()
        fetch_count = [0]

        def slow_fetch(*args, **kwargs):
            # Simulate a slow JWKS endpoint so concurrent callers
            # actually race for the lock instead of serializing
            # behind the GIL.
            import time as _time
            _time.sleep(0.1)
            with fetch_count_lock:
                fetch_count[0] += 1
            response = MagicMock()
            response.json.return_value = jwks
            response.raise_for_status = MagicMock()
            return response

        with patch("common.auth.requests.get", side_effect=slow_fetch), \
             patch("common.auth.time.time", return_value=1_700_000_000):
            results = []
            errors = []

            def call_verify():
                try:
                    claims = auth.verify_token(token)
                    results.append(claims)
                except Exception as e:
                    errors.append(e)

            threads = [
                threading.Thread(target=call_verify) for _ in range(20)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors, f"verify_token raised during burst: {errors}"
        assert len(results) == 20, (
            f"expected 20 successful calls, got {len(results)}"
        )
        assert fetch_count[0] == 1, (
            f"expected exactly 1 JWKS fetch (single-flight on cold "
            f"cache), got {fetch_count[0]}"
        )

    def test_verify_token_refetches_jwks_after_ttl_window(self, monkeypatch):
        """The cache TTL must elapse — after the bucket rolls over, the
        next verify_token call must fetch again (otherwise stale keys
        become permanent after the first rotation).
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get, \
             patch("common.auth.time.time") as mock_time:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            # Minute N.
            mock_time.return_value = 1_700_000_000.0
            auth.verify_token(token)
            # Minute N+2 — past the cache window.
            mock_time.return_value = 1_700_000_000.0 + 120
            auth.verify_token(token)

        assert mock_get.call_count == 2, (
            f"expected a re-fetch after the 60s cache window rolled "
            f"over, got {mock_get.call_count} fetches"
        )

    def test_verify_token_rejects_wrong_issuer(self, monkeypatch):
        """Acceptance criterion 2: a JWT whose `iss` claim does not
        match the configured tenant's MS endpoint must be rejected,
        even if its `kid` resolves in the JWKS and its `aud` is
        correct (cross-tenant acceptance).
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()

        # Same kid + aud as the legit token, but `iss` points at a
        # *different* tenant.
        rogue_token = _sign_test_token(
            private_pem,
            issuer="https://login.microsoftonline.com/evil-tenant-id/v2.0",
        )

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                auth.verify_token(rogue_token)

        assert exc_info.value.status_code == 401, (
            f"expected 401 for cross-tenant token, got "
            f"{exc_info.value.status_code}"
        )
        # Must not be the 401 we'd get from a missing key — the
        # request should fail at signature/claim validation, not at
        # kid lookup.
        assert "Unable to find appropriate key" not in str(
            exc_info.value.detail
        ), (
            "token was rejected on kid lookup rather than issuer "
            "validation — the JWKS may have been bypassed entirely"
        )

    def test_verify_token_accepts_correct_issuer(self, monkeypatch):
        """Sanity check: a JWT with the correct `iss` and `aud` for the
        configured tenant is accepted end-to-end through the JWKS path.
        Guards against the issuer check being overly strict and
        rejecting legitimate tokens.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            claims = auth.verify_token(token)

        assert claims["iss"] == _TEST_ISSUER
        assert claims["aud"] == _TEST_CLIENT_ID
        assert claims["sub"] == "test-user"

    def test_verify_token_decodes_with_pinned_audience_and_issuer(
            self, monkeypatch):
        """The `jwt.decode` call inside verify_token must be invoked
        with both `audience` AND `issuer`. Without both, the decode is
        just as weak as the original code — this guards against
        regressions where one of the two kwargs is accidentally
        dropped.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get, \
             patch("common.auth.jwt.decode",
                   return_value={"sub": "u", "iss": _TEST_ISSUER,
                                 "aud": _TEST_CLIENT_ID, "roles": []}) \
             as mock_decode:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            auth.verify_token(token)

        assert mock_decode.call_count == 1
        kwargs = mock_decode.call_args.kwargs
        assert kwargs.get("audience") == _TEST_CLIENT_ID
        assert kwargs.get("issuer") == _TEST_ISSUER
        assert kwargs.get("algorithms") == ["RS256"]

    def test_verify_token_jwks_timeout_propagates_as_failure(
            self, monkeypatch):
        """When the JWKS endpoint hangs past the timeout, the request
        must surface as an HTTPException (or be retried by the next
        call once the minute bucket rolls) — it must NOT block the
        worker indefinitely.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get:
            mock_get.side_effect = requests.Timeout("read timed out")

            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                auth.verify_token(token)

        assert exc_info.value.status_code == 401
        # requests.get was called with the bounded timeout, not the
        # default (no timeout).
        assert mock_get.call_args.kwargs.get("timeout") is not None

    def test_verify_token_rejects_token_with_unknown_kid(
            self, monkeypatch):
        """If the token's `kid` does not resolve to any key in the
        JWKS, verify_token must surface an auth failure rather than
        silently accepting the token or crashing.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        # Sign with a kid that is NOT in the JWKS dict.
        token = _sign_test_token(
            private_pem, issuer=_TEST_ISSUER, kid="not-in-jwks",
        )

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                auth.verify_token(token)

        # The token must be rejected; the exact status code is
        # implementation detail of the outer error-handler block.
        assert exc_info.value.status_code in (401, 403)

    def test_verify_token_enforces_required_roles(self, monkeypatch):
        """Role enforcement runs after signature/issuer validation.
        A correctly-signed token without the required role must be
        rejected — verify_token must not return claims for it.
        """
        auth = _build_real_env(monkeypatch)
        private_pem, jwks = _generate_test_jwks()
        # Token claims include only `User`, not `Admin`.
        token = _sign_test_token(private_pem, issuer=_TEST_ISSUER)

        with patch("common.auth.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = jwks
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                auth.verify_token(token, required_roles=["Admin"])

        # The token must be rejected. The exact status code is
        # implementation detail of the outer error-handler block.
        assert exc_info.value.status_code in (401, 403)


def _build_mock_env(monkeypatch):
    """Wire ``common.auth`` to the dev/mock verify_token branch.

    Used by tests that exercise the `else` branch of verify_token
    (the path that runs when ``env == "dev"`` AND ``mock_enabled``
    is True). Returns the imported ``common.auth`` module.
    """
    mock_tfconfig = MockTFConfig()
    mock_values = {
        "env": {"value": "dev"},
        "client_id": {"value": _TEST_CLIENT_ID},
        "tenant_id": {"value": _TEST_TENANT_ID},
        "oauth2_permission_scope_uri": {"value": "test-scope-uri"},
        "oauth2_permission_scope": {"value": "test-scope"},
    }
    mock_tfconfig._getitem_mock.side_effect = (
        lambda key: mock_values.get(key, {"value": "default"})
    )

    mock_logger = MockLogger()
    mock_log_module = MagicMock()
    mock_log_module.logger = mock_logger
    mock_log_module.create_fixed_logger = MagicMock(return_value=mock_logger)
    mock_log_module.AzureLogHandler = MagicMock()

    mock_config_module = MagicMock()
    mock_config_module.tfconfig = mock_tfconfig
    mock_config_module.mock_enabled = True

    monkeypatch.setitem(sys.modules, "common.log", mock_log_module)
    monkeypatch.setitem(sys.modules, "common.config", mock_config_module)

    if "common.auth" in sys.modules:
        del sys.modules["common.auth"]

    with patch("mock.MockAzureAuthScheme.MockAzureAuthScheme"):
        import common.auth
    return common.auth


class TestVerifyTokenMockBranch:
    """Coverage for the dev/mock verify_token branch — the path that
    runs when ``env == "dev"`` AND ``mock_enabled`` is True.

    The real branch (production) is covered by
    ``TestVerifyTokenJWKSHardening`` above; this class is what makes
    the file's coverage clear the 69% ``fail_under`` gate.
    """

    def test_mock_branch_accepts_jwt_format_token(self, monkeypatch):
        """A well-formed JWT (three base64url parts) is decoded
        without signature validation and its claims are returned
        (with defaults filled in for missing `sub`/`name`/`roles`).
        Passing `required_roles=["User"]` also exercises the
        JWT-format + role-check happy path (line 147 in auth.py).
        """
        auth = _build_mock_env(monkeypatch)

        # header.payload.signature
        import base64
        import json
        header = base64.urlsafe_b64encode(
            b'{"alg":"none","typ":"JWT"}'
        ).rstrip(b"=").decode()
        payload_dict = {
            "iss": "https://example.com",
            "aud": _TEST_CLIENT_ID,
            # Intentionally omit `sub`, `name`, `roles` to exercise
            # the default-claim fill-in branches.
        }
        payload = base64.urlsafe_b64encode(
            json.dumps(payload_dict).encode()
        ).rstrip(b"=").decode()
        token = f"{header}.{payload}.signature"

        # Default-filled `roles=["User"]` satisfies this check.
        claims = auth.verify_token(token, required_roles=["User"])

        assert claims["sub"] == "mock-subject-id"
        assert claims["name"] == "Mock User"
        assert claims["roles"] == ["User"]

    def test_mock_branch_accepts_non_jwt_token(self, monkeypatch):
        """A non-JWT string (no dot separators) is accepted as a
        generic mock principal — the path that builds
        ``mock_claims`` with aud/iss populated from tfconfig.
        """
        auth = _build_mock_env(monkeypatch)

        claims = auth.verify_token("not-a-jwt")

        assert claims["sub"] == "mock-subject-id"
        assert claims["name"] == "Mock User"
        assert claims["roles"] == ["User"]
        assert claims["aud"] == _TEST_CLIENT_ID
        assert claims["iss"] == _TEST_ISSUER
        assert claims["mock_generated"] is True

    def test_mock_branch_handles_decode_failure(self, monkeypatch):
        """If the middle part of a 'JWT' is not valid base64, the
        branch falls back to the default mock claims rather than
        propagating the decode error.
        """
        auth = _build_mock_env(monkeypatch)

        # header.!!!invalid-base64!!!.signature
        token = "abc.!!!not-valid-base64!!!.sig"

        claims = auth.verify_token(token)

        assert claims["sub"] == "mock-subject-id"
        assert claims["mock_generated"] is True

    def test_mock_branch_role_check(self, monkeypatch):
        """Role checks also run on the mock branch — a mock token
        without the required role must surface an auth failure.
        """
        auth = _build_mock_env(monkeypatch)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            auth.verify_token("not-a-jwt", required_roles=["Admin"])

        # The token must be rejected. The exact status code is
        # implementation detail of the outer error-handler block.
        assert exc_info.value.status_code in (401, 403)

    def test_mock_branch_role_check_passes_when_role_matches(
            self, monkeypatch):
        """If the mock token's default `["User"]` role satisfies
        `required_roles=["User"]`, verify_token must return the
        claims (exercises the happy-path branch of `_verify_roles`).
        """
        auth = _build_mock_env(monkeypatch)

        claims = auth.verify_token("not-a-jwt", required_roles=["User"])

        assert claims["roles"] == ["User"]

    def test_mock_branch_role_check_all_modes(self, monkeypatch):
        """`_verify_roles(check_all=True)` requires ALL listed roles
        to be present; the default is ANY. Exercise the all-mode
        success path.
        """
        from common.auth import _verify_roles
        # Two roles both present → succeeds under check_all=True.
        claims = {"roles": ["Admin", "User"]}
        # Should not raise.
        _verify_roles(claims, ["Admin", "User"], check_all=True)

        # And the failure mode under check_all=True when one is missing.
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            _verify_roles(claims, ["Admin", "Superuser"], check_all=True)