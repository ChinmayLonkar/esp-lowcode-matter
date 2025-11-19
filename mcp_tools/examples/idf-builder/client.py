#!/usr/bin/env python3
"""
ESP-IDF Builder MCP client.
This client provides a command-line interface for interacting with the ESP-IDF Builder MCP server.
"""

import os
import sys
import json
import logging
import argparse
import traceback
import asyncio
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
from fastmcp.client import PythonStdioTransport

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
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "client.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Parse command line arguments
parser = argparse.ArgumentParser(description="IDF Builder Client")
parser.add_argument(
    "--format",
    choices=["text", "json", "csv", "table"],
    default="text",
    help="Output format"
)
parser.add_argument(
    "--server",
    default="subprocess",
    choices=["subprocess", "http"],
    help="Server connection type"
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
    """Run an interactive loop for the client."""
    output.print("ESP-IDF Builder Client", color="green")
    output.print("Type 'exit' or 'quit' to exit", color="green")

    # Create transport and client
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "server.py")

    # Create the transport
    transport = PythonStdioTransport(
        script_path=server_path,
        python_cmd="python3"
    )

    # Use client as an async context manager
    async with Client(transport) as client:
        # List available tools
        tools = await client.list_tools()
        output.info(f"Connected to server with {len(tools)} tools available")

        # Display menu
        output.print("\nAvailable commands:", color="cyan")
        output.print("  1 - Detect connected ESP32 chip")
        output.print("  2 - Build an ESP32 project")
        output.print("  3 - Get build summary")
        output.print("  4 - Get full build log")
        output.print("  help - Show this help")
        output.print("  exit - Exit the client")

        while True:
            try:
                # Get user input
                user_input = input("\nCommand> ").strip()

                # Check for exit command
                if user_input.lower() in ["exit", "quit"]:
                    output.print("Exiting...", color="yellow")
                    break

                # Process commands
                if user_input == "help":
                    output.print("\nAvailable commands:", color="cyan")
                    output.print("  1 - Detect connected ESP32 chip")
                    output.print("  2 - Build an ESP32 project")
                    output.print("  3 - Get build summary")
                    output.print("  4 - Get full build log")
                    output.print("  help - Show this help")
                    output.print("  exit - Exit the client")

                elif user_input == "1":
                    # Detect chip
                    output.info("Detecting connected ESP32 chip...")
                    try:
                        result = await client.call_tool("detect_chip")
                        chip_info = json.loads(result[0].text) if result else {}

                        if chip_info.get("success", False):
                            output.success("Chip detected successfully!")
                            if "chip_type" in chip_info:
                                output.print(f"Chip type: {chip_info['chip_type']}", color="green")
                            if "features" in chip_info:
                                output.print(f"Features: {chip_info['features']}")
                            if "mac" in chip_info:
                                output.print(f"MAC Address: {chip_info['mac']}")
                        else:
                            output.error("Failed to detect chip")
                            if "message" in chip_info:
                                output.print(f"Error: {chip_info['message']}")
                    except Exception as e:
                        output.error(f"Error detecting chip: {str(e)}")
                        logger.error(f"Error in detect_chip: {e}")
                        traceback.print_exc()

                elif user_input == "2":
                    # Build project
                    project_path = input("Enter the path to your ESP32 project: ")
                    project_path = os.path.expanduser(project_path)

                    output.info(f"Building project at {project_path}...")
                    try:
                        result = await client.call_tool("build_project", {"project_path": project_path})
                        build_result = json.loads(result[0].text) if result else {}

                        if build_result.get("success", False):
                            output.success("Build completed successfully!")
                            if "warning_count" in build_result:
                                output.print(f"Warnings: {build_result['warning_count']}")
                            if "summary" in build_result:
                                output.print("\nBuild Summary:", color="green")
                                output.print(build_result["summary"])
                        else:
                            output.error("Build failed")
                            if "error_count" in build_result:
                                output.print(f"Errors: {build_result['error_count']}")
                            if "warning_count" in build_result:
                                output.print(f"Warnings: {build_result['warning_count']}")
                            if "summary" in build_result:
                                output.print("\nBuild Summary:", color="red")
                                output.print(build_result["summary"])
                            elif "message" in build_result:
                                output.print(f"Error: {build_result['message']}")
                    except Exception as e:
                        output.error(f"Error building project: {str(e)}")
                        logger.error(f"Error in build_project: {e}")
                        traceback.print_exc()

                elif user_input == "3":
                    # Get build summary
                    output.info("Getting build summary...")
                    try:
                        result = await client.call_tool("get_build_summary")
                        if result and result[0].text:
                            output.print("\nBuild Summary:", color="blue")
                            output.print(result[0].text)
                        else:
                            output.warning("No build summary available. Please run a build first.")
                    except Exception as e:
                        output.error(f"Error getting build summary: {str(e)}")
                        logger.error(f"Error in get_build_summary: {e}")
                        traceback.print_exc()

                elif user_input == "4":
                    # Get full build log
                    output.info("Getting full build log...")
                    try:
                        result = await client.call_tool("get_full_build_log")

                        if result and result[0].text:
                            save_to_file = input("Would you like to save the log to a file? (y/n): ").lower() == 'y'

                            if save_to_file:
                                file_path = input("Enter the file path to save the log: ")
                                file_path = os.path.expanduser(file_path)

                                try:
                                    with open(file_path, 'w') as f:
                                        f.write(result[0].text)
                                    output.success(f"Log saved to {file_path}")
                                except Exception as file_e:
                                    output.error(f"Error saving log to file: {str(file_e)}")
                                    output.print("\nBuild Log:", color="blue")
                                    output.print(result[0].text)
                            else:
                                # Print with pagination
                                output.print("\nBuild Log:", color="blue")
                                lines = result[0].text.split('\n')
                                page_size = 30

                                for i in range(0, len(lines), page_size):
                                    page = lines[i:i+page_size]
                                    output.print('\n'.join(page))

                                    if i + page_size < len(lines):
                                        cont = input("Press Enter to continue, 'q' to quit: ")
                                        if cont.lower() == 'q':
                                            break
                        else:
                            output.warning("No build log available. Please run a build first.")
                    except Exception as e:
                        output.error(f"Error getting build log: {str(e)}")
                        logger.error(f"Error in get_full_build_log: {e}")
                        traceback.print_exc()

                else:
                    output.error(f"Unknown command: {user_input}")
                    output.print("Type 'help' for available commands", color="yellow")

            except Exception as e:
                output.error(f"Error: {str(e)}")
                logger.error(f"Error in command processing: {e}")
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(interactive_loop())
