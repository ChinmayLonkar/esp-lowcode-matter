#!/usr/bin/env python3
"""
Device Manager for ESP32 Device Test Server.

This module provides thread-safe device state management, SerialMonitor, and Device
classes for ESP32 testing operations.
"""

import asyncio
import os
import sys
import subprocess
import threading
import logging
import time
import re
from typing import Dict, Optional, List, Any
from enum import Enum
from dataclasses import dataclass

# Try to import pyserial
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("Warning: pyserial not available. Serial monitoring will not work.")

logger = logging.getLogger(__name__)


def get_baud_rate_for_chip(chip_type: str) -> int:
    """Get appropriate baud rate based on ESP32 chip type.

    Args:
        chip_type: The chip type string (e.g., "ESP32-C2", "esp32c2", etc.)

    Returns:
        Appropriate baud rate (74800 for ESP32-C2, 115200 for others)
    """
    if chip_type and "c2" in chip_type.lower():
        return 74800
    return 115200


def detect_chip_via_esptool(port: str) -> Optional[str]:
    """Detect ESP32 chip type using esptool.py on a specific port.

    Args:
        port: Serial port to check

    Returns:
        Chip type string if detected, None otherwise
    """
    try:
        # Try using esptool.py to detect chip
        cmd = ["esptool.py", "--port", port, "chip_id"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            # Parse the chip information from output
            for line in result.stdout.splitlines():
                if "Chip is" in line:
                    chip_type = line.split("Chip is")[1].strip()
                    logger.info(f"Detected chip type on {port}: {chip_type}")
                    return chip_type

        # Try with IDF_PATH if direct call failed
        idf_path = os.environ.get("IDF_PATH")
        if idf_path and result.returncode != 0:
            esptool_path = os.path.join(idf_path, "components", "esptool_py", "esptool", "esptool.py")
            if os.path.exists(esptool_path):
                cmd = ["python", esptool_path, "--port", port, "chip_id"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if "Chip is" in line:
                            chip_type = line.split("Chip is")[1].strip()
                            logger.info(f"Detected chip type on {port}: {chip_type}")
                            return chip_type

    except Exception as e:
        logger.debug(f"Failed to detect chip on {port}: {e}")

    return None


class DeviceRole(Enum):
    """Role of the device in the test."""
    DUT = "dut"
    PROBE = "probe"


class SerialMonitor:
    """Serial monitor for ESP32 devices with continuous logging."""

    def __init__(self, port: str, baudrate: int = 115200, log_file_prefix: str = None):
        if not SERIAL_AVAILABLE:
            raise RuntimeError("pyserial is not available. Please install it with: pip install pyserial")

        self.port = port
        self.baudrate = baudrate
        self.serial_connection = None
        self.is_monitoring = False
        self.monitor_thread = None
        self.received_data = []
        self.data_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.bytes_received = 0

        # Log file setup
        self.log_file_prefix = log_file_prefix
        self.log_file_handle = None
        self._setup_log_file()
        self.lines_received = 0
        self.line_buffer = ""  # Buffer for incomplete lines
        self.connection_time = None  # Track when connection was established

    def _setup_log_file(self):
        """Set up log file for capturing device output."""
        # Check if device logging is enabled via environment variable
        device_log_enabled = os.environ.get("DEVICE_LOG_ENABLED", "true").lower() == "true"

        if self.log_file_prefix and device_log_enabled:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Create a safe filename from port name
            safe_port = self.port.replace('/', '_').replace('\\', '_').replace(':', '_')

            # Use custom log directory if specified, otherwise use logs folder
            log_dir = os.environ.get("DEVICE_LOG_DIR", "logs")
            log_filename = os.path.join(log_dir, f"{self.log_file_prefix}_{safe_port}_{timestamp}.log")

            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(log_filename), exist_ok=True)
                self.log_file_handle = open(log_filename, 'w', encoding='utf-8')
                logger.info(f"Device log file created: {log_filename}")
            except Exception as e:
                logger.error(f"Failed to create log file {log_filename}: {e}")
                self.log_file_handle = None

    def _close_log_file(self):
        """Close the log file if open."""
        if self.log_file_handle:
            try:
                self.log_file_handle.close()
                logger.info(f"Device log file closed")
            except Exception as e:
                logger.error(f"Error closing log file: {e}")
            finally:
                self.log_file_handle = None

    def _write_to_log_file(self, line: str, timestamp: float):
        """Write a line to the log file with timestamp."""
        if self.log_file_handle:
            try:
                import datetime
                dt = datetime.datetime.fromtimestamp(timestamp)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # millisecond precision
                self.log_file_handle.write(f"[{timestamp_str}] {line}\n")
                self.log_file_handle.flush()  # Ensure data is written immediately
            except Exception as e:
                logger.error(f"Error writing to log file: {e}")

    def connect(self) -> bool:
        """Connect to the serial port and immediately start continuous monitoring."""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            # Clear any existing data in buffers
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()

            logger.info(f"Connected to {self.port} at {self.baudrate} baud")
            logger.info(f"Serial settings: {self.serial_connection.get_settings()}")

            # Record connection time
            self.connection_time = time.time()

            # Validate the connection immediately
            if not self._validate_connection():
                logger.error(f"Serial connection validation failed for {self.port}")
                return False

            # Immediately start continuous monitoring
            self._start_continuous_monitoring()

            return True
        except Exception as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            return False

    def _validate_connection(self):
        """Validate that the serial connection is healthy."""
        try:
            if not self.serial_connection or not self.serial_connection.is_open:
                return False

            # Try to access in_waiting to check if the file descriptor is valid
            _ = self.serial_connection.in_waiting
            return True
        except (TypeError, OSError, AttributeError) as e:
            logger.error(f"Serial connection validation failed: {e}")
            return False

    def _start_continuous_monitoring(self):
        """Start continuous monitoring immediately upon connection."""
        if self.is_monitoring:
            return

        # Initialize monitoring state
        self.bytes_received = 0
        self.lines_received = 0
        self.line_buffer = ""

        # Clear any old data and start fresh
        with self.data_lock:
            self.received_data.clear()

        self.is_monitoring = True
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, name="SerialMonitor")
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        # Wait a moment to ensure the thread actually starts
        time.sleep(0.1)  # This is acceptable in thread startup
        logger.info("Started continuous serial monitoring")

    def reset_esp32(self) -> bool:
        """Reset ESP32 device while maintaining continuous log capture."""
        if not self.serial_connection or not self.serial_connection.is_open:
            logger.error("Cannot reset: Serial connection not established")
            return False

        try:
            logger.info("Resetting ESP32 device (keeping log buffer for continuous capture)...")

            # ESP32 reset sequence using DTR and RTS lines
            # Set DTR and RTS to initial state
            self.serial_connection.dtr = False
            self.serial_connection.rts = False
            time.sleep(0.1)

            # Pull DTR low (reset) and RTS high (GPIO0 high for normal boot)
            self.serial_connection.dtr = True  # Reset line active
            self.serial_connection.rts = False # GPIO0 high (normal boot)
            time.sleep(0.1)

            # Release reset
            self.serial_connection.dtr = False
            time.sleep(0.1)

            # Clear hardware buffers to ensure clean data flow
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()

            # DO NOT clear our software buffer - keep continuous logging!
            # This ensures we capture all boot messages from the moment of reset
            logger.info("ESP32 reset sequence completed, continuous logging maintained")
            return True

        except Exception as e:
            logger.error(f"Failed to reset ESP32: {e}")
            return False

    def disconnect(self):
        """Disconnect from the serial port and stop monitoring."""
        self.stop_monitoring()
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            logger.info(f"Disconnected from {self.port}")

        # Close log file when disconnecting
        self._close_log_file()

    def stop_monitoring(self):
        """Stop monitoring serial data with proper thread cleanup."""
        if self.is_monitoring:
            self.is_monitoring = False
            self.stop_event.set()
            
            if self.monitor_thread:
                # Wait for thread to stop gracefully
                self.monitor_thread.join(timeout=2)
                
                # Check if thread actually stopped
                if self.monitor_thread.is_alive():
                    logger.warning(f"Monitor thread for {self.port} did not stop cleanly within timeout")
                    # Give it one more chance with a shorter timeout
                    self.monitor_thread.join(timeout=1)
                    
                    if self.monitor_thread.is_alive():
                        logger.error(f"Monitor thread for {self.port} is stuck - may cause resource leak")
                
                # Clear thread reference regardless of whether it stopped
                self.monitor_thread = None
            
            logger.info(f"Stopped serial monitoring on {self.port}. Received {self.lines_received} lines, {self.bytes_received} bytes total")

    async def stop_monitoring_async(self):
        """Async wrapper for stop_monitoring to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.stop_monitoring)

    async def connect_async(self) -> bool:
        """Async wrapper for connect to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connect)

    async def reset_esp32_async(self) -> bool:
        """Async wrapper for reset_esp32 to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.reset_esp32)

    def _monitor_loop(self):
        """Main monitoring loop running in separate thread - continuous logging."""
        logger.info("Continuous serial monitor loop started")
        consecutive_empty_reads = 0
        max_buffer_size = 100000  # Increase buffer size to avoid losing data
        loop_count = 0

        while self.is_monitoring and not self.stop_event.is_set():
            try:
                loop_count += 1

                # Check if data is available
                try:
                    bytes_waiting = self.serial_connection.in_waiting
                except (TypeError, OSError, AttributeError) as e:
                    logger.error(f"Serial connection error in monitoring loop: {e}")
                    logger.error(f"Serial connection state: is_open={getattr(self.serial_connection, 'is_open', 'unknown')}")
                    self.is_monitoring = False
                    break

                # Process data when available
                if bytes_waiting > 0:
                    logger.debug(f"Data available: {bytes_waiting} bytes waiting")
                    consecutive_empty_reads = 0

                    # Read available data
                    raw_data = self.serial_connection.read(bytes_waiting)
                    self.bytes_received += len(raw_data)
                    logger.debug(f"Read {len(raw_data)} bytes, total bytes: {self.bytes_received}")

                    # Decode and handle line buffering
                    try:
                        text_data = raw_data.decode('utf-8', errors='replace')
                        logger.debug(f"Decoded text: {repr(text_data)}")

                        # Add to line buffer
                        self.line_buffer += text_data

                        # Split on newlines and process complete lines
                        lines = self.line_buffer.split('\n')

                        # Keep the last part (might be incomplete) in buffer
                        self.line_buffer = lines[-1]

                        # Process all complete lines (all except the last one)
                        for line in lines[:-1]:
                            line = line.strip()
                            if line:  # Only store non-empty lines
                                logger.debug(f"Processing complete line: {repr(line)}")
                                timestamp = time.time()
                                with self.data_lock:
                                    self.received_data.append({
                                        'timestamp': timestamp,
                                        'data': line
                                    })

                                # Write to log file if enabled
                                self._write_to_log_file(line, timestamp)

                                # Limit buffer size to prevent memory issues
                                if len(self.received_data) > max_buffer_size:
                                    # Remove oldest 1000 entries when buffer is full
                                    self.received_data = self.received_data[100:]

                                self.lines_received += 1
                                logger.info(f"Stored line {self.lines_received}: {line}")

                    except UnicodeDecodeError as e:
                        logger.warning(f"Unicode decode error: {e}")
                        # Store raw bytes as hex for debugging
                        hex_data = raw_data.hex()
                        timestamp = time.time()
                        hex_line = f"[HEX] {hex_data}"
                        with self.data_lock:
                            self.received_data.append({
                                'timestamp': timestamp,
                                'data': hex_line
                            })

                        # Write to log file if enabled
                        self._write_to_log_file(hex_line, timestamp)
                else:
                    consecutive_empty_reads += 1
                    # Log every 10000 empty reads (about 50 seconds at 0.005s intervals)
                    if consecutive_empty_reads % 10000 == 0:
                        logger.debug(f"No data available, {consecutive_empty_reads} consecutive empty reads")
                    # Use stop_event.wait() with timeout for more responsive shutdown
                    if self.stop_event.wait(timeout=0.005):
                        break  # Stop event was set, exit loop immediately

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                break

        logger.info(f"Continuous serial monitor loop ended after {loop_count} iterations")

    def get_recent_data(self, seconds: int = 10) -> List[str]:
        """Get recent data from the last N seconds."""
        current_time = time.time()
        cutoff_time = current_time - seconds

        with self.data_lock:
            # Get all data within the time window
            recent_data = [
                entry['data'] for entry in self.received_data
                if entry['timestamp'] >= cutoff_time
            ]

            # If no recent data, return the last 20 lines regardless of time
            if not recent_data and self.received_data:
                recent_data = [entry['data'] for entry in self.received_data[-20:]]
                logger.info(f"No data in last {seconds}s, returning last 20 lines")

            logger.info(f"Returning {len(recent_data)} lines of recent data from last {seconds}s")
            return recent_data

    def get_all_data(self) -> List[str]:
        """Get all received data since connection/last reset."""
        with self.data_lock:
            all_data = [item['data'] for item in self.received_data]
        return all_data

    def get_data_since_timestamp(self, timestamp: float) -> List[str]:
        """Get all data received since a specific timestamp."""
        with self.data_lock:
            data_since = [
                entry['data'] for entry in self.received_data
                if entry['timestamp'] >= timestamp
            ]
        return data_since

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        with self.data_lock:
            total_lines = len(self.received_data)

        return {
            "is_monitoring": self.is_monitoring,
            "total_lines": total_lines,
            "bytes_received": self.bytes_received,
            "lines_received": self.lines_received,
            "port": self.port,
            "baudrate": self.baudrate,
            "line_buffer_length": len(self.line_buffer),
            "line_buffer_content": self.line_buffer[:100] + "..." if len(self.line_buffer) > 100 else self.line_buffer,
            "connection_time": self.connection_time,
            "monitoring_duration": time.time() - self.connection_time if self.connection_time else 0
        }

    def flush_line_buffer(self) -> Optional[str]:
        """Flush any remaining data in the line buffer as a complete line."""
        if self.line_buffer.strip():
            line = self.line_buffer.strip()
            timestamp = time.time()
            with self.data_lock:
                self.received_data.append({
                    'timestamp': timestamp,
                    'data': line
                })
            self.lines_received += 1
            self.line_buffer = ""

            # Write to log file if enabled
            self._write_to_log_file(line, timestamp)
            logger.info(f"Flushed partial line {self.lines_received}: {line}")
            return line
        return None

    def clear_data(self):
        """Clear all received data (useful when explicitly requested)."""
        with self.data_lock:
            self.received_data.clear()
        # Don't reset counters as they track total since connection
        # self.bytes_received = 0
        # self.lines_received = 0
        self.line_buffer = ""  # Clear any partial line data
        logger.info("Manually cleared received data buffer")

    def wait_for_pattern(self, pattern: str, timeout: float = 10.0, since_timestamp: Optional[float] = None) -> Optional[str]:
        """Wait for a specific pattern in the serial data using substring matching.

        Args:
            pattern: Pattern to search for (case-insensitive substring match)
            timeout: Maximum time to wait for the pattern
            since_timestamp: Only search data received after this timestamp (useful for reset scenarios)

        Returns:
            The matching line if found, None if timeout
        """
        start_time = time.time()
        pattern_lower = pattern.lower()
        search_start_timestamp = since_timestamp or start_time

        # Keep track of data we've already checked to avoid re-checking
        checked_lines = 0

        while time.time() - start_time < timeout:
            # Get all data (or data since timestamp)
            if since_timestamp:
                all_data = self.get_data_since_timestamp(since_timestamp)
            else:
                all_data = self.get_all_data()

            logger.debug(f"Checking {len(all_data)} lines for pattern")

            # Check new lines that we haven't checked yet
            for i in range(checked_lines, len(all_data)):
                line = all_data[i]
                if pattern_lower in line.lower():
                    logger.debug(f"Substring pattern '{pattern}' matched line: {line}")
                    return line

            # Update the count of lines we've checked
            checked_lines = len(all_data)

            # Short sleep to avoid busy waiting
            time.sleep(0.05)

        logger.debug(f"Pattern '{pattern}' not found within {timeout} seconds")
        return None

    async def wait_for_pattern_async(self, pattern: str, timeout: float = 10.0, since_timestamp: Optional[float] = None) -> Dict[str, Any]:
        """Async wrapper for wait_for_pattern to avoid blocking the event loop.
        
        Args:
            pattern: Pattern to search for
            timeout: Maximum time to wait for the pattern
            since_timestamp: Only search data received after this timestamp
            
        Returns:
            Dict with 'found' boolean and optional 'matched_line'
        """
        loop = asyncio.get_event_loop()
        
        # Run the blocking wait_for_pattern in a thread pool to avoid blocking the event loop
        matched_line = await loop.run_in_executor(None, self.wait_for_pattern, pattern, timeout, since_timestamp)
        
        if matched_line:
            return {
                "found": True,
                "matched_line": matched_line
            }
        else:
            return {
                "found": False,
                "matched_line": None
            }

    def send_command(self, command: str, wait_for_response: bool = True, timeout: float = 10.0) -> Dict[str, Any]:
        """Send a command to the device and optionally wait for response.

        Args:
            command: Command to send to the device
            wait_for_response: Whether to wait for a response after sending
            timeout: Maximum time to wait for response

        Returns:
            Dictionary with command result and response data
        """
        if not self.serial_connection or not self.serial_connection.is_open:
            return {
                "success": False,
                "error": "Serial connection not established",
                "command": command
            }

        try:
            # Record timestamp before sending command
            send_timestamp = time.time()

            # Send command (add newline if not present)
            command_to_send = command if command.endswith('\n') else command + '\n'

            # Add small delay before sending to ensure ESP32 is ready
            time.sleep(0.05)

            # Send command in chunks to avoid UART buffer overflow
            chunk_size = 32  # Send in 32-byte chunks
            command_bytes = command_to_send.encode('utf-8')

            for i in range(0, len(command_bytes), chunk_size):
                chunk = command_bytes[i:i + chunk_size]
                self.serial_connection.write(chunk)
                self.serial_connection.flush()
                # Small delay between chunks to prevent buffer overflow
                if i + chunk_size < len(command_bytes):  # Don't delay after last chunk
                    time.sleep(0.01)

            logger.info(f"Sent command: {repr(command)} (length: {len(command_bytes)} bytes)")

            if not wait_for_response:
                return {
                    "success": True,
                    "command": command,
                    "message": "Command sent successfully",
                    "timestamp": send_timestamp
                }

            # Wait a moment for command to be processed
            time.sleep(0.1)

            # Get all data received after sending the command
            response_data = self.get_data_since_timestamp(send_timestamp)

            # If no immediate response, wait a bit more
            if not response_data:
                time.sleep(0.5)
                response_data = self.get_data_since_timestamp(send_timestamp)

            return {
                "success": True,
                "command": command,
                "response_lines": response_data,
                "response_count": len(response_data),
                "timestamp": send_timestamp,
                "message": f"Command sent, received {len(response_data)} response lines"
            }

        except Exception as e:
            logger.error(f"Error sending command '{command}': {e}")
            return {
                "success": False,
                "error": str(e),
                "command": command
            }


@dataclass
class Device:
    """Represents a device (DUT or Probe) with its serial monitor."""
    role: DeviceRole
    serial_monitor: SerialMonitor

    def __init__(self, role: DeviceRole, serial_monitor: SerialMonitor):
        self.role = role
        self.serial_monitor = serial_monitor


class DeviceManager:
    """Thread-safe device state management for ESP32 testing.
    
    This class manages the lifecycle of ESP32 devices used in testing,
    providing thread-safe access, automatic state persistence, and
    proper resource cleanup.
    
    Features:
    - Thread-safe device access using RLock
    - Automatic state persistence to database
    - Resource cleanup with error handling
    - Convenient getter/setter methods
    - Support for DUT and Probe device roles
    """
    
    def __init__(self, database):
        """Initialize the device manager.
        
        Args:
            database: Database instance for state persistence
        """
        self._devices: Dict[DeviceRole, Optional[Device]] = {
            DeviceRole.DUT: None,
            DeviceRole.PROBE: None
        }
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        self._db = database  # Reference to database for persistence
    
    def get_device(self, role: DeviceRole) -> Optional['Device']:
        """Thread-safe device retrieval.
        
        Args:
            role: Device role (DUT or PROBE)
            
        Returns:
            Device instance or None if not connected
        """
        with self._lock:
            return self._devices.get(role)
    
    def set_device(self, role: DeviceRole, device: Optional['Device']) -> None:
        """Thread-safe device assignment.
        
        Args:
            role: Device role (DUT or PROBE)
            device: Device instance or None to clear
        """
        with self._lock:
            self._devices[role] = device
            self._save_state()
    
    def get_dut(self) -> Optional['Device']:
        """Convenience method for DUT access.
        
        Returns:
            DUT device instance or None
        """
        return self.get_device(DeviceRole.DUT)
    
    def get_probe(self) -> Optional['Device']:
        """Convenience method for Probe access.
        
        Returns:
            Probe device instance or None
        """
        return self.get_device(DeviceRole.PROBE)
    
    def set_dut(self, device: Optional['Device']) -> None:
        """Convenience method for DUT assignment.
        
        Args:
            device: Device instance or None to clear
        """
        self.set_device(DeviceRole.DUT, device)
    
    def set_probe(self, device: Optional['Device']) -> None:
        """Convenience method for Probe assignment.
        
        Args:
            device: Device instance or None to clear
        """
        self.set_device(DeviceRole.PROBE, device)
    
    def clear_device(self, role: DeviceRole) -> None:
        """Clear device and cleanup resources.
        
        This method safely disconnects the device and cleans up
        all associated resources before clearing the reference.
        SerialMonitor handles its own thread cleanup.
        
        Args:
            role: Device role to clear
        """
        with self._lock:
            device = self._devices.get(role)
            if device and device.serial_monitor:
                try:
                    port = device.serial_monitor.port
                    
                    # SerialMonitor handles its own thread cleanup via disconnect()
                    device.serial_monitor.disconnect()
                    
                    logger.info(f"Successfully disconnected {role.value} device from {port}")
                    
                except Exception as e:
                    logger.error(f"Error disconnecting {role.value}: {e}")
            
            # Clear device reference - this is DeviceManager's responsibility
            self._devices[role] = None
            
            # Persist the cleared state - this is DeviceManager's responsibility  
            self._save_state()
    
    def clear_all(self) -> None:
        """Clear all devices and cleanup resources.
        
        This method is typically called during server shutdown
        to ensure all resources are properly cleaned up.
        """
        logger.info("Clearing all devices...")
        for role in DeviceRole:
            self.clear_device(role)
        logger.info("All devices cleared")
    
    def get_connected_devices(self) -> Dict[str, bool]:
        """Get connection status of all devices.
        
        Returns:
            Dictionary mapping device roles to connection status
        """
        with self._lock:
            status = {}
            for role, device in self._devices.items():
                is_connected = (
                    device is not None and 
                    device.serial_monitor is not None and
                    device.serial_monitor.serial_connection is not None and
                    device.serial_monitor.serial_connection.is_open
                )
                status[role.value] = is_connected
            return status
    
    def _save_state(self) -> None:
        """Save current state to database.
        
        This method persists the current device state to the database
        for recovery across server restarts.
        """
        try:
            for role, device in self._devices.items():
                if device and device.serial_monitor:
                    state_data = {
                        "port": device.serial_monitor.port,
                        "baudrate": device.serial_monitor.baudrate,
                        "role": device.role.value,
                        "connected": (
                            device.serial_monitor.serial_connection is not None and 
                            device.serial_monitor.serial_connection.is_open 
                            if device.serial_monitor.serial_connection else False
                        )
                    }
                    self._db.store_data("device_state", state_data, role.value)
                else:
                    self._db.store_data("device_state", None, role.value)
        except Exception as e:
            logger.error(f"Failed to save device state: {e}")
    
    def load_state(self) -> None:
        """Load state from database.
        
        This method attempts to restore device connections from
        previously saved state. It's typically called during
        server startup or when needed.
        """
        with self._lock:
            for role in DeviceRole:
                try:
                    state_data = self._db.get_data("device_state", role.value)
                    if state_data and isinstance(state_data, dict):
                        device = Device(
                            role, 
                            SerialMonitor(state_data["port"], state_data["baudrate"], role.value)
                        )
                        
                        # Try to reconnect if was connected
                        if state_data.get("connected", False):
                            try:
                                if device.serial_monitor.connect():
                                    logger.info(f"Restored {role.value} connection to {state_data['port']}")
                                    self._devices[role] = device
                                else:
                                    logger.warning(f"Could not restore {role.value} connection")
                            except Exception as e:
                                logger.warning(f"Failed to restore {role.value} connection: {e}")
                        else:
                            self._devices[role] = device
                            logger.info(f"Restored {role.value} device configuration (not connected)")
                except Exception as e:
                    logger.error(f"Failed to load {role.value} state: {e}")
    
    def get_status(self) -> Dict[str, any]:
        """Get comprehensive status of all managed devices.
        
        Returns:
            Dictionary containing detailed status information
        """
        with self._lock:
            status = {
                "connected_devices": self.get_connected_devices(),
                "device_count": len([d for d in self._devices.values() if d is not None]),
                "devices": {}
            }
            
            for role, device in self._devices.items():
                if device:
                    device_status = {
                        "role": role.value,
                        "port": device.serial_monitor.port if device.serial_monitor else None,
                        "baudrate": device.serial_monitor.baudrate if device.serial_monitor else None,
                        "connected": False,
                        "monitoring": False
                    }
                    
                    if device.serial_monitor:
                        device_status["connected"] = (
                            device.serial_monitor.serial_connection is not None and
                            device.serial_monitor.serial_connection.is_open
                        )
                        device_status["monitoring"] = device.serial_monitor.is_monitoring
                    
                    status["devices"][role.value] = device_status
            
            return status
    
    def connect_device(self, role: DeviceRole, port: str, baudrate: int, auto_detect_chip: bool = True) -> Dict[str, Any]:
        """Connect a single device (DUT or Probe) with proper error handling.
        
        Args:
            role: Device role (DUT or PROBE)
            port: Serial port to connect to
            baudrate: Initial baudrate (may be auto-adjusted)
            auto_detect_chip: Whether to auto-detect chip type for baud optimization
            
        Returns:
            Connection result with success status and device details
        """
        try:
            # Check if already connected to the same port
            existing_device = self.get_device(role)
            if (existing_device and
                existing_device.serial_monitor and
                existing_device.serial_monitor.serial_connection and
                existing_device.serial_monitor.serial_connection.is_open and
                existing_device.serial_monitor.port == port):
                
                logger.info(f"Already connected to {port} for {role.value}")
                return {
                    "success": True,
                    "port": port,
                    "baudrate": existing_device.serial_monitor.serial_connection.baudrate,
                    "chip_type": None,
                    "already_connected": True
                }
            
            # Auto-detect chip type for baud rate optimization
            detected_baudrate = baudrate
            chip_type = None
            
            if auto_detect_chip:
                try:
                    chip_type = detect_chip_via_esptool(port)
                    if chip_type:
                        detected_baudrate = get_baud_rate_for_chip(chip_type)
                        if detected_baudrate != baudrate:
                            logger.info(f"Auto-detected {chip_type} on {port}, using baud rate {detected_baudrate}")
                except Exception as e:
                    logger.debug(f"Chip detection failed for {port}: {e}")
            
            # Create device with optimized settings
            log_prefix = role.value.upper()
            device = Device(role, SerialMonitor(port, detected_baudrate, log_prefix))
            
            # Attempt connection
            if device.serial_monitor.connect():
                # Store in device manager
                self.set_device(role, device)
                
                logger.info(f"Successfully connected {role.value} to {port} at {detected_baudrate} baud")
                return {
                    "success": True,
                    "port": port,
                    "baudrate": detected_baudrate,
                    "original_baudrate": baudrate,
                    "chip_type": chip_type,
                    "already_connected": False
                }
            else:
                return {
                    "success": False,
                    "port": port,
                    "error": "Failed to establish serial connection"
                }
                
        except Exception as e:
            logger.error(f"Error connecting {role.value} to {port}: {e}")
            return {
                "success": False,
                "port": port,
                "error": str(e)
            }
    
    async def connect_device_async(self, role: DeviceRole, port: str, baudrate: int = 115200, auto_detect_chip: bool = True) -> Dict[str, Any]:
        """Async wrapper for connect_device to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.connect_device, role, port, baudrate, auto_detect_chip)

    async def clear_device_async(self, role: DeviceRole) -> None:
        """Async wrapper for clear_device to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.clear_device, role)
