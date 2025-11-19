#!/usr/bin/env python3
"""
Script to combine multiple MCP tool configurations into a single JSON file.
This allows for easy integration with MCP clients like Cursor.
"""

import os
import sys
import json
import argparse
import glob
from pathlib import Path

def find_mcp_json_files(tool_names=None):
    """
    Find and return paths to mcp.json files in the examples directory.

    Args:
        tool_names: Optional list of tool names to filter by. If None, all tools are included.

    Returns:
        List of (tool_name, json_path) tuples
    """
    # Get the script directory and mcp_tools directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_tools_dir = os.path.dirname(script_dir)
    examples_dir = os.path.join(mcp_tools_dir, "examples")

    if not os.path.exists(examples_dir):
        print(f"ERROR: Examples directory not found: {examples_dir}")
        return []

    # Find all tool directories in examples
    tool_dirs = [d for d in os.listdir(examples_dir)
                 if os.path.isdir(os.path.join(examples_dir, d))
                 and d != "template"]

    # Filter by provided tool names if any
    if tool_names:
        tool_dirs = [d for d in tool_dirs if d in tool_names]

    # Find mcp.json files
    result = []
    for tool_dir in tool_dirs:
        mcp_json_path = os.path.join(examples_dir, tool_dir, "config", "mcp.json")
        if os.path.exists(mcp_json_path):
            result.append((tool_dir, mcp_json_path))
        else:
            print(f"WARNING: No mcp.json found for tool {tool_dir}")

    return result

def combine_mcp_jsons(json_files, output_file=None):
    """
    Combine multiple mcp.json files into a single JSON configuration.

    Args:
        json_files: List of (tool_name, json_path) tuples
        output_file: Path to output file. If None, print to stdout.

    Returns:
        Combined JSON as a string
    """
    combined = {"mcpServers": {}}

    for tool_name, json_path in json_files:
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)

            if 'mcpServers' in data:
                for server_name, server_config in data['mcpServers'].items():
                    combined['mcpServers'][server_name] = server_config
            else:
                print(f"WARNING: No mcpServers found in {json_path}")
        except Exception as e:
            print(f"ERROR processing {json_path}: {e}")

    # Convert to formatted JSON string
    json_str = json.dumps(combined, indent=4)

    # Write to file or print
    if output_file:
        with open(output_file, 'w') as f:
            f.write(json_str)
        print(f"Combined JSON written to {output_file}")

    return json_str

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Combine multiple MCP tool configurations into a single JSON file."
    )
    parser.add_argument(
        "tools", nargs="*",
        help="Names of tools to include. If omitted, all tools are included."
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file. If omitted, JSON is printed to stdout."
    )
    parser.add_argument(
        "-l", "--list", action="store_true",
        help="List available tools and exit."
    )

    args = parser.parse_args()

    # List all available tools if requested
    if args.list:
        json_files = find_mcp_json_files()
        if json_files:
            print("Available MCP tools:")
            for tool_name, _ in json_files:
                print(f"  - {tool_name}")
        else:
            print("No MCP tools found.")
        return

    # Find and combine JSON files
    json_files = find_mcp_json_files(args.tools if args.tools else None)

    if not json_files:
        print("No matching MCP tool configurations found.")
        return

    # Print what tools were found
    print(f"Combining configurations for {len(json_files)} tools:")
    for tool_name, _ in json_files:
        print(f"  - {tool_name}")

    # Combine and output
    combined_json = combine_mcp_jsons(json_files, args.output)

    # If no output file was specified, print the JSON
    if not args.output:
        print("\nCombined JSON:")
        print(combined_json)
        print("\nCopy the above JSON and paste it into your MCP client configuration.")

if __name__ == "__main__":
    main()
