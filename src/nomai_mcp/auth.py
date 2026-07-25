import logging
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, BaseModel
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from nomai_mcp.settings import Settings

logger = logging.getLogger(__name__)

MCP_SCOPE = "mcp"
OFFLINE_ACCESS_SCOPE = "offline_access"

REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 days

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


class PendingAuthorization(BaseModel):
    """The original MCP client's authorization request, kept around while
    the user is off completing the Google login step."""

    redirect_uri: str
    code_challenge: str | None
    redirect_uri_provided_explicitly: bool
    client_id: str
    resource: str | None
    original_state: str | None
    scopes: list[str]


class PersistedState(BaseModel):
    clients: dict[str, OAuthClientInformationFull] = {}
    auth_codes: dict[str, AuthorizationCode] = {}
    tokens: dict[str, AccessToken] = {}
    refresh_tokens: dict[str, RefreshToken] = {}
    state_mapping: dict[str, PendingAuthorization] = {}


class GoogleProxyOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """MCP Authorization Server that proxies human login to Google.

    MCP clients (Claude Code, etc.) register with and authenticate against
    THIS server via standard OAuth 2.1 + Dynamic Client Registration — no
    Google credentials ever touch them. Internally, the actual login step
    redirects to Google using one confidential OAuth client held here, and
    the resulting email is checked against an allowlist before this server
    mints its own MCP access token.

    Registered clients, in-flight authorization codes, and issued tokens are
    persisted to `settings.state_path` on every change and reloaded at
    startup, so a redeploy doesn't force every MCP client to re-register and
    every user to re-authenticate. Clients that request the `offline_access`
    scope get a rotating refresh token so they can renew silently instead of
    repeating the Google login every hour.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._allowed_emails = {e.lower() for e in settings.allowed_emails}
        self._google_redirect_uri = f"{str(settings.server_url).rstrip('/')}/google/callback"
        self._state_path = Path(settings.state_path)

        state = self._load()
        self.clients: dict[str, OAuthClientInformationFull] = state.clients
        self.auth_codes: dict[str, AuthorizationCode] = state.auth_codes
        self.tokens: dict[str, AccessToken] = state.tokens
        self.refresh_tokens: dict[str, RefreshToken] = state.refresh_tokens
        # state -> the original MCP client's authorization request, kept
        # around while the user is off completing the Google login step.
        self.state_mapping: dict[str, PendingAuthorization] = state.state_mapping

    # --- persistence -----------------------------------------------------------

    def _load(self) -> PersistedState:
        if not self._state_path.exists():
            return PersistedState()
        try:
            return PersistedState.model_validate_json(self._state_path.read_text())
        except ValueError:
            logger.warning("Failed to parse OAuth state file %s, starting empty", self._state_path)
            return PersistedState()

    def _save(self) -> None:
        state = PersistedState(
            clients=self.clients,
            auth_codes=self.auth_codes,
            tokens=self.tokens,
            refresh_tokens=self.refresh_tokens,
            state_mapping=self.state_mapping,
        )
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(state.model_dump_json())
        tmp_path.replace(self._state_path)

    # --- client registration -------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info
        self._save()

    # --- authorization (proxies to Google) -----------------------------------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        state = secrets.token_hex(16)
        self.state_mapping[state] = PendingAuthorization(
            redirect_uri=str(params.redirect_uri),
            code_challenge=params.code_challenge,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            client_id=client.client_id,
            resource=str(params.resource) if params.resource else None,
            original_state=params.state,
            scopes=params.scopes or [MCP_SCOPE],
        )
        self._save()

        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.google_client_id,
                "redirect_uri": self._google_redirect_uri,
                "scope": "openid email",
                "state": state,
                "access_type": "online",
                "prompt": "select_account",
            }
        )
        return f"{GOOGLE_AUTH_URL}?{query}"

    async def handle_google_callback(self, request: Request) -> Response:
        """Route handler for GET /google/callback, Google's redirect target."""
        error = request.query_params.get("error")
        if error:
            raise HTTPException(400, f"Google login failed: {error}")

        code = request.query_params.get("code")
        state = request.query_params.get("state")
        if not code or not state:
            raise HTTPException(400, "Missing code or state parameter")

        state_data = self.state_mapping.get(state)
        if not state_data:
            raise HTTPException(400, "Invalid or expired state parameter")

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._settings.google_client_id,
                    "client_secret": self._settings.google_client_secret,
                    "redirect_uri": self._google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        if token_response.status_code != 200:
            logger.warning("Google token exchange failed: %s", token_response.text)
            raise HTTPException(401, "Google token exchange failed")

        google_access_token = token_response.json()["access_token"]

        async with httpx.AsyncClient(timeout=10.0) as client:
            info_response = await client.get(GOOGLE_TOKENINFO_URL, params={"access_token": google_access_token})
        if info_response.status_code != 200:
            raise HTTPException(401, "Failed to verify Google token")

        info = info_response.json()
        email = info.get("email", "").lower()
        email_verified = str(info.get("email_verified")).lower() == "true"
        if not email_verified or email not in self._allowed_emails:
            logger.warning("Rejected login: email %r not allowed", email)
            raise HTTPException(403, f"{email or 'this account'} is not authorized to use this server")

        new_code = f"mcp_{secrets.token_hex(16)}"
        self.auth_codes[new_code] = AuthorizationCode(
            code=new_code,
            client_id=state_data.client_id,
            redirect_uri=AnyHttpUrl(state_data.redirect_uri),
            redirect_uri_provided_explicitly=state_data.redirect_uri_provided_explicitly,
            expires_at=time.time() + 300,
            scopes=state_data.scopes,
            code_challenge=state_data.code_challenge,
            resource=state_data.resource,
            subject=email,
        )
        del self.state_mapping[state]
        self._save()

        redirect_url = construct_redirect_uri(
            state_data.redirect_uri,
            code=new_code,
            state=state_data.original_state,
        )
        return RedirectResponse(url=redirect_url, status_code=302)

    # --- authorization code / token exchange ---------------------------------

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self.auth_codes.get(authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        if authorization_code.code not in self.auth_codes:
            raise ValueError("Invalid authorization code")

        mcp_token = f"mcp_{secrets.token_hex(32)}"
        self.tokens[mcp_token] = AccessToken(
            token=mcp_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(time.time()) + 3600,
            resource=authorization_code.resource,
            subject=authorization_code.subject,
        )

        new_refresh_token: str | None = None
        if OFFLINE_ACCESS_SCOPE in authorization_code.scopes:
            new_refresh_token = f"mcp_refresh_{secrets.token_hex(32)}"
            self.refresh_tokens[new_refresh_token] = RefreshToken(
                token=new_refresh_token,
                client_id=client.client_id,
                scopes=authorization_code.scopes,
                expires_at=int(time.time()) + REFRESH_TOKEN_TTL_SECONDS,
                subject=authorization_code.subject,
            )

        del self.auth_codes[authorization_code.code]
        self._save()

        return OAuthToken(
            access_token=mcp_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(authorization_code.scopes),
            refresh_token=new_refresh_token,
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        return self.refresh_tokens.get(refresh_token)

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotate: the old refresh token is single-use, per OAuth 2.1's
        # requirement for public clients (DCR/CIMD registrants have no
        # client secret to prove possession, so rotation limits replay).
        del self.refresh_tokens[refresh_token.token]

        mcp_token = f"mcp_{secrets.token_hex(32)}"
        self.tokens[mcp_token] = AccessToken(
            token=mcp_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time()) + 3600,
            subject=refresh_token.subject,
        )

        new_refresh_token = f"mcp_refresh_{secrets.token_hex(32)}"
        self.refresh_tokens[new_refresh_token] = RefreshToken(
            token=new_refresh_token,
            client_id=client.client_id,
            scopes=scopes,
            expires_at=int(time.time()) + REFRESH_TOKEN_TTL_SECONDS,
            subject=refresh_token.subject,
        )
        self._save()

        return OAuthToken(
            access_token=mcp_token,
            token_type="Bearer",
            expires_in=3600,
            scope=" ".join(scopes),
            refresh_token=new_refresh_token,
        )

    # --- resource server side (FastMCP wraps this in a TokenVerifier itself) -

    async def load_access_token(self, token: str) -> AccessToken | None:
        access_token = self.tokens.get(token)
        if not access_token:
            return None
        if access_token.expires_at and access_token.expires_at < time.time():
            del self.tokens[token]
            self._save()
            return None
        return access_token

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        removed = self.tokens.pop(token.token, None) is not None
        removed = self.refresh_tokens.pop(token.token, None) is not None or removed
        if removed:
            self._save()
