#!/usr/bin/env python3
"""
Test runner for MCP tools.
This script runs all tests for the MCP tools project.
"""

import os
import sys
import argparse
import subprocess
import time

def run_test(test_script, verbose=False):
    """Run a test script and return the result."""
    start_time = time.time()

    # Build the command to run the test
    cmd = ["python3", test_script]

    # Run the test
    print(f"Running {os.path.basename(test_script)}...")
    if verbose:
        # Run with output visible
        result = subprocess.run(cmd)
        success = result.returncode == 0
    else:
        # Run with output captured
        result = subprocess.run(cmd, capture_output=True, text=True)
        success = result.returncode == 0
        if not success:
            print(f"Test failed. Output:")
            print(result.stdout)
            print(result.stderr)

    elapsed = time.time() - start_time

    if success:
        print(f"✅ {os.path.basename(test_script)} PASSED ({elapsed:.2f}s)")
    else:
        print(f"❌ {os.path.basename(test_script)} FAILED ({elapsed:.2f}s)")

    return success

def run_all_tests(tests_dir, verbose=False):
    """Run all test scripts in the tests directory."""
    # Find all test scripts
    test_scripts = []
    for file in os.listdir(tests_dir):
        if file.startswith("test_") and file.endswith(".py") and file != "test_idf_builder.py":
            test_scripts.append(os.path.join(tests_dir, file))

    test_scripts.sort()  # Run tests in alphabetical order

    # Print the test plan
    print(f"Found {len(test_scripts)} test scripts:")
    for script in test_scripts:
        print(f"  - {os.path.basename(script)}")
    print("")

    # Run each test
    results = []
    for script in test_scripts:
        success = run_test(script, verbose)
        results.append((os.path.basename(script), success))

    # Print summary
    print("\n=== Test Summary ===")
    passed = sum(1 for _, success in results if success)
    print(f"Passed: {passed}/{len(results)}")

    if passed < len(results):
        print("\nFailed tests:")
        for script, success in results:
            if not success:
                print(f"  - {script}")

    return passed == len(results)

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Run MCP tools tests.")
    parser.add_argument(
        "--test",
        help="Run a specific test script (without the .py extension)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show test output"
    )

    args = parser.parse_args()

    # Get the tests directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tests_dir = current_dir

    if args.test:
        # Run a specific test
        test_script = os.path.join(tests_dir, f"{args.test}.py")
        if not os.path.exists(test_script):
            print(f"Error: Test script not found: {test_script}")
            return 1

        success = run_test(test_script, args.verbose)
        return 0 if success else 1
    else:
        # Run all tests
        success = run_all_tests(tests_dir, args.verbose)
        return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
