#!/usr/bin/env python3
"""
Tests for MCP tools utility scripts.
This script tests the create_tool.py and create_json.py utilities.
"""

import os
import sys
import json
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

class TestCreateTool(unittest.TestCase):
    """Test the create_tool.py script."""

    def setUp(self):
        """Set up the test environment."""
        print("Setting up TestCreateTool...")
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.abspath(os.path.join(self.script_dir, "../.."))
        self.mcp_tools_dir = os.path.join(self.root_dir, "mcp_tools")

        # Path to create_tool.py (now in tools directory)
        self.create_tool_path = os.path.join(self.mcp_tools_dir, "tools", "create_tool.py")

        # Create a temporary test tool in examples folder
        self.test_tool_name = "test-tool-utility"
        self.test_tool_display_name = "Test Tool Utility"
        self.examples_dir = os.path.join(self.mcp_tools_dir, "examples")
        self.test_tool_dir = os.path.join(self.examples_dir, self.test_tool_name)

        # Clean up any existing test tool directory
        if os.path.exists(self.test_tool_dir):
            import shutil
            shutil.rmtree(self.test_tool_dir)

        print(f"Create tool path: {self.create_tool_path}")
        print(f"Test tool dir: {self.test_tool_dir}")
        print("TestCreateTool setup complete.")

    def tearDown(self):
        """Clean up the test environment."""
        # Remove the test tool directory if it exists
        if os.path.exists(self.test_tool_dir):
            import shutil
            shutil.rmtree(self.test_tool_dir)

    def test_create_tool(self):
        """Test the create_tool.py script."""
        print("\n--- Testing create_tool.py ---")

        # Run the create_tool.py script
        result = subprocess.run([
            "python3",
            self.create_tool_path,
            self.test_tool_name,
            "--display-name",
            self.test_tool_display_name
        ], capture_output=True, text=True)

        # Check that the command succeeded
        self.assertEqual(result.returncode, 0, f"create_tool.py failed: {result.stderr}")

        # Check that the tool directory was created in the examples folder
        self.assertTrue(os.path.exists(self.test_tool_dir), "Tool directory was not created")

        # Check that essential files were created
        essential_files = ["server.py", "client.py", "server_http.py", "client_http.py", "README.md"]
        for file in essential_files:
            file_path = os.path.join(self.test_tool_dir, file)
            self.assertTrue(os.path.exists(file_path), f"File not created: {file}")

        # Check that config directory was created
        config_dir = os.path.join(self.test_tool_dir, "config")
        self.assertTrue(os.path.exists(config_dir), "Config directory not created")

        # Check that mcp.json exists in config
        mcp_json_path = os.path.join(config_dir, "mcp.json")
        self.assertTrue(os.path.exists(mcp_json_path), "mcp.json not created")

        # Check content of files for proper tool name substitution
        with open(os.path.join(self.test_tool_dir, "server.py"), "r") as f:
            server_content = f.read()
            self.assertIn(self.test_tool_name, server_content, "Tool name not found in server.py")
            self.assertNotIn("custom-tool", server_content, "Template placeholder 'custom-tool' still present in server.py")

        # Check mcp.json for proper tool configuration
        with open(mcp_json_path, "r") as f:
            mcp_config = json.load(f)
            self.assertIn("mcpServers", mcp_config, "mcpServers not found in mcp.json")
            self.assertIn(self.test_tool_name, mcp_config["mcpServers"], "Tool name not found in mcp.json mcpServers")
            self.assertEqual(
                mcp_config["mcpServers"][self.test_tool_name]["command"],
                "python3",
                "Incorrect command in mcp.json"
            )

            # Check the args list contains the path to server.py
            args = mcp_config["mcpServers"][self.test_tool_name]["args"]
            self.assertTrue(any("server.py" in arg for arg in args), "server.py path not found in mcp.json args")

        print("create_tool.py test: PASSED")
        return True


class TestCreateJson(unittest.TestCase):
    """Test the create_json.py script."""

    def setUp(self):
        """Set up the test environment."""
        print("Setting up TestCreateJson...")
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.abspath(os.path.join(self.script_dir, "../.."))
        self.mcp_tools_dir = os.path.join(self.root_dir, "mcp_tools")

        # Path to create_json.py in tools directory
        self.create_json_path = os.path.join(self.mcp_tools_dir, "tools", "create_json.py")

        # Temp directory for output files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_file = os.path.join(self.temp_dir.name, "combined_mcp.json")

        print(f"Create json path: {self.create_json_path}")
        print(f"Output file: {self.output_file}")
        print("TestCreateJson setup complete.")

    def tearDown(self):
        """Clean up the test environment."""
        # Clean up temp directory
        if hasattr(self, 'temp_dir'):
            self.temp_dir.cleanup()

    def test_create_json_list(self):
        """Test the --list option of create_json.py script."""
        print("\n--- Testing create_json.py --list ---")

        # Run the create_json.py script with --list option
        result = subprocess.run([
            "python3",
            self.create_json_path,
            "--list"
        ], capture_output=True, text=True)

        # Check that the command succeeded
        self.assertEqual(result.returncode, 0, f"create_json.py --list failed: {result.stderr}")

        # Check that output contains "Available MCP tools:"
        self.assertIn("Available MCP tools:", result.stdout, "List output not found")

        print("create_json.py --list test: PASSED")
        return True

    def test_create_json_output(self):
        """Test the output generation of create_json.py script."""
        print("\n--- Testing create_json.py output generation ---")

        # Run the create_json.py script with output file
        result = subprocess.run([
            "python3",
            self.create_json_path,
            "-o", self.output_file
        ], capture_output=True, text=True)

        # Check that the command succeeded
        self.assertEqual(result.returncode, 0, f"create_json.py output generation failed: {result.stderr}")

        # Check that output file was created
        self.assertTrue(os.path.exists(self.output_file), "Output file not created")

        # Check that file contains valid JSON with mcpServers
        with open(self.output_file, "r") as f:
            try:
                data = json.load(f)
                self.assertIn("mcpServers", data, "mcpServers not found in output JSON")
                self.assertIsInstance(data["mcpServers"], dict, "mcpServers is not a dictionary")
            except json.JSONDecodeError:
                self.fail("Output file does not contain valid JSON")

        print("create_json.py output generation test: PASSED")
        return True

    def test_create_json_specific_tool(self):
        """Test specifying a specific tool in create_json.py."""
        print("\n--- Testing create_json.py with specific tool ---")

        # Get available tools first
        list_result = subprocess.run([
            "python3",
            self.create_json_path,
            "--list"
        ], capture_output=True, text=True)

        # Parse the output to get available tools
        lines = list_result.stdout.strip().split('\n')
        tool_lines = [line.strip() for line in lines if line.strip().startswith("- ")]

        # Skip test if no tools available
        if not tool_lines:
            print("No tools available, skipping specific tool test")
            return True

        # Extract the first tool name
        first_tool = tool_lines[0][2:].strip()  # Remove "- " prefix

        # Run create_json.py with the specific tool
        result = subprocess.run([
            "python3",
            self.create_json_path,
            first_tool,
            "-o", self.output_file
        ], capture_output=True, text=True)

        # Check that the command succeeded
        self.assertEqual(result.returncode, 0, f"create_json.py with specific tool failed: {result.stderr}")

        # Check that output contains the specific tool
        self.assertIn(f"Combining configurations for 1 tools:", result.stdout, "Specific tool output not found")
        self.assertIn(f"- {first_tool}", result.stdout, f"Specific tool '{first_tool}' not found in output")

        # Check that output file contains only the specified tool
        with open(self.output_file, "r") as f:
            try:
                data = json.load(f)
                self.assertIn("mcpServers", data, "mcpServers not found in output JSON")
                self.assertIn(first_tool, data["mcpServers"], f"Tool '{first_tool}' not found in output JSON")
                self.assertEqual(len(data["mcpServers"]), 1, "Output JSON contains more than one tool")
            except json.JSONDecodeError:
                self.fail("Output file does not contain valid JSON")

        print("create_json.py specific tool test: PASSED")
        return True


def main():
    """Run all tests."""
    print("=== Testing MCP Tools Utilities ===")

    # Test the create_tool.py script
    try:
        create_tool_test = TestCreateTool()
        create_tool_test.setUp()  # Explicitly call setUp
        create_tool_success = create_tool_test.test_create_tool()
        create_tool_test.tearDown()  # Explicitly call tearDown
    except Exception as e:
        print(f"Error in create_tool test: {str(e)}")
        create_tool_success = False

    # Test the create_json.py script
    try:
        create_json_test = TestCreateJson()
        create_json_test.setUp()  # Explicitly call setUp

        list_success = create_json_test.test_create_json_list()
        output_success = create_json_test.test_create_json_output()
        specific_success = create_json_test.test_create_json_specific_tool()

        create_json_test.tearDown()  # Explicitly call tearDown
        create_json_success = list_success and output_success and specific_success
    except Exception as e:
        print(f"Error in create_json test: {str(e)}")
        create_json_success = False

    if create_tool_success and create_json_success:
        print("\n=== All tool utility tests completed successfully ===")
        return 0
    else:
        print("\n=== Some tool utility tests failed ===")
        return 1

if __name__ == "__main__":
    sys.exit(main())
