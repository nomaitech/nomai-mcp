from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, loaded from environment variables / .env.

    This server acts as its own OAuth Authorization Server (with Dynamic
    Client Registration) AND Resource Server. It never asks end users for
    any Google credentials — it holds one confidential "Web application"
    Google OAuth client itself and proxies the actual login to Google,
    minting its own MCP tokens afterward.
    """

    model_config = SettingsConfigDict(env_prefix="NOMAI_MCP_", env_file=".env")

    host: str = "0.0.0.0"
    port: int = 8000

    # This server's own public URL — used as the OAuth issuer, the resource
    # identifier, and the base for its Google callback route.
    server_url: AnyHttpUrl

    # Google "Web application" OAuth credentials. Held only here, server-side
    # — end users/friends never see or handle these.
    google_client_id: str
    google_client_secret: str

    # Gemini API key (from Google AI Studio) used by the image generation
    # tool. Unrelated to the OAuth client above — that's for login only.
    gemini_api_key: str

    # Only these emails are allowed to use the server (Google login alone
    # doesn't restrict to your company unless you're on real Workspace).
    allowed_emails: list[str]

    # Where registered OAuth clients / issued tokens are persisted to disk,
    # so redeploys (which recreate the pod) don't force every MCP client to
    # rediscover and re-authenticate. In k8s this should point at a mounted
    # PersistentVolume; the default is fine for local dev.
    state_path: str = "oauth_state.json"
