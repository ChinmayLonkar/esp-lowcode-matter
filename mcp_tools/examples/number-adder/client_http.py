#!/usr/bin/env python3
"""
HTTP client for the Number Adder MCP tool.
This is a simplified version that only provides the add_numbers functionality.
This client connects to the MCP HTTP server to call the number adding tool.
"""

import os
import sys
import json
import argparse
import asyncio
from typing import Dict, List, Any, Optional, Union

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
sys.path.append(root_dir)
from components.path_setup import setup_path
setup_path()

# Import MCP client
from fastmcp import Client
from fastmcp.client.transports import HttpTransport

# Import additional base components
from components.output import get_output_manager, OutputFormat

# Parse command line arguments
parser = argparse.ArgumentParser(description="Number Adder HTTP Client")
parser.add_argument(
    "--host",
    default="localhost",
    help="Host to connect to"
)
parser.add_argument(
    "--port",
    type=int,
    default=8000,
    help="Port to connect to"
)
parser.add_argument(
    "--format",
    choices=["text", "json", "csv", "table"],
    default="text",
    help="Output format"
)
parser.add_argument(
    "--color",
    action="store_true",
    default=True,
    help="Enable colored output"
)
parser.add_argument(
    "numbers",
    nargs="*",
    help="Numbers to add (if provided)"
)
args = parser.parse_args()

# Initialize output manager with selected format
output = get_output_manager(format=args.format, color=args.color)

async def main():
    """Main entry point for the client."""
    # Set up HTTP transport
    url = f"http://{args.host}:{args.port}"

    # Create the transport
    transport = HttpTransport(url)

    # Use client as an async context manager
    async with Client(transport) as client:
        # If numbers are provided as command line arguments, add them
        if len(args.numbers) >= 2:
            try:
                # Convert the first two arguments to numbers
                num1 = args.numbers[0]
                num2 = args.numbers[1]

                try:
                    num1 = int(num1)
                except ValueError:
                    num1 = float(num1)

                try:
                    num2 = int(num2)
                except ValueError:
                    num2 = float(num2)

                # Call the add_numbers tool
                output.info(f"Adding numbers: {num1} + {num2}")
                result = await client.call_tool("add_numbers", {"num1": num1, "num2": num2})

                if result:
                    output.output(json.loads(result[0].text))
                else:
                    output.error("No result returned from server")

                return
            except Exception as e:
                output.error(f"Error: {str(e)}")
                return

        # Interactive mode
        output.print("Number Adder HTTP Client", color="green")
        output.print(f"Connected to server at {url}", color="green")
        output.print("Type 'exit' or 'quit' to exit", color="yellow")
        output.print("Available commands:", color="cyan")
        output.print("  add NUMBER1 NUMBER2 - Add two numbers together")
        output.print("  help - Show this help")

        # List available tools
        tools = await client.list_tools()
        tool_names = [t["name"] for t in tools]
        output.info(f"Available tools: {', '.join(tool_names)}")

        while True:
            try:
                # Get user input
                user_input = input("\nCommand> ").strip()

                # Check for exit command
                if user_input.lower() in ["exit", "quit"]:
                    output.print("Exiting...", color="yellow")
                    break

                # Process commands
                parts = user_input.split()
                command = parts[0].lower() if parts else ""

                if command == "help":
                    output.print("Available commands:", color="cyan")
                    output.print("  add NUMBER1 NUMBER2 - Add two numbers together")
                    output.print("  help - Show this help")

                elif command == "add":
                    if len(parts) < 3:
                        output.error("Missing number parameters")
                        continue

                    try:
                        # Get numbers from input
                        num1 = parts[1]
                        num2 = parts[2]

                        # Try to convert to numbers
                        try:
                            num1 = int(num1)
                        except ValueError:
                            try:
                                num1 = float(num1)
                            except ValueError:
                                output.error(f"Invalid number: {num1}")
                                continue

                        try:
                            num2 = int(num2)
                        except ValueError:
                            try:
                                num2 = float(num2)
                            except ValueError:
                                output.error(f"Invalid number: {num2}")
                                continue

                        # Call the add_numbers tool
                        output.info(f"Adding numbers: {num1} + {num2}")
                        result = await client.call_tool("add_numbers", {"num1": num1, "num2": num2})

                        if result:
                            output.output(json.loads(result[0].text))
                        else:
                            output.error("No result returned from server")

                    except Exception as e:
                        output.error(f"Error: {str(e)}")

                else:
                    output.error(f"Unknown command: {command}")
                    output.print("Type 'help' for available commands", color="yellow")

            except Exception as e:
                output.error(f"Error: {str(e)}")
                continue
            except KeyboardInterrupt:
                output.print("\nExiting...", color="yellow")
                break

if __name__ == "__main__":
    asyncio.run(main())
