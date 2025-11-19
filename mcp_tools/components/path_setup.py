#!/usr/bin/env python3
"""
Utility module for setting up Python import paths for MCP tools.
This module ensures that the root directory is in the Python path
so that mcp_tools packages can be imported correctly.
"""

import os
import sys
import inspect

def setup_path():
    """
    Add the root directory to the Python path if it's not already there.
    This allows importing modules from the root directory regardless of
    where the script is run from.

    Usage:
        from mcp_tools.components.path_setup import setup_path
        setup_path()
    """
    # Get the calling module's file path
    caller_frame = inspect.stack()[1]
    caller_file = caller_frame.filename
    caller_dir = os.path.dirname(os.path.abspath(caller_file))

    # Find the root directory (looking for marker files/directories)
    current_dir = caller_dir
    while current_dir and os.path.dirname(current_dir) != current_dir:
        # Check for common root directory indicators
        if (os.path.exists(os.path.join(current_dir, ".git")) or
            os.path.basename(current_dir) == "yolo" or
            os.path.exists(os.path.join(current_dir, "mcp_tools"))):
            break
        current_dir = os.path.dirname(current_dir)

    # If we couldn't find a reasonable root, use 3 levels up from the mcp_tools directory
    if not current_dir or os.path.dirname(current_dir) == current_dir:
        # Find mcp_tools directory and go up to the appropriate level
        if "mcp_tools" in caller_dir:
            mcp_index = caller_dir.find("mcp_tools")
            if mcp_index >= 0:
                mcp_dir = caller_dir[:mcp_index + len("mcp_tools")]
                # Go up to find the root
                current_dir = os.path.dirname(mcp_dir)

        # Fallback to 3 levels up from the calling script
        if not current_dir or os.path.dirname(current_dir) == current_dir:
            current_dir = os.path.abspath(os.path.join(caller_dir, "../../.."))

    # Add the root directory to the Python path if it's not already there
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
        print(f"Added {current_dir} to Python path")

    return current_dir

def get_root_dir():
    """
    Get the root directory of the project.

    Returns:
        The absolute path to the root directory.
    """
    return setup_path()

if __name__ == "__main__":
    # If run directly, just print the root directory
    print(f"Root directory: {setup_path()}")
