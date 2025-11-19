#!/usr/bin/env python3
"""
Test script for MCP base components.
This script verifies that all base components are working correctly.
"""

import os
import sys
import asyncio
import tempfile
import time

# Add the parent directory to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import path setup and set up the paths
from mcp_tools.components.path_setup import setup_path, get_root_dir
setup_path()

# Import other components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat
from mcp_tools.components.network import ApiClient, NetworkError
from mcp_tools.components.async_utils import (
    TaskManager, AsyncRetry, AsyncCache, async_to_sync,
    is_async_callable, gather_with_concurrency
)

async def test_database():
    """Test the database component."""
    print("\n--- Testing Database ---")

    # Create a temporary database
    with tempfile.NamedTemporaryFile(suffix=".db") as temp_db:
        db_path = temp_db.name

    # Initialize the database
    db = ToolDatabase(db_path)

    # Test storing and retrieving data
    test_key = "test_key"
    test_value = {"name": "Test", "value": 123}
    test_tool = "test_tool"

    db.store_data(test_key, test_value, test_tool)
    retrieved_value = db.get_data(test_key, test_tool)

    print(f"Stored value: {test_value}")
    print(f"Retrieved value: {retrieved_value}")

    assert retrieved_value == test_value, "Retrieved value does not match stored value"

    # Test recording tool calls
    db.record_tool_call(
        tool_name="test_tool",
        parameters={"param1": "value1"},
        result={"success": True},
        status="success"
    )

    history = db.get_tool_history("test_tool", 1)
    print(f"Tool call history: {history}")

    assert len(history) == 1, "Expected 1 tool call in history"
    assert history[0]["tool_name"] == "test_tool", "Tool name does not match"

    # Clean up
    db.close()
    try:
        os.remove(db_path)
    except:
        pass

    print("Database test: PASSED")

def test_output():
    """Test the output formatting component."""
    print("\n--- Testing Output ---")

    # Test output formats
    for format_name in ["text", "json", "csv", "table"]:
        output = get_output_manager(format=format_name, color=False)
        print(f"\nTesting {format_name.upper()} format:")

        # Test basic output
        output.print(f"This is {format_name} output")

        # Test data output
        test_data = [
            {"id": 1, "name": "Item 1", "value": 100},
            {"id": 2, "name": "Item 2", "value": 200}
        ]
        output.output(test_data)

        # Test status messages
        output.info("Info message")
        output.success("Success message")
        output.warning("Warning message")
        output.error("Error message")

    print("Output test: PASSED")

async def test_network():
    """Test the network component."""
    print("\n--- Testing Network ---")

    # Create a mock server response for testing
    # In a real scenario, we would connect to a real server

    try:
        # Create a client
        async with ApiClient(base_url="https://httpbin.org") as client:
            # Test GET request
            response = await client.get("/get")
            print(f"GET response: {response}")

            # Test POST request
            post_data = {"name": "Test", "value": 123}
            response = await client.post("/post", json_data=post_data)
            print(f"POST response contains data: {'json' in response}")

    except NetworkError as e:
        print(f"Network error: {e}")
        # If we're offline, this is expected
        print("Network test: SKIPPED (network connection issue)")
        return

    print("Network test: PASSED")

async def test_async_utils():
    """Test the async utilities."""
    print("\n--- Testing Async Utilities ---")

    # Test TaskManager
    print("\nTesting TaskManager:")
    task_manager = TaskManager(max_concurrent=5)

    async def sample_task(name, duration, should_fail=False):
        """Sample task for testing."""
        await asyncio.sleep(duration)
        if should_fail:
            raise ValueError(f"Task {name} failed intentionally")
        return f"Result from {name}"

    # Run multiple tasks
    print("Running multiple tasks...")
    task1 = asyncio.create_task(task_manager.run("task1", sample_task("task1", 0.2)))
    task2 = asyncio.create_task(task_manager.run("task2", sample_task("task2", 0.5)))

    # Wait for tasks to complete
    results = await asyncio.gather(task1, task2, return_exceptions=True)
    print(f"Task results: {results}")
    assert "Result from task1" in results, "Task1 result not found"
    assert "Result from task2" in results, "Task2 result not found"

    # Test direct task execution
    print("Testing direct task execution...")
    result3 = await task_manager.run("task3", sample_task("task3", 0.3))
    print(f"Task3 result: {result3}")
    assert result3 == "Result from task3", "Task3 result is incorrect"

    # Test task cancellation - create a long-running task
    print("Testing task cancellation...")
    # Run a long task that we'll cancel
    cancel_task = asyncio.create_task(task_manager.run("task4", sample_task("task4", 2.0)))

    # Give the task a moment to start
    await asyncio.sleep(0.3)

    # Verify it was registered and cancel it
    cancelled = task_manager.cancel_task("task4")
    print(f"Task4 cancelled: {cancelled}")

    # Try to await the cancelled task - should raise an exception
    try:
        await cancel_task
        print("Task was not cancelled properly")
    except asyncio.CancelledError:
        print("Task was cancelled successfully")

    # Test task failure
    print("Testing task failure...")
    try:
        await task_manager.run("task_fail", sample_task("task_fail", 0.1, should_fail=True))
        assert False, "Task should have failed"
    except ValueError as e:
        print(f"Task failed as expected: {e}")

    # Test AsyncRetry decorator
    print("\nTesting AsyncRetry decorator:")

    retry_count = 0

    @AsyncRetry(max_retries=2, retry_delay=0.1)
    async def retry_function(should_succeed_on_retry=False):
        """Function that fails but should be retried."""
        nonlocal retry_count
        retry_count += 1
        print(f"Retry attempt: {retry_count}")
        if retry_count < 2 or not should_succeed_on_retry:
            raise ValueError("Temporary error")
        return "Success after retry"

    # Reset retry count
    retry_count = 0

    # Test successful retry
    print("Testing successful retry:")
    try:
        result = await retry_function(should_succeed_on_retry=True)
        print(f"Retry succeeded after {retry_count} attempts with result: {result}")
        assert result == "Success after retry", "Unexpected result from retry"
        assert retry_count == 2, f"Expected 2 retries, got {retry_count}"
    except ValueError:
        assert False, "Retry should have succeeded"

    # Reset retry count
    retry_count = 0

    # Test failed retry
    print("Testing failed retry:")
    try:
        await retry_function(should_succeed_on_retry=False)
        assert False, "Retry should have failed"
    except ValueError as e:
        print(f"Retry failed after {retry_count} attempts as expected: {e}")
        assert retry_count == 3, f"Expected 3 retries, got {retry_count}"

    # Test AsyncCache decorator
    print("\nTesting AsyncCache decorator:")

    call_count = 0

    @AsyncCache(ttl=1)
    async def cached_function(param):
        """Function whose results are cached."""
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return f"Result for {param} (call {call_count})"

    # Test cache hit
    print("Testing cache hits and misses:")
    result1 = await cached_function("test")
    print(f"First call: {result1}")

    result2 = await cached_function("test")
    print(f"Second call (should be cached): {result2}")

    assert result1 == result2, "Cached results should match"
    assert call_count == 1, f"Expected 1 actual call, got {call_count}"

    # Test different parameter
    result3 = await cached_function("different")
    print(f"Call with different param: {result3}")
    assert call_count == 2, f"Expected 2 actual calls, got {call_count}"

    # Test cache expiration
    print("Testing cache expiration:")
    print("Waiting for cache to expire...")
    await asyncio.sleep(1.1)  # Wait for cache to expire

    result4 = await cached_function("test")
    print(f"Call after expiration: {result4}")
    assert call_count == 3, f"Expected 3 actual calls, got {call_count}"

    # Test is_async_callable
    print("\nTesting is_async_callable:")

    async def async_func():
        pass

    def sync_func():
        pass

    print(f"async_func is async: {is_async_callable(async_func)}")
    print(f"sync_func is async: {is_async_callable(sync_func)}")
    assert is_async_callable(async_func), "async_func should be identified as async"
    assert not is_async_callable(sync_func), "sync_func should not be identified as async"

    # Test gather_with_concurrency
    print("\nTesting gather_with_concurrency:")

    async def delay_task(delay, value):
        await asyncio.sleep(delay)
        return value

    # Create tasks with different delays
    tasks = [
        delay_task(0.3, "task1"),
        delay_task(0.1, "task2"),
        delay_task(0.2, "task3"),
    ]

    # Run with concurrency limit
    print("Running tasks with concurrency limit...")
    start_time = time.time()
    results = await gather_with_concurrency(2, *tasks)
    elapsed = time.time() - start_time

    print(f"Results: {results}")
    print(f"Elapsed time: {elapsed:.2f}s")

    # Verify results
    assert results == ["task1", "task2", "task3"], f"Expected ordered results, got {results}"

    print("Async utils test: PASSED")

def test_async_to_sync():
    """Test the async_to_sync decorator separately."""
    print("\n--- Testing async_to_sync ---")

    @async_to_sync
    async def async_add(a, b):
        """Asynchronous function to be converted to sync."""
        await asyncio.sleep(0.1)
        return a + b

    # Call the function synchronously
    result = async_add(5, 3)
    print(f"Result of sync call to async function: {result}")
    assert result == 8, f"Expected 8, got {result}"
    print("async_to_sync test: PASSED")

async def main():
    """Run all tests."""
    print("=== Testing MCP Base Components ===")

    # Test path setup
    print("\n--- Testing Path Setup ---")
    root_dir = get_root_dir()
    print(f"Root directory: {root_dir}")
    assert os.path.exists(root_dir), "Root directory does not exist"
    print("Path setup test: PASSED")

    # Test other components
    await test_database()
    test_output()
    await test_network()
    await test_async_utils()

    print("\n=== All tests completed successfully ===")

if __name__ == "__main__":
    # Run the main async tests
    asyncio.run(main())

    # Test async_to_sync separately after the main tests
    test_async_to_sync()

    print("\n=== ALL TESTS COMPLETED SUCCESSFULLY ===")
