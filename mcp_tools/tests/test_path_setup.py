#!/usr/bin/env python3
"""
Tests for the path_setup module.
This script verifies that the path_setup module works correctly.
"""

import os
import sys
import unittest
import tempfile
from pathlib import Path

# Add the parent directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import the module to test
from mcp_tools.components.path_setup import setup_path, get_root_dir

class TestPathSetup(unittest.TestCase):
    """Test the path_setup module."""

    def test_get_root_dir(self):
        """Test the get_root_dir function."""
        root_dir = get_root_dir()

        # The root directory should exist
        self.assertTrue(os.path.exists(root_dir), "Root directory does not exist")

        # The root directory should contain the mcp_tools directory
        mcp_tools_dir = os.path.join(root_dir, "mcp_tools")
        self.assertTrue(os.path.exists(mcp_tools_dir), "mcp_tools directory not found in root directory")

        # The mcp_tools directory should contain the components directory
        components_dir = os.path.join(mcp_tools_dir, "components")
        self.assertTrue(os.path.exists(components_dir), "components directory not found in mcp_tools directory")

        print(f"Root directory: {root_dir}")
        print("get_root_dir test: PASSED")

    def test_setup_path(self):
        """Test the setup_path function."""
        # Save the original sys.path
        original_path = sys.path.copy()

        try:
            # Call setup_path
            setup_path()

            # Get the root directory
            root_dir = get_root_dir()

            # The root directory should be in sys.path
            self.assertIn(root_dir, sys.path, "Root directory not added to sys.path")

            # Call setup_path again (should not duplicate the path)
            setup_path()

            # Count occurrences of root_dir in sys.path
            occurrences = sys.path.count(root_dir)
            self.assertEqual(occurrences, 1, f"Root directory appears {occurrences} times in sys.path, expected 1")

            print("setup_path test: PASSED")
        finally:
            # Restore the original sys.path
            sys.path = original_path

    def test_module_import(self):
        """Test importing modules after setup_path."""
        # Save the original sys.path
        original_path = sys.path.copy()

        try:
            # Call setup_path
            setup_path()

            # Try importing various modules from the project
            # If imports fail, the test will fail
            from mcp_tools.components.database import ToolDatabase
            from mcp_tools.components.output import get_output_manager
            from mcp_tools.components.network import ApiClient

            # Test creating instances
            db = ToolDatabase(":memory:")  # In-memory database
            output = get_output_manager(format="text", color=False)

            # Test basic functionality
            db.store_data("test_key", "test_value", "test_tool")
            value = db.get_data("test_key", "test_tool")
            self.assertEqual(value, "test_value")

            db.close()
            print("module_import test: PASSED")
        finally:
            # Restore the original sys.path
            sys.path = original_path

def main():
    """Run all tests."""
    print("=== Testing Path Setup ===")

    # Create and run the test suite
    suite = unittest.TestSuite()
    suite.addTest(TestPathSetup("test_get_root_dir"))
    suite.addTest(TestPathSetup("test_setup_path"))
    suite.addTest(TestPathSetup("test_module_import"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(main())
