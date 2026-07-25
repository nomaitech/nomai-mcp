import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP
from starlette.exceptions import HTTPException
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


LONDONIST_BASE_URL = "https://londonist.com"
LONDONIST_THINGS_TO_DO_URL = f"{LONDONIST_BASE_URL}/things-to-do"

# Londonist returns 403 to httpx's default User-Agent, so pretend to be a browser.
_SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}

_WEEKEND_LINK_RE = re.compile(r"things to do in london this weekend", re.IGNORECASE)


@mcp.tool()
async def things_to_do_in_london_this_weekend() -> str:
    """Scrape londonist.com for the current "Things To Do In London This
    Weekend" article and return its events, grouped by section (e.g. "All
    weekend", "Saturday", "Sunday").
    """
    async with httpx.AsyncClient(
        headers=_SCRAPE_HEADERS, timeout=15.0, follow_redirects=True
    ) as client:
        index_response = await client.get(LONDONIST_THINGS_TO_DO_URL)
        index_response.raise_for_status()
        index_soup = BeautifulSoup(index_response.text, "html.parser")

        link = index_soup.find("a", string=_WEEKEND_LINK_RE)
        if link is None or not link.get("href"):
            logger.warning("Could not find 'this weekend' link on %s", LONDONIST_THINGS_TO_DO_URL)
            raise HTTPException(502, "Could not find the 'Things To Do This Weekend' link")

        article_url = urljoin(LONDONIST_BASE_URL, link["href"])

        article_response = await client.get(article_url)
        article_response.raise_for_status()
        article_soup = BeautifulSoup(article_response.text, "html.parser")

    title_tag = article_soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Things To Do In London This Weekend"

    body = article_soup.find(attrs={"itemprop": "articleBody"})
    if body is None:
        logger.warning("Could not find article body on %s", article_url)
        raise HTTPException(502, "Could not find the article content")

    lines = [title, f"Source: {article_url}", ""]
    for element in body.find_all(["h2", "p"]):
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        lines.append(f"## {text}" if element.name == "h2" else f"- {text}")

    return "\n".join(lines)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
