# nomai-mcp

Nomai's company MCP server, exposed over remote HTTP and protected with OAuth 2.1.

This server acts as an OAuth **Resource Server** only: it does not issue
tokens or store credentials. It delegates login to Google (Sign in with
Google) and validates each request's access token via Google's tokeninfo
endpoint, then checks the caller's email against an allowlist.

## Setup

1. In [Google Cloud Console](https://console.cloud.google.com):
   - Create a project (or use an existing one).
   - Go to **APIs & Services > OAuth consent screen** and configure it
     (External user type is fine; you don't need to publish/verify it for a
     small internal user list — just add your teammates as test users).
   - Go to **APIs & Services > Credentials > Create Credentials > OAuth
     client ID**. Choose the application type your MCP client expects (e.g.
     "Web application") and add its redirect URI.
   - Copy the generated **Client ID**.
2. Copy `.env.example` to `.env` and fill in:
   - `NOMAI_MCP_GOOGLE_CLIENT_ID` — the Client ID from step 1.
   - `NOMAI_MCP_ALLOWED_EMAILS` — the exact emails allowed to use the server.
   - `NOMAI_MCP_RESOURCE_SERVER_URL` — this server's own public URL.
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

`things_to_do_in_london_this_weekend` scrapes londonist.com/things-to-do,
follows the current "Things To Do In London This Weekend" article link, and
returns its events grouped by section.

## Connecting a client

When adding this as a custom connector, use the full MCP endpoint URL,
including the path — e.g. `https://mcp.nomaitech.com/mcp` — not just the
bare domain. The OAuth discovery/login endpoints live at the domain root,
but the actual MCP protocol (streamable-HTTP transport) is only served at
`/mcp`; pointing a client at the bare domain will authenticate successfully
and then fail to find any server, since `/` itself returns 404.

Google doesn't support OAuth Dynamic Client Registration, so MCP clients
(Claude Code, Claude.ai, etc.) will need the Client ID from setup step 1
configured manually rather than discovering it automatically — this is an
expected, spec-supported fallback, not a bug. The client then takes the
user through Google's normal login + consent screen and sends the resulting
access token as the bearer token on each request.

Only accounts listed in `NOMAI_MCP_ALLOWED_EMAILS` will be accepted — anyone
else who signs in with Google will authenticate successfully but be
rejected by this server with an invalid-token error.
