import logging

import httpx
from mcp.server.auth.provider import AccessToken, TokenVerifier

from nomai_mcp.settings import Settings

logger = logging.getLogger(__name__)

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class GoogleTokenVerifier(TokenVerifier):
    """Validates bearer tokens by asking Google's tokeninfo endpoint about them.

    Google's OAuth access tokens are opaque (not JWTs), so they can't be
    checked locally against a JWKS — instead each request is verified by
    calling Google, then the caller's email is checked against an allowlist
    (Google login alone doesn't restrict who can call this server).
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._allowed_emails = {e.lower() for e in settings.allowed_emails}

    async def verify_token(self, token: str) -> AccessToken | None:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(GOOGLE_TOKENINFO_URL, params={"access_token": token})

        if response.status_code != 200:
            logger.warning("Rejected token: tokeninfo returned %s", response.status_code)
            return None

        info = response.json()

        if info.get("aud") != self._settings.google_client_id:
            logger.warning("Rejected token: audience mismatch")
            return None

        email = info.get("email", "").lower()
        email_verified = str(info.get("email_verified")).lower() == "true"
        if not email_verified or email not in self._allowed_emails:
            logger.warning("Rejected token: email %r not allowed", email)
            return None

        return AccessToken(
            token=token,
            client_id=info.get("azp", info.get("aud", "unknown")),
            scopes=info.get("scope", "").split(),
            subject=info.get("sub"),
            claims=info,
        )
