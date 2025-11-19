#!/usr/bin/env python3
"""
Asynchronous utilities for MCP tools.
Provides helpers for managing asynchronous tasks and operations.
"""

import asyncio
import logging
import time
import functools
import inspect
from typing import Dict, List, Any, Optional, Union, Callable, Awaitable, TypeVar, Generic, Tuple

logger = logging.getLogger(__name__)

T = TypeVar('T')

class TaskManager:
    """
    Manager for asynchronous tasks.

    Allows tracking, cancellation, and monitoring of async tasks.
    """

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize the task manager.

        Args:
            max_concurrent: Maximum number of concurrent tasks
        """
        self.tasks: Dict[str, asyncio.Task] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.results: Dict[str, Any] = {}
        self.errors: Dict[str, Exception] = {}

    async def run(self, name: str, coro: Awaitable[T], timeout: Optional[float] = None) -> T:
        """
        Run a coroutine as a tracked task.

        Args:
            name: Unique name for the task
            coro: Coroutine to run
            timeout: Timeout in seconds (None for no timeout)

        Returns:
            Result of the coroutine

        Raises:
            asyncio.TimeoutError: If the task times out
            Exception: Any exception raised by the task
        """
        if name in self.tasks and not self.tasks[name].done():
            logger.warning(f"Task {name} is already running")
            return await self.wait_for_task(name, timeout)

        async with self.semaphore:
            start_time = time.time()
            logger.debug(f"Starting task {name}")

            # Create and store the task
            if timeout is not None:
                task = asyncio.create_task(asyncio.wait_for(coro, timeout))
            else:
                task = asyncio.create_task(coro)

            self.tasks[name] = task

            try:
                result = await task
                elapsed = time.time() - start_time
                logger.debug(f"Task {name} completed in {elapsed:.2f}s")
                self.results[name] = result
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"Task {name} failed after {elapsed:.2f}s: {str(e)}")
                self.errors[name] = e
                raise

    async def wait_for_task(self, name: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for a specific task to complete.

        Args:
            name: Name of the task
            timeout: Timeout in seconds (None for no timeout)

        Returns:
            Result of the task

        Raises:
            KeyError: If the task doesn't exist
            asyncio.TimeoutError: If waiting times out
            Exception: Any exception raised by the task
        """
        if name not in self.tasks:
            raise KeyError(f"Task {name} not found")

        task = self.tasks[name]
        if task.done():
            # Task already completed
            if task.exception() is not None:
                raise task.exception()
            return task.result()

        # Wait for the task to complete
        if timeout is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout)
        else:
            await task

        if task.exception() is not None:
            raise task.exception()
        return task.result()

    def cancel_task(self, name: str) -> bool:
        """
        Cancel a running task.

        Args:
            name: Name of the task

        Returns:
            True if the task was canceled, False if it doesn't exist or is already done
        """
        if name in self.tasks and not self.tasks[name].done():
            logger.info(f"Cancelling task {name}")
            self.tasks[name].cancel()
            return True
        return False

    def cancel_all_tasks(self) -> int:
        """
        Cancel all running tasks.

        Returns:
            Number of tasks canceled
        """
        count = 0
        for name, task in list(self.tasks.items()):
            if not task.done():
                logger.info(f"Cancelling task {name}")
                task.cancel()
                count += 1
        return count

    def get_running_tasks(self) -> List[str]:
        """
        Get names of all running tasks.

        Returns:
            List of task names
        """
        return [name for name, task in self.tasks.items() if not task.done()]

    def get_task_status(self, name: str) -> Dict[str, Any]:
        """
        Get status information for a task.

        Args:
            name: Name of the task

        Returns:
            Dictionary with task status information

        Raises:
            KeyError: If the task doesn't exist
        """
        if name not in self.tasks:
            raise KeyError(f"Task {name} not found")

        task = self.tasks[name]
        status = {
            "name": name,
            "state": "completed" if task.done() else "running",
            "cancelled": task.cancelled(),
        }

        if task.done():
            if task.cancelled():
                status["result"] = None
                status["error"] = "Task was cancelled"
            elif task.exception() is not None:
                status["result"] = None
                status["error"] = str(task.exception())
                status["exception"] = task.exception().__class__.__name__
            else:
                status["result"] = task.result()
                status["error"] = None

        return status


class AsyncRetry:
    """
    Decorator for retrying async functions with exponential backoff.
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        retry_on_exceptions: Tuple[type, ...] = (Exception,),
        retry_if: Optional[Callable[[Exception], bool]] = None
    ):
        """
        Initialize retry decorator.

        Args:
            max_retries: Maximum number of retries
            retry_delay: Initial delay between retries in seconds
            backoff_factor: Multiplicative factor for retry delay
            retry_on_exceptions: Exception types to retry on
            retry_if: Optional function to determine if an exception should trigger retry
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.retry_on_exceptions = retry_on_exceptions
        self.retry_if = retry_if

    def __call__(self, func):
        """Apply the decorator to an async function."""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            delay = self.retry_delay

            while True:
                try:
                    return await func(*args, **kwargs)
                except self.retry_on_exceptions as e:
                    retries += 1

                    # Check if we should retry based on custom function
                    if self.retry_if and not self.retry_if(e):
                        logger.debug(f"Not retrying due to retry_if function: {str(e)}")
                        raise

                    # Check if we've exceeded max retries
                    if retries > self.max_retries:
                        logger.warning(f"Max retries ({self.max_retries}) exceeded: {str(e)}")
                        raise

                    # Calculate delay with exponential backoff
                    wait_time = delay * (self.backoff_factor ** (retries - 1))
                    logger.info(f"Retry {retries}/{self.max_retries} after {wait_time:.2f}s: {str(e)}")

                    # Wait before retrying
                    await asyncio.sleep(wait_time)

        return wrapper


class AsyncCache:
    """
    Simple async function result cache with TTL.
    """

    def __init__(self, ttl: int = 300):
        """
        Initialize the cache.

        Args:
            ttl: Time-to-live for cache entries in seconds
        """
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl

    def __call__(self, func):
        """Apply the cache decorator to an async function."""
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend([str(arg) for arg in args])
            key_parts.extend([f"{k}={v}" for k, v in sorted(kwargs.items())])
            key = ":".join(key_parts)

            # Check if result is in cache and not expired
            if key in self.cache:
                entry = self.cache[key]
                now = time.time()
                if now - entry["time"] < self.ttl:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return entry["result"]

            # Call the function and cache the result
            result = await func(*args, **kwargs)
            self.cache[key] = {
                "result": result,
                "time": time.time()
            }
            logger.debug(f"Cache miss for {func.__name__}, stored result")
            return result

        return wrapper


def async_to_sync(func):
    """
    Decorator to convert an async function to a sync function.

    This runs the function in the current event loop if it's running,
    or creates a new event loop if needed.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an event loop, create a task and use threading
                # to wait for its result, which avoids nested event loops
                current_task = asyncio.current_task()
                if current_task is not None:
                    # We're in a coroutine context, directly await the function
                    logger.warning(
                        "async_to_sync called from within a coroutine. "
                        "Consider using the async function directly."
                    )
                    # Return a coroutine that can be awaited by the caller
                    return func(*args, **kwargs)

                # We're in an event loop but not in a coroutine context
                # Use run_in_executor to avoid blocking the event loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = loop.run_in_executor(
                        executor,
                        lambda: asyncio.run(func(*args, **kwargs))
                    )
                    return future.result()
            else:
                # No event loop is running, create one
                return asyncio.run(func(*args, **kwargs))
        except RuntimeError as e:
            # If we can't get an event loop, create a new one
            if "There is no current event loop in thread" in str(e):
                return asyncio.run(func(*args, **kwargs))
            raise

    return wrapper


def is_async_callable(obj: Any) -> bool:
    """
    Check if an object is an async callable.

    Args:
        obj: Object to check

    Returns:
        True if the object is an async callable, False otherwise
    """
    if not callable(obj):
        return False

    # Check if it's a coroutine function
    if inspect.iscoroutinefunction(obj):
        return True

    # Check if it's an async method
    if inspect.ismethod(obj) and inspect.iscoroutinefunction(obj.__func__):
        return True

    # Check if it has __await__ method (awaitable)
    if hasattr(obj, "__await__"):
        return True

    return False


async def gather_with_concurrency(n: int, *tasks):
    """
    Run tasks concurrently but limit the number of tasks running at once.

    Args:
        n: Maximum number of concurrent tasks
        *tasks: Tasks to run

    Returns:
        List of task results in the same order as tasks
    """
    semaphore = asyncio.Semaphore(n)

    async def semaphore_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(*(semaphore_task(task) for task in tasks))
