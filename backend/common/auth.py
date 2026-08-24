from os import environ as os_environ, path as os_path
from fastapi_azure_auth.auth import SingleTenantAzureAuthorizationCodeBearer
from common.config import tfconfig, mock_enabled
from common.log import logger
from jose import JWTError, jwt  # Add JWTError import
from fastapi import HTTPException, status
import functools
import requests
import time
from typing import List

# Before the verify_token function, initialize the JWKS client


# Module-level JWKS cache with TTL. The cache key includes a per-minute
# bucket (`cache_epoch_minute`), so the upstream JWKS endpoint is fetched
# at most once per minute per process even under repeated authenticated
# calls. This both bounds the per-request JWKS work (DoS amplification on a
# slow upstream) and bounds the worst-case hang time at exactly the JWKS
# fetch timeout, not at "however long upstream takes to time out".
@functools.lru_cache(maxsize=8)
def _get_jwks(tenant_id: str, cache_epoch_minute: int):
    jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    response = requests.get(jwks_url, timeout=5)
    response.raise_for_status()
    return response.json()

# define scope to use in the API   
scopes = [tfconfig["oauth2_permission_scope"]["value"]]

azure_scheme = None

# Print mock settings
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

# dont apply mock on other environment than dev and only if mock_enabled is set to true
if tfconfig["env"]["value"] != "dev" or not mock_enabled:
    console = Console()
    console.print(Panel(f"MOCK [bold]DISABLED[/bold] passing real Azure Scheme", style="green"))
    azure_scheme = SingleTenantAzureAuthorizationCodeBearer(
        app_client_id=tfconfig["client_id"]["value"],  
        tenant_id=tfconfig["tenant_id"]["value"], 
        scopes={tfconfig["oauth2_permission_scope_uri"]["value"]: tfconfig["oauth2_permission_scope"]["value"]},
        allow_guest_users=True
    )
else:
    from mock.MockAzureAuthScheme import MockAzureAuthScheme
    console = Console()
    console.print(Panel(f"MOCK: [bold]ENABLED[/bold] passing Mock azure scheme", style="yellow"))
    logger.info("MOCK environment is enabled")
    # Define mock authentication scheme
    # Assign the mock scheme
 

    azure_scheme = MockAzureAuthScheme(logger)


def verify_token(token: str, required_roles: List[str] = [], check_all: bool = False):
    """Verify a JWT token and return its claims
    
    Args:
        token: The JWT token string
        required_roles: Optional list of roles to check against token claims
        check_all: If True, user must have ALL roles; if False, ANY role is sufficient
    
    Returns:
        The token claims dictionary if validation succeeds
    
    Raises:
        HTTPException: If token validation fails or roles check fails
    """
    try:
        # Use the same condition pattern for consistency
        if tfconfig["env"]["value"] != "dev" or not mock_enabled:
            # For real Azure auth, manually verify the token
            tenant_id = tfconfig['tenant_id']['value']
            # Refresh JWKS at most once per minute; the per-minute bucket is
            # the second lru_cache argument so each token causes at most one
            # upstream fetch per minute total per process, not one per call.
            jwks = _get_jwks(tenant_id, int(time.time() // 60))

            # Extract unverified headers to get the kid
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            # Find the signing key
            signing_key = None
            for key in jwks["keys"]:
                if key["kid"] == kid:
                    signing_key = key
                    break

            if not signing_key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Unable to find appropriate key for token validation",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Verify the token — pin the issuer to this tenant so a token
            # minted by a different tenant (whose kid happens to resolve in
            # the JWKS) cannot be accepted as long as `aud` matches.
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=tfconfig["client_id"]["value"],
                issuer=f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            )
            
            # Check roles if required_roles is not empty
            if required_roles:
                _verify_roles(claims, required_roles, check_all)
                
            return claims
        else:
            # Mock implementation
            logger.warning("MOCK TOKEN VERIFICATION: Accepting any token without validation")
            try:
                # Try to decode the token without verification
                # This will work for valid JWT format tokens
                parts = token.split('.')
                if len(parts) == 3:  # Proper JWT format (header.payload.signature)
                    import base64
                    import json
                    
                    # Decode the payload (middle part)
                    # Fix padding for base64 decoding
                    padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    decoded = base64.b64decode(padded.replace('-', '+').replace('_', '/'))
                    claims = json.loads(decoded)
                    
                    # Ensure minimum required claims exist
                    if not claims.get("sub"):
                        claims["sub"] = "mock-subject-id"
                    if not claims.get("name"):
                        claims["name"] = "Mock User"
                    if not claims.get("roles"):
                        claims["roles"] = ["User"]
                        
                    logger.info(f"Mock token decoded with claims: {claims}")
                    
                    # Check roles if required_roles is not empty
                    if required_roles:
                        _verify_roles(claims, required_roles, check_all)
                        
                    return claims
                else:
                    # For non-JWT format tokens, return a mock object
                    mock_claims = {
                        "sub": "mock-subject-id",
                        "name": "Mock User",
                        "roles": ["User"],
                        "aud": tfconfig["client_id"]["value"],
                        "iss": f"https://login.microsoftonline.com/{tfconfig['tenant_id']['value']}/v2.0",
                        "mock_generated": True
                    }
                    
                    # Check roles if required_roles is not empty
                    if required_roles:
                        _verify_roles(mock_claims, required_roles, check_all)
                        
                    return mock_claims
            except Exception as e:
                logger.warning(f"Failed to decode mock token, using default: {str(e)}")
                # Return default mock claims if token couldn't be decoded
                default_claims = {
                    "sub": "mock-subject-id",
                    "name": "Mock User",
                    "roles": ["User"],
                    "mock_generated": True
                }
                
                # Check roles if required_roles is not empty
                if required_roles:
                    _verify_roles(default_claims, required_roles, check_all)
                    
                return default_claims
            
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to validate token",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Add helper function for role verification
def _verify_roles(claims, required_roles, check_all=False):
    """Verify that the claims contain the required roles"""
    # Get roles from claims
    roles = claims.get("roles", [])
    
    # Normalize roles for case-insensitive comparison
    normalized_roles = [role.lower() for role in roles]
    normalized_required_roles = [role.lower() for role in required_roles]
    
    # Check if user has required roles
    has_access = False
    if check_all:
        # User must have ALL required roles
        has_access = all(role in normalized_roles for role in normalized_required_roles)
    else:
        # User must have ANY of the required roles
        has_access = any(role in normalized_roles for role in normalized_required_roles)
    
    if not has_access:
        logger.warning(f"Role check failed - User roles: {roles}, Required roles: {required_roles}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Insufficient permissions",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Role check successful for {required_roles}")
    return True