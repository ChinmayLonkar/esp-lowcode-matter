#!/usr/bin/env python3
"""
Common MCP client for interacting with any server.py file in the mcp_tools subdirectories.

This client provides two main functions:
1. list_tools: List all tools available in a specific server
2. call_tool: Call a specific tool with parameters

Usage:
    # List tools in a server
    python common_client.py --list-tools --server idf-builder

    # Call a tool with parameters
    python common_client.py --call-tool build_project --server idf-builder --params '{"project_path": "/path/to/project"}'
"""

import os
import sys
import json
import asyncio
import argparse
from typing import Dict, List, Any, Optional
from pathlib import Path

# Add the parent directory to sys.path to find local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from fastmcp import Client
    from fastmcp.client.transports import PythonStdioTransport
except ImportError:
    print("Error: fastmcp package not found. Please make sure it's installed.")
    sys.exit(1)


class MCPCommonClient:
    """Common client for interacting with MCP servers in subdirectories."""

    def __init__(self, log_level: str = "WARNING", keep_alive: bool = False):
        """Initialize the MCP common client."""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.servers = self._find_servers()
        self.log_level = log_level
        self.keep_alive = keep_alive
        
        # Connection pool for persistent connections
        self._active_clients: Dict[str, Client] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}

    def _find_servers(self) -> Dict[str, str]:
        """Find all server.py files in subdirectories.

        Returns:
            Dict mapping server names to their script paths
        """
        servers = {}

        # Directories to search
        search_dirs = [
            os.path.join(self.base_dir, "examples"),
            self.base_dir
        ]

        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue

            # Find all directories under the search_dir
            for dirpath, dirnames, filenames in os.walk(search_dir):
                # Skip the base directory itself
                if dirpath == self.base_dir:
                    continue

                # Check if this directory contains a server.py file
                if "server.py" in filenames:
                    # Use the directory name as the server name
                    server_name = os.path.basename(dirpath)
                    server_path = os.path.join(dirpath, "server.py")

                    # Only add if not already found
                    if server_name not in servers:
                        servers[server_name] = server_path

        return servers

    def get_server_path(self, server_name: str) -> Optional[str]:
        """Get the path to a server script by name.

        Args:
            server_name: Name of the server

        Returns:
            Path to the server script or None if not found
        """
        # Exact match
        if server_name in self.servers:
            return self.servers[server_name]

        # Case-insensitive match
        for name, path in self.servers.items():
            if name.lower() == server_name.lower():
                return path

        # Try to find it directly
        custom_path = os.path.join(self.base_dir, server_name, "server.py")
        if os.path.exists(custom_path):
            return custom_path

        # Not found
        return None

    def list_available_servers(self) -> List[str]:
        """List all available servers.

        Returns:
            List of server names
        """
        return sorted(list(self.servers.keys()))

    async def _create_client(self, server_path: str) -> Client:
        """Create a FastMCP client for a specific server.

        Args:
            server_path: Path to the server.py file

        Returns:
            FastMCP Client instance
        """
        # Create a transport that runs the specified server script
        # Pass through logging level environment variables
        env = os.environ.copy()
        env["LOGGING_LEVEL"] = self.log_level

        transport = PythonStdioTransport(
            script_path=server_path,
            python_cmd="python3",
            env=env
        )

        # Create and return the client
        return Client(transport)

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """List all tools available in a specific server.

        Args:
            server_name: Name of the server

        Returns:
            List of tool definitions

        Raises:
            ValueError: If server not found
        """
        server_path = self.get_server_path(server_name)
        if not server_path:
            raise ValueError(f"Server '{server_name}' not found. Available servers: {', '.join(self.list_available_servers())}")

        # Create client and list tools
        async with await self._create_client(server_path) as client:
            tools = await client.list_tools()

            # Convert tools to a simpler format
            tool_list = []
            for tool in tools:
                tool_info = {
                    "name": tool.name,
                    "description": tool.description
                }

                # Add parameters if available
                if hasattr(tool, "parameters") and tool.parameters:
                    tool_info["parameters"] = tool.parameters

                tool_list.append(tool_info)

            return tool_list

    async def _get_or_create_client(self, server_name: str) -> Client:
        """Get existing client or create new one with connection pooling."""
        server_path = self.get_server_path(server_name)
        if not server_path:
            raise ValueError(f"Server '{server_name}' not found. Available servers: {', '.join(self.list_available_servers())}")
        
        # Get or create lock for this server
        if server_name not in self._connection_locks:
            self._connection_locks[server_name] = asyncio.Lock()
        
        async with self._connection_locks[server_name]:
            # Check if we have an active client
            if self.keep_alive and server_name in self._active_clients:
                client = self._active_clients[server_name]
                try:
                    # Test if client is still alive
                    await client.list_tools()
                    return client
                except Exception:
                    # Client died, remove it
                    del self._active_clients[server_name]
            
            # Create new client and initialize it properly
            transport = PythonStdioTransport(
                script_path=server_path,
                python_cmd="python3",
                env={"LOGGING_LEVEL": self.log_level}
            )
            
            client = Client(transport)
            
            # Initialize the client connection
            await client.__aenter__()
            
            if self.keep_alive:
                # Store for reuse
                self._active_clients[server_name] = client
            
            return client

    async def call_tool(self, server_name: str, tool_name: str, params: Dict[str, Any] = None) -> Any:
        """Call a tool on a specific server.

        Args:
            server_name: Name of the server
            tool_name: Name of the tool to call
            params: Parameters to pass to the tool (default: None)

        Returns:
            Result of the tool call

        Raises:
            ValueError: If server not found
        """
        if self.keep_alive:
            # Use persistent connection
            client = await self._get_or_create_client(server_name)
            
            # Check if the tool exists
            tools = await client.list_tools()
            tool_names = [tool.name for tool in tools]

            if tool_name not in tool_names:
                raise ValueError(f"Tool '{tool_name}' not found in server '{server_name}'. Available tools: {', '.join(tool_names)}")

            # Call the tool with parameters
            result = await client.call_tool(tool_name, params or {})
            return result
        else:
            # Use original single-use client behavior
            server_path = self.get_server_path(server_name)
            if not server_path:
                raise ValueError(f"Server '{server_name}' not found. Available servers: {', '.join(self.list_available_servers())}")

            # Create client and call tool
            async with await self._create_client(server_path) as client:
                # Check if the tool exists
                tools = await client.list_tools()
                tool_names = [tool.name for tool in tools]

                if tool_name not in tool_names:
                    raise ValueError(f"Tool '{tool_name}' not found in server '{server_name}'. Available tools: {', '.join(tool_names)}")

                # Call the tool with parameters
                result = await client.call_tool(tool_name, params or {})
                return result

    async def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all tools from all available servers.

        Returns:
            Dictionary mapping server names to their tool lists
        """
        all_tools = {}

        for server_name in self.servers.keys():
            try:
                tools = await self.list_tools(server_name)
                all_tools[server_name] = tools
            except Exception as e:
                print(f"Warning: Could not list tools from server '{server_name}': {e}")

        return all_tools

    async def find_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Find which server provides a specific tool.

        Args:
            tool_name: Name of the tool to find

        Returns:
            Server name that provides the tool, or None if not found
        """
        for server_name in self.servers.keys():
            try:
                tools = await self.list_tools(server_name)
                if any(tool["name"] == tool_name for tool in tools):
                    return server_name
            except Exception:
                continue

        return None
    
    async def cleanup_connections(self):
        """Clean up all active connections."""
        for server_name, client in self._active_clients.items():
            try:
                # Properly close the client using async context manager exit
                await client.__aexit__(None, None, None)
            except Exception as e:
                print(f"Warning: Error closing client for {server_name}: {e}")
        
        self._active_clients.clear()
        self._connection_locks.clear()

    async def call_tool_auto(self, tool_name: str, params: Dict[str, Any] = None) -> Any:
        """Call a tool on the appropriate server automatically.

        Args:
            tool_name: Name of the tool to call
            params: Parameters to pass to the tool (default: None)

        Returns:
            Result of the tool call

        Raises:
            ValueError: If tool not found on any server
        """
        server_name = await self.find_server_for_tool(tool_name)

        if not server_name:
            raise ValueError(f"Tool '{tool_name}' not found on any available server")

        print(f"Found tool '{tool_name}' on server '{server_name}'")
        return await self.call_tool(server_name, tool_name, params)


async def main():
    """Main entry point for the command-line interface."""
    parser = argparse.ArgumentParser(description="Common MCP client for interacting with any server in mcp_tools")

    # Action group (list tools or call tool)
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--list-tools", action="store_true", help="List all tools available across all servers")
    action_group.add_argument("--call-tool", metavar="TOOL", help="Call a specific tool (will auto-detect the server)")

    # Tool parameters (for call-tool)
    parser.add_argument("--params", help="JSON string of parameters to pass to the tool")

    # List servers
    parser.add_argument("--list-servers", action="store_true", help="List all available servers")

    # Optional server filtering (not required)
    parser.add_argument("--server", help="Optional: Filter to specific server")

    args = parser.parse_args()

    # Create client
    client = MCPCommonClient()

    # List servers if requested
    if args.list_servers:
        servers = client.list_available_servers()
        print("Available servers:")
        for server in servers:
            print(f"  - {server}")
        return

    try:
        if args.list_tools:
            if args.server:
                # List tools for specific server
                tools = await client.list_tools(args.server)
                print(f"Tools available in server '{args.server}':")
                for tool in tools:
                    print(f"  - {tool['name']}: {tool['description']}")

                    # Show parameters if available
                    if "parameters" in tool:
                        print("    Parameters:")
                        for param_name, param_info in tool["parameters"].items():
                            param_type = param_info.get("type", "unknown")
                            required = "required" if param_info.get("required", False) else "optional"
                            print(f"      - {param_name} ({param_type}, {required})")
            else:
                # List tools from all servers
                all_tools = await client.list_all_tools()

                if not all_tools:
                    print("No tools found in any server.")
                    return

                print("Available tools by server:")
                for server_name, tools in all_tools.items():
                    print(f"\n[{server_name}]")
                    for tool in tools:
                        print(f"  - {tool['name']}: {tool['description']}")

                        # Show parameters if available
                        if "parameters" in tool:
                            print("    Parameters:")
                            for param_name, param_info in tool["parameters"].items():
                                param_type = param_info.get("type", "unknown")
                                required = "required" if param_info.get("required", False) else "optional"
                                print(f"      - {param_name} ({param_type}, {required})")

        elif args.call_tool:
            # Parse parameters
            params = {}
            if args.params:
                try:
                    params = json.loads(args.params)
                except json.JSONDecodeError:
                    print("Error: --params must be a valid JSON string")
                    sys.exit(1)

            # Call the tool (with or without server specification)
            if args.server:
                print(f"Calling tool '{args.call_tool}' on server '{args.server}' with parameters: {params}")
                result = await client.call_tool(args.server, args.call_tool, params)
            else:
                print(f"Looking for tool '{args.call_tool}' across all servers...")
                result = await client.call_tool_auto(args.call_tool, params)

            # Print the result
            print("\nResult:")
            try:
                # Try to serialize as JSON
                print(json.dumps(result, indent=2))
            except (TypeError, json.JSONDecodeError):
                # Fall back to simple string representation
                print(result)

    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
