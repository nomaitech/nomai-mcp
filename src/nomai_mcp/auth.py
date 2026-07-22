import asyncio
import logging

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

from nomai_mcp.settings import Settings

logger = logging.getLogger(__name__)


class JWKSTokenVerifier(TokenVerifier):
    """Validates bearer tokens as JWTs signed by an external OAuth/OIDC provider.

    Works with any standard provider that exposes a JWKS endpoint (Auth0, Okta,
    Google, Keycloak, ...) — this server never issues or stores credentials
    itself, it only checks signature, issuer, audience and expiry.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._jwk_client = PyJWKClient(str(settings.oauth_jwks_uri))

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = await asyncio.to_thread(
                self._jwk_client.get_signing_key_from_jwt, token
            )
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self._settings.oauth_audience,
                issuer=str(self._settings.oauth_issuer_url),
            )
        except jwt.PyJWTError:
            logger.warning("Rejected invalid bearer token", exc_info=True)
            return None

        scopes = claims.get("scope", "").split() if isinstance(claims.get("scope"), str) else claims.get("scope", [])

        return AccessToken(
            token=token,
            client_id=claims.get("client_id") or claims.get("azp") or claims.get("sub", "unknown"),
            scopes=scopes,
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
            claims=claims,
        )
