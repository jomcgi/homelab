# Tests for mcp-http-app-explicit-transport rule.
import uvicorn
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("my-server")


# ruleid: mcp-http-app-explicit-transport
app = mcp.http_app()


# ruleid: mcp-http-app-explicit-transport
app = mcp.http_app(path="/mcp")


# ruleid: mcp-http-app-explicit-transport
app = mcp.http_app(middleware=[])


# ok: mcp-http-app-explicit-transport — explicit sse transport
app = mcp.http_app(transport="sse")


# ok: mcp-http-app-explicit-transport — explicit streamable-http transport
app = mcp.http_app(transport="streamable-http")


# ok: mcp-http-app-explicit-transport — explicit transport with other kwargs
app = mcp.http_app(path="/mcp", transport="sse", middleware=[])
