#!/usr/bin/env python3
"""
Number Adder Client.
This is a client for the Number Adder MCP tool.
"""

import os
import sys
import json
import logging
import argparse
from typing import Dict, List, Any, Optional

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
from fastmcp.client.transports import PythonStdioTransport

# Import additional base components
from components.database import ToolDatabase
from components.output import get_output_manager, OutputFormat

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
parser = argparse.ArgumentParser(description="Number Adder Client")
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
parser.add_argument(
    "numbers",
    nargs="*",
    help="Numbers to add (if provided)"
)
args = parser.parse_args()

# Initialize output manager with selected format
output = get_output_manager(format=args.format, color=args.color)


async def interactive_loop():
    """Run an interactive loop for the client."""
    output.print("Number Adder Client", color="green")
    output.print("Type 'exit' or 'quit' to exit", color="green")
    output.print("Available commands:", color="cyan")
    output.print("  add NUMBER1 NUMBER2 - Add two numbers together")
    output.print("  help - Show this help")

    # Create transport and client
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "server.py")

    # Create the transport
    transport = PythonStdioTransport(
        script_path=server_path,
        python_cmd="python3"
    )

    # Process command line arguments if provided
    if len(args.numbers) >= 2:
        try:
            # Convert the numbers
            try:
                num1 = int(args.numbers[0])
            except ValueError:
                num1 = float(args.numbers[0])

            try:
                num2 = int(args.numbers[1])
            except ValueError:
                num2 = float(args.numbers[1])

            output.info(f"Adding numbers: {num1} + {num2}")

            # Use client as an async context manager
            async with Client(transport) as client:
                result = await client.call_tool("add_numbers", {"num1": num1, "num2": num2})

                if result:
                    result_data = json.loads(result[0].text)
                    output.output(result_data)
                else:
                    output.error("No result returned from server")

            return
        except Exception as e:
            output.error(f"Error: {str(e)}")

    # Use client as an async context manager for interactive mode
    async with Client(transport) as client:
        # List available tools
        tools = await client.list_tools()
        output.info(f"Connected to server with {len(tools)} tools available")

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
                        output.error("Missing number parameters. Usage: add NUMBER1 NUMBER2")
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

                        output.info(f"Adding numbers: {num1} + {num2}")
                        result = await client.call_tool("add_numbers", {"num1": num1, "num2": num2})

                        # Store the result in the local database for history
                        if result:
                            result_data = json.loads(result[0].text)
                            db.record_tool_call(
                                tool_name="add_numbers",
                                parameters={"num1": num1, "num2": num2},
                                result=result_data,
                                status="success"
                            )
                            output.output(result_data)
                        else:
                            output.error("No result returned from server")

                    except Exception as e:
                        output.error(f"Error adding numbers: {str(e)}")

                else:
                    output.error(f"Unknown command: {command}")
                    output.print("Type 'help' for available commands", color="yellow")

            except Exception as e:
                output.error(f"Error: {str(e)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_loop())
