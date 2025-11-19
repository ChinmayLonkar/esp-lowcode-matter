#!/usr/bin/env python3
"""
Test Framework for ESP32 Device Testing.

This module provides test execution classes and data structures for automated
ESP32 device testing scenarios.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Any, Optional

# Import device manager components
try:
    from .device_manager import DeviceRole, Device
except ImportError:
    from device_manager import DeviceRole, Device

logger = logging.getLogger(__name__)


class TestType(Enum):
    """Types of tests that can be executed."""
    LOG = "log"         # test if a particular log appears on the DUT/Tester (Action: check)
    GPIO = "gpio"       # test to set/get GPIO state on the DUT (Action: check, action)
    UART = "uart"       # test to send/receive UART messages on the DUT (Action: action)
    I2C_SLAVE = "i2c_slave"  # I2C slave monitor commands (Action: command)
    PWM = "pwm"         # test to set/get PWM signal on the DUT (Action: action)
    RESET = "reset"     # reset the DUT/Tester (Action: action)
    DELAY = "delay"     # delay for a particular amount of time (Action: action)
    FLASH = "flash"     # flash the DUT with a particular firmware (Action: action)


class TestAction(Enum):
    """Types of test actions."""
    WRITE = "write"
    READ = "read"
    COMMAND = "command"


@dataclass
class TestCase:
    """Represents a single test case."""
    type: TestType
    action: TestAction
    role: DeviceRole
    expected_value_int: Optional[int] = None
    expected_value_str: Optional[str] = None
    expected_value_float: Optional[float] = None
    expected_value_bool: Optional[bool] = None
    actual_value_int: Optional[int] = None
    actual_value_str: Optional[str] = None
    actual_value_float: Optional[float] = None
    actual_value_bool: Optional[bool] = None
    test_case_data: Optional[Dict[str, Any]] = None
    timeout: float = 10.0
    description: Optional[str] = None


@dataclass
class TestResult:
    """Result of a test execution."""
    test_case: TestCase
    success: bool
    message: str
    execution_time: float
    captured_data: Optional[str] = None


class TestExecutor:
    """Executes test cases on connected devices."""

    def __init__(self, dut: Optional[Device] = None, tester: Optional[Device] = None):
        """Initialize test executor with device references."""
        self.dut = dut
        self.tester = tester

    def set_devices(self, dut: Optional[Device] = None, tester: Optional[Device] = None):
        """Update device references."""
        if dut is not None:
            self.dut = dut
        if tester is not None:
            self.tester = tester

    async def execute_test_case(self, test_case: TestCase) -> TestResult:
        """Execute a single test case and return the result."""
        start_time = time.time()
        logger.info(f"Executing test case: {test_case.type.value} - {test_case.description}")

        try:
            if test_case.type == TestType.LOG:
                return await self._execute_log_test(test_case, start_time)
            elif test_case.type == TestType.RESET:
                return await self._execute_reset_test(test_case, start_time)
            elif test_case.type == TestType.DELAY:
                return await self._execute_delay_test(test_case, start_time)
            elif test_case.type == TestType.FLASH:
                return await self._execute_flash_test(test_case, start_time)
            else:
                execution_time = time.time() - start_time
                return TestResult(
                    test_case=test_case,
                    success=False,
                    message=f"Test type {test_case.type.value} not implemented",
                    execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Test execution failed: {e}")
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"Test execution failed: {str(e)}",
                execution_time=execution_time
            )

    async def _execute_log_test(self, test_case: TestCase, start_time: float) -> TestResult:
        """Execute a LOG-based test."""
        if test_case.role == DeviceRole.DUT:
            dut = self.dut
        else:
            dut = self.tester

        if not dut or not dut.serial_monitor:
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"No {test_case.role.value} device connected",
                execution_time=execution_time
            )

        try:
            # Search for the expected pattern in the logs
            pattern = test_case.expected_value_str
            if not pattern:
                execution_time = time.time() - start_time
                return TestResult(
                    test_case=test_case,
                    success=False,
                    message="No search pattern specified",
                    execution_time=execution_time
                )

            # Use the device's async search functionality (proper async wrapper for wait_for_pattern)
            search_result = await dut.serial_monitor.wait_for_pattern_async(
                pattern=pattern,
                timeout=test_case.timeout,
                since_timestamp=start_time
            )

            execution_time = time.time() - start_time

            if search_result["found"]:
                # Get recent data for context
                recent_data = dut.serial_monitor.get_recent_data(seconds=5)
                
                return TestResult(
                    test_case=test_case,
                    success=True,
                    message=f"Pattern '{pattern}' found in logs",
                    execution_time=execution_time,
                    captured_data="\n".join(recent_data[-10:])  # Last 10 lines
                )
            else:
                return TestResult(
                    test_case=test_case,
                    success=False,
                    message=f"Pattern '{pattern}' not found within {test_case.timeout}s",
                    execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"Log test failed: {str(e)}",
                execution_time=execution_time
            )

    async def _execute_reset_test(self, test_case: TestCase, start_time: float) -> TestResult:
        """Execute a RESET-based test."""
        if test_case.role == DeviceRole.DUT:
            dut = self.dut
        else:
            dut = self.tester
        try:
            # Record the timestamp before reset for future searches
            reset_timestamp = time.time()

            # Reset the ESP32 (this also clears the log buffer)
            reset_success = await dut.serial_monitor.reset_esp32_async()

            if reset_success:
                # If additional wait time is specified, use it; otherwise use default
                if test_case.expected_value_str:
                    try:
                        wait_time = float(test_case.expected_value_str)
                        await asyncio.sleep(wait_time)
                    except ValueError:
                        # If it's not a number, wait default time
                        await asyncio.sleep(2.0)
                else:
                    # Default wait time for reset to complete
                    await asyncio.sleep(2.0)

                execution_time = time.time() - start_time
                return TestResult(
                    test_case=test_case,
                    success=True,
                    message=f"Device reset completed successfully",
                    execution_time=execution_time
                )
            else:
                execution_time = time.time() - start_time
                return TestResult(
                    test_case=test_case,
                    success=False,
                    message="Device reset failed",
                    execution_time=execution_time
                )

        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"Reset test failed: {str(e)}",
                execution_time=execution_time
            )

    async def _execute_delay_test(self, test_case: TestCase, start_time: float) -> TestResult:
        """Execute a DELAY-based test."""
        try:
            delay_seconds = test_case.expected_value_float or test_case.expected_value_int or 1.0
            
            logger.info(f"Executing delay of {delay_seconds} seconds")
            await asyncio.sleep(delay_seconds)
            
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=True,
                message=f"Delay of {delay_seconds} seconds completed",
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"Delay test failed: {str(e)}",
                execution_time=execution_time
            )

    async def _execute_flash_test(self, test_case: TestCase, start_time: float) -> TestResult:
        """Execute a FLASH-based test."""
        try:
            # This would need to import and call the flash_firmware function
            # For now, return a placeholder result
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message="Flash test not yet implemented in test framework",
                execution_time=execution_time
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                test_case=test_case,
                success=False,
                message=f"Flash test failed: {str(e)}",
                execution_time=execution_time
            )

    async def execute_test_sequence(self, test_cases: List[TestCase]) -> List[TestResult]:
        """Execute a sequence of test cases and return all results."""
        results = []
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"Executing test {i+1}/{len(test_cases)}: {test_case.description or test_case.type.value}")
            
            result = await self.execute_test_case(test_case)
            results.append(result)
            
            # Log result
            status = "✅ PASS" if result.success else "❌ FAIL"
            logger.info(f"Test {i+1} {status}: {result.message} (took {result.execution_time:.2f}s)")
            
            # Stop on failure if needed (could be configurable)
            if not result.success:
                logger.warning(f"Test {i+1} failed, continuing with remaining tests...")
        
        return results
