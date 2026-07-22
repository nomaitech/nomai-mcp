from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, loaded from environment variables / .env.

    Auth is delegated to Google (Sign in with Google via a Google Cloud
    OAuth client) — this server never handles passwords itself, it only
    validates the access tokens Google issues (Resource Server pattern).
    """

    model_config = SettingsConfigDict(env_prefix="NOMAI_MCP_", env_file=".env")

    host: str = "0.0.0.0"
    port: int = 8000

    # Public URL of this MCP server itself (used as the OAuth resource identifier).
    resource_server_url: AnyHttpUrl

    # OAuth Client ID from Google Cloud Console (Credentials > OAuth client ID).
    google_client_id: str

    # Only these emails are allowed to use the server (Google login alone
    # doesn't restrict to your company unless you're on real Workspace).
    allowed_emails: list[str]

    required_scopes: list[str] = []
