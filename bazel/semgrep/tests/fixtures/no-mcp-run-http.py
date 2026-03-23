# Tests for no-mcp-run-http rule.
import mcp
import uvicorn


# ruleid: no-mcp-run-http
mcp.run(transport="http")


# ruleid: no-mcp-run-http
mcp.run(host="0.0.0.0", port=8080, transport="http")


# ruleid: no-mcp-run-http
mcp.run(transport="http", port=9000)


# ok: no-mcp-run-http — http_app() + uvicorn is the correct pattern
app = mcp.http_app()
uvicorn.run(app, host="0.0.0.0", port=8080)


# ok: no-mcp-run-http — stdio transport is fine
mcp.run(transport="stdio")


# ok: no-mcp-run-http — sse transport is a different concern
mcp.run(transport="sse")
