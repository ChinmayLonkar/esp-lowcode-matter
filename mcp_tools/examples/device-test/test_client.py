#!/usr/bin/env python3
"""
Test script to verify client-server communication for execute_tests
"""

import asyncio
import sys
import os

# Add parent directories to path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from mcp_tools.components.client import MCPClient

async def test_execute_tests():
    """Test the execute_tests functionality through MCP client"""
    print('Testing execute_tests through MCP client...')

    # Create MCP client
    client = MCPClient(server_mode="subprocess", server_script="server.py")

    try:
        # Connect to server
        await client.connect()
        print('✓ Connected to server')

        # List available tools
        tools = await client.list_tools()
        print(f'✓ Found {len(tools)} tools')

        # Check if execute_tests is available
        execute_tests_tool = None
        for tool in tools:
            if tool.get('name') == 'execute_tests':
                execute_tests_tool = tool
                break

        if execute_tests_tool:
            print('✓ execute_tests tool found')
        else:
            print('✗ execute_tests tool not found')
            print('Available tools:')
            for tool in tools:
                print(f'  - {tool.get("name")}')
            return

        # Test simple delay command
        print('\nTesting simple delay command...')
        result = await client.call_tool('execute_tests', {
            'steps': ['delay 1']
        })

        print(f'Result: {result}')

        # Test with mock log search (this will fail but we can see the structure)
        print('\nTesting log search command...')
        result = await client.call_tool('execute_tests', {
            'steps': ['search log "test pattern" 2']
        })

        print(f'Result: {result}')

    except Exception as e:
        print(f'✗ Error: {e}')
        import traceback
        traceback.print_exc()

    finally:
        await client.close()
        print('✓ Client closed')

if __name__ == "__main__":
    asyncio.run(test_execute_tests())
