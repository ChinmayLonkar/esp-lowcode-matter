#!/usr/bin/env python3
"""
HTTP client for the ESP-IDF Builder MCP tool.
This client provides a command-line interface for interacting with the ESP-IDF Builder MCP server.
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
parser = argparse.ArgumentParser(description="IDF Builder HTTP Client")
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
    output.print("ESP-IDF Builder HTTP Client", color="green")
    output.print("Type 'exit' or 'quit' to exit", color="green")

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
                output.info(f"Connected to server with {len(tools)} tools available")

                # Print available commands
                output.print("\nAvailable commands:", color="cyan")
                output.print("  1 - Detect connected ESP32 chip")
                output.print("  2 - Build an ESP32 project")
                output.print("  3 - Get build summary")
                output.print("  4 - Get full build log")
                output.print("  help - Show this help")
                output.print("  exit - Exit the client")
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
                    if user_input.lower() == "help":
                        output.print("Available commands:", color="cyan")
                        output.print("  1 - Detect connected ESP32 chip")
                        output.print("  2 - Build an ESP32 project")
                        output.print("  3 - Get build summary")
                        output.print("  4 - Get full build log")
                        output.print("  help - Show this help")
                        output.print("  exit - Exit the client")

                    elif user_input == "1":
                        output.info("Detecting connected ESP32 chip...")
                        result = await client.call_tool("detect_chip", {"random_string": "dummy"})
                        # Store the result in the local database for history
                        db.record_tool_call(
                            tool_name="detect_chip",
                            parameters={},
                            result={"text": result[0].text} if result else None,
                            status="success"
                        )
                        output.output(json.loads(result[0].text) if result else "No response")

                    elif user_input == "2":
                        project_path = input("Enter the path to the ESP32 project: ").strip()
                        if not project_path:
                            output.error("Project path cannot be empty")
                            continue

                        output.info(f"Building project at: {project_path}")
                        result = await client.call_tool("build_project", {"project_path": project_path})
                        # Store the result in the local database for history
                        db.record_tool_call(
                            tool_name="build_project",
                            parameters={"project_path": project_path},
                            result={"text": result[0].text} if result else None,
                            status="success"
                        )
                        output.output(json.loads(result[0].text) if result else "No response")

                    elif user_input == "3":
                        output.info("Getting build summary...")
                        result = await client.call_tool("get_build_summary", {"random_string": "dummy"})
                        # Store the result in the local database for history
                        db.record_tool_call(
                            tool_name="get_build_summary",
                            parameters={},
                            result={"text": result[0].text} if result else None,
                            status="success"
                        )
                        output.output(json.loads(result[0].text) if result else "No response")

                    elif user_input == "4":
                        output.info("Getting full build log...")
                        result = await client.call_tool("get_full_build_log", {"random_string": "dummy"})
                        # Store the result in the local database for history
                        db.record_tool_call(
                            tool_name="get_full_build_log",
                            parameters={},
                            result={"text": result[0].text} if result else None,
                            status="success"
                        )
                        output.output(json.loads(result[0].text) if result else "No response")

                    else:
                        output.error(f"Unknown command: {user_input}")
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
