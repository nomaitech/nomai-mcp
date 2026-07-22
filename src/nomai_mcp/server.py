import logging

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from nomai_mcp.auth import JWKSTokenVerifier
from nomai_mcp.settings import Settings

logging.basicConfig(level=logging.INFO)

settings = Settings()

mcp = FastMCP(
    "nomai-mcp",
    host=settings.host,
    port=settings.port,
    token_verifier=JWKSTokenVerifier(settings),
    auth=AuthSettings(
        issuer_url=settings.oauth_issuer_url,
        resource_server_url=settings.resource_server_url,
        required_scopes=settings.required_scopes,
    ),
)


@mcp.tool()
def ping() -> str:
    """Health-check tool: confirms auth worked and the server is reachable."""
    return "pong"


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
