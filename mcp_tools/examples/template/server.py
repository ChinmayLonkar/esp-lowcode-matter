#!/usr/bin/env python3
"""
Template for an MCP server.
This is a starting point for creating a custom tool that follows the MCP protocol.
"""

import os
import sys
import json
import logging
import tempfile
from typing import Dict, List, Any, Optional, TypedDict, Literal

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
from mcp_tools.components.path_setup import setup_path
setup_path()

# Import FastMCP modules
from fastmcp import FastMCP
from fastmcp.server.server import stdio_server as stdio_transport

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat
from mcp_tools.components.network import ApiClient, NetworkError

# Configure logging with environment variable support
log_level = os.environ.get("MCP_LOG_LEVEL", os.environ.get("LOGGING_LEVEL", "INFO")).upper()
numeric_level = getattr(logging, log_level, logging.INFO)

logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Suppress verbose logging if level is WARNING or higher
if numeric_level >= logging.WARNING:
    logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.ERROR)
    logging.getLogger('fastmcp').setLevel(logging.ERROR)

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Initialize output manager
output = get_output_manager(format="text", color=True)

# Create FastMCP instance
mcp = FastMCP(name="custom-tool")

@mcp.tool(name="sample_tool")
def sample_tool(text: str) -> str:
    """Sample tool that processes text.

    Args:
        text: Input text to process

    Returns:
        Processed text
    """
    # Log tool usage
    db.record_tool_call(
        tool_name="sample_tool",
        parameters={"text": text},
        status="success"
    )

    # Process the text (uppercase in this example)
    result = text.upper()

    # Output the result
    output.success(f"Processed text: {result}")

    return result

@mcp.tool(name="save_data")
def save_data(key: str, value: Any) -> Dict[str, Any]:
    """Save data to the database.

    Args:
        key: The key to store the data under
        value: The value to store

    Returns:
        Status information
    """
    try:
        # Store the data
        db.store_data(key, value, "custom-tool")

        # Log success
        output.success(f"Data saved with key: {key}")

        return {
            "success": True,
            "key": key,
            "message": f"Data saved successfully with key: {key}"
        }
    except Exception as e:
        # Log error
        output.error(f"Error saving data: {str(e)}")

        return {
            "success": False,
            "key": key,
            "error": str(e)
        }

@mcp.tool(name="get_data")
def get_data(key: str) -> Dict[str, Any]:
    """Retrieve data from the database.

    Args:
        key: The key to retrieve

    Returns:
        The stored data or error information
    """
    # Get the data
    data = db.get_data(key, "custom-tool")

    if data is None:
        output.warning(f"No data found for key: {key}")
        return {
            "success": False,
            "key": key,
            "error": "Data not found"
        }

    output.info(f"Retrieved data for key: {key}")
    return {
        "success": True,
        "key": key,
        "data": data
    }

@mcp.tool(name="fetch_data")
async def fetch_data(url: str) -> Dict[str, Any]:
    """Fetch data from an API.

    Args:
        url: The URL to fetch data from

    Returns:
        The fetched data or error information
    """
    try:
        # Create an API client
        async with ApiClient(base_url="") as client:
            # Make the request
            data = await client.get(url)

            # Log the result
            output.success(f"Data fetched from {url}")

            # Store in history
            db.record_tool_call(
                tool_name="fetch_data",
                parameters={"url": url},
                result={"success": True},
                status="success"
            )

            return {
                "success": True,
                "url": url,
                "data": data
            }
    except NetworkError as e:
        # Log the error
        output.error(f"Error fetching data: {str(e)}")

        # Record error in history
        db.record_tool_call(
            tool_name="fetch_data",
            parameters={"url": url},
            result={"success": False, "error": str(e)},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "url": url,
            "error": str(e)
        }

@mcp.tool(name="get_history")
def get_history(tool_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get the history of tool calls.

    Args:
        tool_name: Filter by tool name (optional)
        limit: Maximum number of records to return

    Returns:
        List of tool call records
    """
    history = db.get_tool_history(tool_name, limit)

    # Format the output
    output.print("Tool Call History:", color="blue")
    output.output(history)

    return history


async def main():
    """Main entry point."""
    # Print available tools
    tools = await mcp.get_tools()
    tools_data = [{"name": t.name, "description": t.description} for t in tools.values()]
    output.print("Registered Tools:", color="green")
    output.output(tools_data)

    # Start the server using stdio transport
    output.info("Starting MCP server using stdio transport")
    await mcp.run_stdio_async()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
