#!/usr/bin/env python3
"""
Template for an MCP HTTP client.
This is a starting point for creating a client for your custom MCP tool using HTTP.
"""

import os
import sys
import json
import logging
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

# Import MCP client
from fastmcp import Client
from urllib.parse import urlparse

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "client_http.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Parse command line arguments
parser = argparse.ArgumentParser(description="Custom Tool HTTP Client")
parser.add_argument(
    "--format",
    choices=["text", "json", "csv", "table"],
    default="text",
    help="Output format"
)
parser.add_argument(
    "--url",
    default="http://localhost:8000",
    help="Server URL"
)
parser.add_argument(
    "--color",
    action="store_true",
    default=True,
    help="Enable colored output"
)
args = parser.parse_args()

# Initialize output manager with selected format
output = get_output_manager(format=args.format, color=args.color)


async def interactive_loop():
    """Run an interactive loop for the HTTP client."""
    output.print("Custom Tool HTTP Client", color="green")
    output.print("Type 'exit' or 'quit' to exit", color="green")
    output.print("Available commands:", color="cyan")
    output.print("  process TEXT - Process text")
    output.print("  save KEY VALUE - Save data to the database")
    output.print("  get KEY - Get data from the database")
    output.print("  fetch URL - Fetch data from a URL")
    output.print("  history [TOOL_NAME] - Get tool history from server")
    output.print("  help - Show this help")

    # Create client
    server_url = args.url

    # Make sure the URL includes the SSE endpoint path
    if not server_url.endswith("/sse"):
        server_url = server_url.rstrip("/") + "/sse"

    output.info(f"Connecting to server at {server_url}")

    try:
        # Use client as an async context manager
        async with Client(server_url) as client:
            # List available tools
            try:
                tools = await client.list_tools()
                output.info(f"Connected to server at {server_url} with {len(tools)} tools available")
            except Exception as e:
                if "404 Not Found" in str(e):
                    output.error(f"Server not found at {server_url}. Make sure:")
                    output.error("1. The server is running (python server_http.py)")
                    output.error("2. The URL is correct and includes the /sse endpoint")
                    output.error("3. You're using the correct port (default: 8000)")
                    return
                else:
                    output.error(f"Error connecting to server: {str(e)}")
                    return

            while True:
                try:
                    # Get user input
                    user_input = input("\nCommand> ").strip()

                    # Check for exit command
                    if user_input.lower() in ["exit", "quit"]:
                        output.print("Exiting...", color="yellow")
                        break

                    # Process commands
                    parts = user_input.split(maxsplit=2)
                    command = parts[0].lower() if parts else ""

                    if command == "help":
                        output.print("Available commands:", color="cyan")
                        output.print("  process TEXT - Process text")
                        output.print("  save KEY VALUE - Save data to the database")
                        output.print("  get KEY - Get data from the database")
                        output.print("  fetch URL - Fetch data from a URL")
                        output.print("  history [TOOL_NAME] - Get tool history from server")
                        output.print("  help - Show this help")

                    elif command == "process":
                        if len(parts) < 2:
                            output.error("Missing text parameter")
                            continue

                        text = parts[1]
                        output.info(f"Processing text: {text}")
                        result = await client.call_tool("sample_tool", {"text": text})
                        # Store the result in the local database for history
                        db.record_tool_call(
                            tool_name="sample_tool",
                            parameters={"text": text},
                            result={"text": result[0].text} if result else None,
                            status="success"
                        )
                        output.output(result[0].text if result else "")

                    elif command == "save":
                        if len(parts) < 3:
                            output.error("Missing parameters. Usage: save KEY VALUE")
                            continue

                        key = parts[1]
                        value = parts[2]
                        try:
                            # Try to parse as JSON
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            # Keep as string if not valid JSON
                            pass

                        output.info(f"Saving data with key: {key}")
                        result = await client.call_tool("save_data", {"key": key, "value": value})
                        output.output(json.loads(result[0].text) if result else {})

                    elif command == "get":
                        if len(parts) < 2:
                            output.error("Missing key parameter")
                            continue

                        key = parts[1]
                        output.info(f"Getting data for key: {key}")
                        result = await client.call_tool("get_data", {"key": key})
                        output.output(json.loads(result[0].text) if result else {})

                    elif command == "fetch":
                        if len(parts) < 2:
                            output.error("Missing URL parameter")
                            continue

                        url = parts[1]
                        output.info(f"Fetching data from: {url}")
                        result = await client.call_tool("fetch_data", {"url": url})
                        output.output(json.loads(result[0].text) if result else {})

                    elif command == "history":
                        tool_name = parts[1] if len(parts) > 1 else None
                        params = {}
                        if tool_name:
                            params["tool_name"] = tool_name
                        params["limit"] = 10

                        output.info("Getting tool history from server")
                        result = await client.call_tool("get_history", params)
                        output.output(json.loads(result[0].text) if result else [])

                    else:
                        output.error(f"Unknown command: {command}")
                        output.print("Type 'help' for available commands", color="yellow")

                except Exception as e:
                    output.error(f"Error: {str(e)}")
                    logger.exception("Error in interactive loop")
    except Exception as e:
        output.error(f"Failed to connect to server: {str(e)}")
        if "404 Not Found" in str(e):
            output.error("The server endpoint was not found. Make sure the server is running and the URL is correct.")
            output.error(f"Tried to connect to: {server_url}")
        elif "Connection refused" in str(e):
            output.error("Connection refused. The server might not be running or might be on a different port.")
            output.error("Try starting the server with: python server_http.py")
        logger.exception("Connection error")


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_loop())
