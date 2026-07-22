# nomai-mcp

Nomai's company MCP server, exposed over remote HTTP and protected with OAuth 2.1.

This server acts as an OAuth **Resource Server** only: it does not issue tokens
or store credentials. It validates bearer tokens (JWTs) against whatever OIDC
provider the company already uses — Auth0, Okta, Google Workspace, Keycloak,
etc. — via that provider's JWKS endpoint.

## Setup

1. Register this server as an API/audience in your OAuth provider, and note:
   - its issuer URL
   - its JWKS URI
   - the audience identifier you configured
2. Copy `.env.example` to `.env` and fill in those values plus this server's
   own public URL.
3. Install dependencies and run:

   ```bash
   uv sync
   uv run nomai-mcp
   ```

   The server listens on `NOMAI_MCP_HOST:NOMAI_MCP_PORT` (default
   `0.0.0.0:8000`) using the streamable-HTTP MCP transport at `/mcp`.

## Adding tools

Add `@mcp.tool()`-decorated functions in `src/nomai_mcp/server.py`. A `ping`
tool is included as a health check — call it once your client has a valid
token to confirm auth is wired up correctly.

## Connecting a client

Clients (Claude Code, Claude.ai, etc.) discover the auth requirements via the
MCP server's protected-resource metadata and go through your OAuth provider's
normal authorization-code + PKCE flow — no client-side secrets to manage
beyond standard OAuth client registration with your provider.
