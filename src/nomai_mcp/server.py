import logging

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from nomai_mcp.auth import GoogleTokenVerifier
from nomai_mcp.settings import Settings

logging.basicConfig(level=logging.INFO)

settings = Settings()

mcp = FastMCP(
    "nomai-mcp",
    host=settings.host,
    port=settings.port,
    token_verifier=GoogleTokenVerifier(settings),
    auth=AuthSettings(
        issuer_url="https://accounts.google.com",
        resource_server_url=settings.resource_server_url,
        required_scopes=settings.required_scopes,
    ),
)


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
