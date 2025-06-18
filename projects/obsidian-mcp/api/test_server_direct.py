#!/usr/bin/env python3
"""
Direct test of the MCP server using the MCP protocol.
"""

import asyncio
import json
import subprocess
import sys
from pathlib import Path


async def test_mcp_server():
    """Test the MCP server directly via stdio."""
    print("🔧 Testing MCP Server via stdio")
    print("=" * 40)
    
    # Start the server process
    server_path = Path(__file__).parent / "server.py"
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(server_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PYTHONPATH": str(Path(__file__).parent)}
    )
    
    async def send_request(method, params=None):
        """Send a JSON-RPC request to the server."""
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or {}
        }
        
        request_str = json.dumps(request) + "\n"
        process.stdin.write(request_str.encode())
        await process.stdin.drain()
        
        # Read response
        response_line = await process.stdout.readline()
        if response_line:
            return json.loads(response_line.decode().strip())
        return None
    
    try:
        # Initialize the server
        print("📡 Initializing MCP connection...")
        response = await send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        })
        print(f"Server response: {response}")
        
        # List available tools
        print("\n🔍 Listing available tools...")
        response = await send_request("tools/list")
        if response and "result" in response:
            tools = response["result"]["tools"]
            print(f"Available tools: {len(tools)}")
            for tool in tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        # Test search_notes tool
        print("\n🔎 Testing search_notes...")
        response = await send_request("tools/call", {
            "name": "search_notes",
            "arguments": {
                "query": "leadership",
                "limit": 3
            }
        })
        print(f"Search response: {response}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Clean up
        if process.returncode is None:
            process.terminate()
            await process.wait()


if __name__ == "__main__":
    asyncio.run(test_mcp_server())