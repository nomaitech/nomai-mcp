import logging

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import Response

from nomai_mcp.auth import MCP_SCOPE, GoogleProxyOAuthProvider
from nomai_mcp.settings import Settings

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

settings = Settings()

oauth_provider = GoogleProxyOAuthProvider(settings)

mcp = FastMCP(
    "nomai-mcp",
    host=settings.host,
    port=settings.port,
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=settings.server_url,
        resource_server_url=settings.server_url,
        required_scopes=[MCP_SCOPE],
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=[MCP_SCOPE],
            default_scopes=[MCP_SCOPE],
        ),
    ),
)


@mcp.custom_route("/google/callback", methods=["GET"])
async def google_callback(request: Request) -> Response:
    return await oauth_provider.handle_google_callback(request)


@mcp.tool()
def ping() -> str:
    """Health-check tool: confirms auth worked and the server is reachable."""
    return "pong"


@mcp.tool()
def who_is_the_owner() -> str:
    """Mock tool: answers who owns this server."""
    return "Carlos The Great"


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
