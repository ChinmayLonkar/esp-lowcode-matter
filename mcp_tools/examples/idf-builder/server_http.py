#!/usr/bin/env python3
"""
HTTP server for the ESP-IDF Builder MCP tool.
This server provides HTTP endpoints for interacting with the ESP-IDF Builder tools.
"""

import os
import sys
import logging
import uvicorn
import argparse
from typing import Dict, List, Any, Optional

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
from mcp_tools.components.path_setup import setup_path
setup_path()

# Import the server script to get the mcp instance
from server import mcp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def main():
    """Entry point for the HTTP server."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ESP-IDF Builder HTTP Server")
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to bind to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on"
    )
    args = parser.parse_args()

    # Get host and port from args
    host = args.host
    port = args.port

    # Create FastAPI app from the FastMCP instance
    app = mcp.sse_app()

    # Log starting info
    logger.info(f"Starting ESP-IDF Builder HTTP server at http://{host}:{port}")
    logger.info(f"SSE endpoint available at: http://{host}:{port}/sse")
    logger.info("Adding /sse to your URL is required for client connections")

    # Get tool list
    async def get_tools():
        return await mcp.get_tools()

    # Create a new event loop to run the async method
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tools = loop.run_until_complete(get_tools())
    tool_names = [t.name for t in tools.values()]
    logger.info(f"Available tools: {', '.join(tool_names)}")

    # Start Uvicorn server
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    main()
