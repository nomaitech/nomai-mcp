import base64
import logging

from google import genai
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.fastmcp import FastMCP, Image
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from nomai_mcp.auth import MCP_SCOPE, GoogleProxyOAuthProvider
from nomai_mcp.settings import Settings

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

settings = Settings()

GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"

genai_client = genai.Client(api_key=settings.gemini_api_key)

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


def _sniff_image_mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


@mcp.tool()
async def generate_image(prompt: str, reference_images: list[str] | None = None) -> Image:
    """Generate an image from a text prompt using Gemini 2.5 Flash Image.

    reference_images is an optional list of base64-encoded images (e.g. to
    edit, combine, or use as style/subject references for the generation).
    """
    input_parts: list[dict] = [{"type": "text", "text": prompt}]
    for image_b64 in reference_images or []:
        input_parts.append(
            {
                "type": "image",
                "data": image_b64,
                "mime_type": _sniff_image_mime_type(base64.b64decode(image_b64)),
            }
        )

    interaction = await genai_client.aio.interactions.create(
        model=GEMINI_IMAGE_MODEL,
        input=input_parts,
        response_format={"type": "image"},
    )

    if not interaction.output_image or not interaction.output_image.data:
        logger.warning("Gemini interaction response contained no image: %r", interaction)
        raise HTTPException(502, "Gemini response contained no image")

    image_bytes = base64.b64decode(interaction.output_image.data)
    mime_type = interaction.output_image.mime_type or "image/png"
    return Image(data=image_bytes, format=mime_type.removeprefix("image/"))


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
