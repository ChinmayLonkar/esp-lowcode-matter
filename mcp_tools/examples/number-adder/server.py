#!/usr/bin/env python3
"""
Number Adder MCP Tool.
A simple tool that adds two numbers together following the MCP protocol.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Union

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
sys.path.append(root_dir)
from components.path_setup import setup_path
setup_path()

# Import FastMCP modules
from fastmcp import FastMCP
from fastmcp.server.server import stdio_server as stdio_transport

# Import additional base components
from components.database import ToolDatabase
from components.output import get_output_manager, OutputFormat

# Configure logging with environment variable support and optional file logging
log_level = os.environ.get("MCP_LOG_LEVEL", os.environ.get("LOGGING_LEVEL", "INFO")).upper()
numeric_level = getattr(logging, log_level, logging.INFO)
mcp_log_file = os.environ.get("MCP_LOG_FILE")

# Set up handlers
handlers = []

# Always add console handler (controlled by LOGGING_LEVEL for terminal suppression)
console_level = os.environ.get("LOGGING_LEVEL", "INFO").upper()
console_numeric_level = getattr(logging, console_level, logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(console_numeric_level)
handlers.append(console_handler)

# Add file handler if MCP_LOG_FILE is specified
if mcp_log_file:
    file_handler = logging.FileHandler(mcp_log_file)
    file_handler.setLevel(numeric_level)  # Use MCP_LOG_LEVEL for file
    handlers.append(file_handler)

logging.basicConfig(
    level=min(numeric_level, console_numeric_level),  # Use the most permissive level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Suppress verbose logging if console level is WARNING or higher
if console_numeric_level >= logging.WARNING:
    logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.ERROR)
    logging.getLogger('fastmcp').setLevel(logging.ERROR)
elif mcp_log_file:
    # If file logging is enabled, configure FastMCP loggers to use our handlers
    mcp_logger = logging.getLogger('mcp.server.lowlevel.server')
    fastmcp_logger = logging.getLogger('fastmcp')
    mcp_logger.handlers = handlers
    fastmcp_logger.handlers = handlers
    mcp_logger.setLevel(numeric_level)
    fastmcp_logger.setLevel(numeric_level)
    mcp_logger.propagate = False
    fastmcp_logger.propagate = False

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Initialize output manager
output = get_output_manager(format="text", color=True)

# Create FastMCP instance
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

        # Log tool usage
        db.record_tool_call(
            tool_name="add_numbers",
            parameters={"num1": num1, "num2": num2},
            result=result,
            status="success"
        )

        # Output the result with printf style TAG and newline
        output.success(f"ADD_RESULT\n{num1} + {num2} = {result}")

        return {
            "success": True,
            "num1": num1,
            "num2": num2,
            "result": result
        }
    except Exception as e:
        # Log error
        output.error(f"Error adding numbers: {str(e)}")

        # Record error in history
        db.record_tool_call(
            tool_name="add_numbers",
            parameters={"num1": num1, "num2": num2},
            result={"success": False, "error": str(e)},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "error": str(e)
        }

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
