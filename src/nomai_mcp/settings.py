from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime config, loaded from environment variables / .env.

    Points at whatever OAuth 2.1 / OIDC authorization server your company
    already uses (Auth0, Okta, Google Workspace, Keycloak, ...). This server
    never handles passwords itself — it only verifies tokens issued by that
    provider (Resource Server pattern).
    """

    model_config = SettingsConfigDict(env_prefix="NOMAI_MCP_", env_file=".env")

    host: str = "0.0.0.0"
    port: int = 8000

    # Public URL of this MCP server itself (used as the OAuth resource identifier).
    resource_server_url: AnyHttpUrl

    # Your OAuth/OIDC provider.
    oauth_issuer_url: AnyHttpUrl
    oauth_jwks_uri: AnyHttpUrl
    oauth_audience: str

    required_scopes: list[str] = []
