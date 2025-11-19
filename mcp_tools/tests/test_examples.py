#!/usr/bin/env python3
"""
End-to-end tests for MCP tools examples.
This script verifies that the example tools are working correctly.
"""

import os
import sys
import json
import asyncio
import tempfile
import subprocess
import unittest
import time
from typing import Dict, Any

# Add the parent directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import path setup and set up the paths
from mcp_tools.components.path_setup import setup_path, get_root_dir
setup_path()

# Import required modules for testing
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

class TestToolTemplate(unittest.TestCase):
    """Test the template example."""

    async def async_setup(self):
        """Set up the test environment."""
        # Path to the example server script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_dir = os.path.abspath(os.path.join(script_dir, "../examples/template"))
        self.server_path = os.path.join(self.template_dir, "server.py")

        # Create temp directory for test data
        self.temp_dir = tempfile.TemporaryDirectory()

        # Create transport and client
        self.transport = PythonStdioTransport(
            script_path=self.server_path,
            python_cmd="python3"
        )
        self.client = Client(self.transport)
        # Client doesn't have a start method, it uses context manager pattern

    async def async_teardown(self):
        """Clean up the test environment."""
        if hasattr(self, 'client'):
            # Client doesn't have a stop method, transport is closed automatically
            pass
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()

    async def test_sample_tool(self):
        """Test the sample_tool functionality."""
        # Test the sample tool that processes text
        result = await self.client.call_tool("sample_tool", {"text": "hello world"})
        self.assertTrue(result)
        self.assertEqual(result[0].text, "HELLO WORLD")

    async def test_data_storage(self):
        """Test data storage and retrieval."""
        # Test saving data
        save_result = await self.client.call_tool("save_data", {
            "key": "test_key",
            "value": {"name": "Test Data", "value": 42}
        })
        self.assertTrue(save_result)
        response = json.loads(save_result[0].text)
        self.assertTrue(response["success"])
        self.assertEqual(response["key"], "test_key")

        # Test retrieving data
        get_result = await self.client.call_tool("get_data", {"key": "test_key"})
        self.assertTrue(get_result)
        response = json.loads(get_result[0].text)
        self.assertTrue(response["success"])
        self.assertEqual(response["key"], "test_key")
        self.assertEqual(response["data"]["name"], "Test Data")
        self.assertEqual(response["data"]["value"], 42)

        # Test retrieving non-existent data
        get_result = await self.client.call_tool("get_data", {"key": "nonexistent"})
        self.assertTrue(get_result)
        response = json.loads(get_result[0].text)
        self.assertFalse(response["success"])

    async def test_history(self):
        """Test tool history functionality."""
        # First call some tools to create history
        await self.client.call_tool("sample_tool", {"text": "test history"})
        await self.client.call_tool("save_data", {"key": "history_test", "value": "history_value"})

        # Get the history
        result = await self.client.call_tool("get_history", {})
        self.assertTrue(result)
        history = json.loads(result[0].text)
        self.assertIsInstance(history, list)
        self.assertGreaterEqual(len(history), 2)  # At least the two calls we just made

        # Test filtering by tool name
        result = await self.client.call_tool("get_history", {"tool_name": "sample_tool"})
        self.assertTrue(result)
        history = json.loads(result[0].text)
        self.assertIsInstance(history, list)
        for entry in history:
            self.assertEqual(entry["tool_name"], "sample_tool")

    async def run_all_tests(self):
        """Run all tests in sequence."""
        try:
            # Setup
            await self.async_setup()

            # Run tests with the client as a context manager
            async with self.client:
                print("\n--- Testing template sample_tool ---")
                await self.test_sample_tool()
                print("sample_tool test: PASSED")

                print("\n--- Testing template data storage ---")
                await self.test_data_storage()
                print("data storage test: PASSED")

                print("\n--- Testing template history ---")
                await self.test_history()
                print("history test: PASSED")

        except Exception as e:
            print(f"ERROR: {str(e)}")
            return False
        finally:
            # Teardown
            await self.async_teardown()

        return True


class TestNumberAdder(unittest.TestCase):
    """Test the number-adder example."""

    async def async_setup(self):
        """Set up the test environment."""
        # Path to the example server script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.example_dir = os.path.abspath(os.path.join(script_dir, "../examples/number-adder"))
        self.server_path = os.path.join(self.example_dir, "server.py")

        print(f"Setting up number-adder test with server at {self.server_path}")

        # Verify that the server script exists
        if not os.path.exists(self.server_path):
            raise FileNotFoundError(f"Server script not found: {self.server_path}")

        # Create temp directory for test data
        self.temp_dir = tempfile.TemporaryDirectory()

        # First test if we can run the server directly to check for any startup issues
        try:
            # Run the server script with a timeout to see if it starts properly
            result = subprocess.run(
                ["python3", self.server_path],
                capture_output=True,
                text=True,
                timeout=2  # Give it 2 seconds to start up
            )
            if result.returncode != 0:
                print(f"WARNING: Server script returned non-zero exit code: {result.returncode}")
                print(f"Server stdout: {result.stdout}")
                print(f"Server stderr: {result.stderr}")
        except subprocess.TimeoutExpired:
            # This is actually expected, as the server will keep running and time out
            pass
        except Exception as e:
            print(f"WARNING: Error starting server directly: {str(e)}")

        # Create transport and client
        try:
            self.transport = PythonStdioTransport(
                script_path=self.server_path,
                python_cmd="python3"
            )
            self.client = Client(self.transport)
        except Exception as e:
            print(f"ERROR: Failed to create client: {str(e)}")
            raise

    async def async_teardown(self):
        """Clean up the test environment."""
        if hasattr(self, 'client'):
            # Client doesn't have a stop method, transport is closed automatically
            pass
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()

    async def test_add_integers(self):
        """Test adding two integers."""
        try:
            # Test adding two integers
            result = await self.client.call_tool("add_numbers", {"num1": 5, "num2": 7})
            self.assertTrue(result)

            # Parse the JSON response
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False), "Addition operation failed")
                self.assertEqual(response.get("num1"), 5, "First number incorrect in response")
                self.assertEqual(response.get("num2"), 7, "Second number incorrect in response")
                self.assertEqual(response.get("result"), 12, "Result incorrect in response")
            except json.JSONDecodeError:
                # If it's not JSON, check for plain text format
                self.assertIn("5 + 7 = 12", output_text)

            # Test adding negative numbers
            result = await self.client.call_tool("add_numbers", {"num1": -3, "num2": 8})
            self.assertTrue(result)
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False))
                self.assertEqual(response.get("num1"), -3)
                self.assertEqual(response.get("num2"), 8)
                self.assertEqual(response.get("result"), 5)
            except json.JSONDecodeError:
                self.assertIn("-3 + 8 = 5", output_text)

            # Test adding zeros
            result = await self.client.call_tool("add_numbers", {"num1": 0, "num2": 0})
            self.assertTrue(result)
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False))
                self.assertEqual(response.get("num1"), 0)
                self.assertEqual(response.get("num2"), 0)
                self.assertEqual(response.get("result"), 0)
            except json.JSONDecodeError:
                self.assertIn("0 + 0 = 0", output_text)

        except Exception as e:
            print(f"ERROR in test_add_integers: {str(e)}")
            raise

    async def test_add_floats(self):
        """Test adding floating point numbers."""
        try:
            # Test adding two floats
            result = await self.client.call_tool("add_numbers", {"num1": 3.5, "num2": 2.7})
            self.assertTrue(result)
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False))
                self.assertEqual(response.get("num1"), 3.5)
                self.assertEqual(response.get("num2"), 2.7)
                self.assertAlmostEqual(response.get("result"), 6.2, places=1)
            except json.JSONDecodeError:
                self.assertIn("3.5 + 2.7 = 6.2", output_text)

            # Test adding integer and float
            result = await self.client.call_tool("add_numbers", {"num1": 10, "num2": 0.5})
            self.assertTrue(result)
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False))
                self.assertEqual(response.get("num1"), 10)
                self.assertEqual(response.get("num2"), 0.5)
                self.assertEqual(response.get("result"), 10.5)
            except json.JSONDecodeError:
                self.assertIn("10 + 0.5 = 10.5", output_text)

            # Test adding float that results in an integer
            result = await self.client.call_tool("add_numbers", {"num1": 2.5, "num2": 3.5})
            self.assertTrue(result)
            output_text = result[0].text
            try:
                response = json.loads(output_text)
                self.assertTrue(response.get("success", False))
                self.assertEqual(response.get("num1"), 2.5)
                self.assertEqual(response.get("num2"), 3.5)
                self.assertEqual(response.get("result"), 6)  # Should be converted to int
            except json.JSONDecodeError:
                self.assertIn("2.5 + 3.5 = 6", output_text)

        except Exception as e:
            print(f"ERROR in test_add_floats: {str(e)}")
            raise

    async def run_all_tests(self):
        """Run all tests in sequence."""
        try:
            # Setup
            await self.async_setup()

            # Run tests with the client as a context manager
            try:
                async with self.client:
                    print("\n--- Testing number-adder with integers ---")
                    try:
                        await self.test_add_integers()
                        print("integer addition test: PASSED")
                    except Exception as e:
                        print(f"integer addition test FAILED: {str(e)}")
                        return False

                    print("\n--- Testing number-adder with floats ---")
                    try:
                        await self.test_add_floats()
                        print("float addition test: PASSED")
                    except Exception as e:
                        print(f"float addition test FAILED: {str(e)}")
                        return False
            except Exception as e:
                print(f"ERROR during client context: {str(e)}")
                return False

        except Exception as e:
            print(f"ERROR during setup: {str(e)}")
            return False
        finally:
            # Teardown
            await self.async_teardown()

        return True


async def main():
    """Run all tests."""
    print("=== Testing MCP Tools Examples ===")

    # Test the template example
    template_test = TestToolTemplate()
    template_success = await template_test.run_all_tests()

    # Check if number-adder example is properly installed
    script_dir = os.path.dirname(os.path.abspath(__file__))
    number_adder_path = os.path.abspath(os.path.join(script_dir, "../examples/number-adder"))
    number_adder_success = True  # Default to True if we skip the test

    if os.path.exists(number_adder_path) and os.path.isdir(number_adder_path):
        # Test the number-adder example
        print("\n=== Testing number-adder tool ===")
        try:
            number_adder_test = TestNumberAdder()
            number_adder_success = await number_adder_test.run_all_tests()
        except Exception as e:
            print(f"ERROR setting up number-adder test: {str(e)}")
            number_adder_success = False
    else:
        print("\n=== Skipping number-adder test (tool not installed) ===")

    # Print overall result
    print("\n=== Test Summary ===")
    print(f"Template tests: {'PASSED' if template_success else 'FAILED'}")
    if os.path.exists(number_adder_path) and os.path.isdir(number_adder_path):
        print(f"Number-adder tests: {'PASSED' if number_adder_success else 'FAILED'}")
    else:
        print("Number-adder tests: SKIPPED (tool not installed)")

    if template_success and number_adder_success:
        print("\n=== All example tests completed successfully ===")
        return 0
    else:
        print("\n=== Some tests failed ===")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
