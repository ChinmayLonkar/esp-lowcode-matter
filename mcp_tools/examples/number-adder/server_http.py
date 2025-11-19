#!/usr/bin/env python3
"""
HTTP server for the Number Adder MCP tool.
This is a simplified version that only provides the add_numbers functionality.
Run this to start an HTTP server that exposes the Number Adder tool via the MCP protocol.
"""

import os
import sys
import json
import argparse
from typing import Dict, List, Any, Optional, Union

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import from local modules
sys.path.append(root_dir)
from components.path_setup import setup_path
setup_path()

# Import FastMCP HTTP server
from fastmcp.server.fastapi_server import create_fastapi_app, run_http_server_blocking
from fastmcp import FastMCP

# Create MCP instance
mcp = FastMCP(name="number-adder")

@mcp.tool(name="add_numbers")
def add_numbers(num1: Union[int, float], num2: Union[int, float]) -> Dict[str, Any]:
    """Add two numbers together.

    Args:
        num1: First number
        num2: Second number

    Returns:
        Dictionary containing the result and input numbers
    """
    try:
        # Convert inputs to numbers if they're strings
        if isinstance(num1, str):
            num1 = float(num1)
            if num1.is_integer():
                num1 = int(num1)

        if isinstance(num2, str):
            num2 = float(num2)
            if num2.is_integer():
                num2 = int(num2)

        # Calculate the sum
        result = num1 + num2

        # Convert to integer if result is a whole number
        if isinstance(result, float) and result.is_integer():
            result = int(result)

        return {
            "success": True,
            "num1": num1,
            "num2": num2,
            "result": result
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

if __name__ == "__main__":
    # Parse arguments
    parser = argparse.ArgumentParser(description="Number Adder HTTP server")
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind the server to"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind the server to"
    )
    args = parser.parse_args()

    # Create FastAPI app
    app = create_fastapi_app(mcp)

    # Run HTTP server
    run_http_server_blocking(app, host=args.host, port=args.port)
