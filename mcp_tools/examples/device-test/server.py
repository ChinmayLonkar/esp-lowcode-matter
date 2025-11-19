#!/usr/bin/env python3
"""
Device Test MCP server.
This tool provides comprehensive functionality for testing ESP32 devices through serial monitoring 
and multi-protocol probing of hardware peripherals (I2C, UART, PWM, SPI, RMT, GPIO, ADC).
"""

import os
import sys
import json
import logging
import tempfile
import asyncio
import threading
import time
import re
import shlex
import subprocess
import glob
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, TypedDict, Literal, Union
from dataclasses import dataclass
from enum import Enum

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
from mcp_tools.components.path_setup import setup_path
setup_path()

# Import FastMCP modules
from fastmcp import FastMCP
from fastmcp.server.server import stdio_server as stdio_transport

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat
from mcp_tools.components.network import ApiClient, NetworkError

# Import device manager and related classes
try:
    from .device_manager import DeviceManager, DeviceRole, Device, SerialMonitor, detect_chip_via_esptool, get_baud_rate_for_chip
    from .test_framework import TestType, TestAction, TestCase, TestResult, TestExecutor
except ImportError:
    from device_manager import DeviceManager, DeviceRole, Device, SerialMonitor, detect_chip_via_esptool, get_baud_rate_for_chip
    from test_framework import TestType, TestAction, TestCase, TestResult, TestExecutor

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("Warning: pyserial not available. Serial monitoring will not work.")

from probe_config_tool import configure_probe

log_level = os.environ.get("MCP_LOG_LEVEL", os.environ.get("LOGGING_LEVEL", "INFO")).upper()
numeric_level = getattr(logging, log_level, logging.INFO)
mcp_log_file = os.environ.get("MCP_LOG_FILE")

# Set up handlers
handlers = []

console_level = os.environ.get("LOGGING_LEVEL", "INFO").upper()
console_numeric_level = getattr(logging, console_level, logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(console_numeric_level)
handlers.append(console_handler)

if mcp_log_file:
    file_handler = logging.FileHandler(mcp_log_file)
    file_handler.setLevel(numeric_level)  # Use MCP_LOG_LEVEL for file
    handlers.append(file_handler)

logging.basicConfig(
    level=min(numeric_level, console_numeric_level),  # Use the most permissive level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

if console_numeric_level >= logging.WARNING:
    logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.ERROR)
    logging.getLogger('fastmcp').setLevel(logging.ERROR)
elif mcp_log_file:
    mcp_logger = logging.getLogger('mcp.server.lowlevel.server')
    fastmcp_logger = logging.getLogger('fastmcp')
    mcp_logger.handlers = handlers
    fastmcp_logger.handlers = handlers
    mcp_logger.setLevel(numeric_level)
    fastmcp_logger.setLevel(numeric_level)
    mcp_logger.propagate = False
    fastmcp_logger.propagate = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

output = get_output_manager(format="text", color=True)

mcp = FastMCP(name="device-test")

device_manager = DeviceManager(db)

# Log management helper functions
def get_log_directory() -> str:
    """Get the directory where device logs are stored."""
    return os.environ.get("DEVICE_LOG_DIR", "logs")

def get_device_log_files(device_role: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get list of device log files with metadata.
    
    Args:
        device_role: Filter by device role ('DUT' or 'PROBE'), or None for all
        limit: Maximum number of files to return (most recent first)
        
    Returns:
        List of log file info dictionaries
    """
    log_dir = get_log_directory()
    log_files = []
    
    try:
        if not os.path.exists(log_dir):
            return []
            
        pattern = "*.log"
        if device_role:
            pattern = f"{device_role.upper()}__*.log"
            
        file_paths = glob.glob(os.path.join(log_dir, pattern))
        
        for file_path in file_paths:
            try:
                file_stat = os.stat(file_path)
                file_name = os.path.basename(file_path)
                
                # Parse filename to extract metadata
                # Format: ROLE__port_timestamp.log
                parts = file_name.replace('.log', '').split('__')
                if len(parts) >= 2:
                    role = parts[0]
                    port_timestamp = parts[1]
                    
                    # Extract timestamp from filename
                    timestamp_match = re.search(r'(\d{8}_\d{6})$', port_timestamp)
                    timestamp_str = timestamp_match.group(1) if timestamp_match else "unknown"
                    
                    log_files.append({
                        "file_path": file_path,
                        "file_name": file_name,
                        "device_role": role,
                        "port": port_timestamp.replace(f'_{timestamp_str}', '') if timestamp_match else port_timestamp,
                        "timestamp": timestamp_str,
                        "size": file_stat.st_size,
                        "modified": file_stat.st_mtime,
                        "modified_iso": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                    })
            except Exception as e:
                logger.warning(f"Error processing log file {file_path}: {e}")
                continue
                
        # Sort by modification time (newest first) and limit
        log_files.sort(key=lambda x: x["modified"], reverse=True)
        return log_files[:limit]
        
    except Exception as e:
        logger.error(f"Error scanning log directory {log_dir}: {e}")
        return []

def get_current_session_logs() -> Dict[str, Optional[str]]:
    """Get the current active session log files for DUT and PROBE.
    
    Returns:
        Dict with 'dut' and 'probe' keys pointing to current log file paths or None
    """
    result = {"dut": None, "probe": None}
    
    try:
        # Get current devices from device manager
        dut_device = device_manager.get_device(DeviceRole.DUT)
        probe_device = device_manager.get_device(DeviceRole.PROBE)
        
        # Get log file paths from active serial monitors
        if dut_device and hasattr(dut_device.serial_monitor, 'log_file_handle'):
            if dut_device.serial_monitor.log_file_handle:
                result["dut"] = dut_device.serial_monitor.log_file_handle.name
                
        if probe_device and hasattr(probe_device.serial_monitor, 'log_file_handle'):
            if probe_device.serial_monitor.log_file_handle:
                result["probe"] = probe_device.serial_monitor.log_file_handle.name
                    
    except Exception as e:
        logger.error(f"Error getting current session logs: {e}")
        
    return result

def read_log_file_content(file_path: str, tail_lines: Optional[int] = None) -> str:
    """Read log file content with optional tail functionality.
    
    Args:
        file_path: Path to the log file
        tail_lines: If specified, return only the last N lines
        
    Returns:
        Log file content as string
    """
    try:
        if not os.path.exists(file_path):
            return f"Log file not found: {file_path}"
            
        with open(file_path, 'r', encoding='utf-8') as f:
            if tail_lines:
                lines = f.readlines()
                return ''.join(lines[-tail_lines:])
            else:
                return f.read()
                
    except Exception as e:
        logger.error(f"Error reading log file {file_path}: {e}")
        return f"Error reading log file: {e}"

# MCP Resources Implementation
@mcp.resource("device-log://dut/current")
def get_dut_current_log() -> str:
    """Current DUT device log content.
    
    Provides access to the currently active DUT device log for real-time analysis.
    Contains timestamped serial output from the Device Under Test.
    """
    try:
        current_session = get_current_session_logs()
        if current_session["dut"]:
            return read_log_file_content(current_session["dut"], tail_lines=200)
        else:
            return "No active DUT session found. Please connect a DUT device first."
    except Exception as e:
        logger.error(f"Error reading current DUT log: {e}")
        return f"Error accessing DUT log: {e}"

@mcp.resource("device-log://probe/current")
def get_probe_current_log() -> str:
    """Current PROBE device log content.
    
    Provides access to the currently active PROBE device log for real-time analysis.
    Contains timestamped serial output from the Probe device including protocol transactions
    (I2C, UART, PWM, SPI, RMT, GPIO, ADC).
    """
    try:
        current_session = get_current_session_logs()
        if current_session["probe"]:
            return read_log_file_content(current_session["probe"], tail_lines=200)
        else:
            return "No active PROBE session found. Please connect a PROBE device first."
    except Exception as e:
        logger.error(f"Error reading current PROBE log: {e}")
        return f"Error accessing PROBE log: {e}"

@mcp.resource("device-log://dut/recent")
def get_dut_recent_logs() -> str:
    """Recent DUT device logs summary.
    
    Provides a summary of recent DUT log files with metadata and brief content previews.
    Useful for analyzing patterns across multiple test sessions.
    """
    try:
        log_files = get_device_log_files("DUT", limit=5)
        if not log_files:
            return "No DUT log files found."
            
        summary = "=== Recent DUT Logs Summary ===\n\n"
        for i, log_file in enumerate(log_files, 1):
            timestamp = log_file["timestamp"]
            try:
                dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                readable_time = timestamp
                
            summary += f"{i}. {log_file['file_name']}\n"
            summary += f"   Time: {readable_time}\n"
            summary += f"   Port: {log_file['port']}\n"
            summary += f"   Size: {log_file['size']} bytes\n"
            
            # Add preview of last few lines
            preview = read_log_file_content(log_file["file_path"], tail_lines=3)
            if preview:
                summary += f"   Preview:\n"
                for line in preview.strip().split('\n'):
                    summary += f"     {line}\n"
            summary += "\n"
            
        return summary
        
    except Exception as e:
        logger.error(f"Error reading recent DUT logs: {e}")
        return f"Error accessing recent DUT logs: {e}"

@mcp.resource("device-log://probe/recent")
def get_probe_recent_logs() -> str:
    """Recent PROBE device logs summary.
    
    Provides a summary of recent PROBE log files with metadata and brief content previews.
    Useful for analyzing protocol transactions (I2C, UART, PWM, SPI, RMT, GPIO, ADC) across multiple sessions.
    """
    try:
        log_files = get_device_log_files("PROBE", limit=5)
        if not log_files:
            return "No PROBE log files found."
            
        summary = "=== Recent PROBE Logs Summary ===\n\n"
        for i, log_file in enumerate(log_files, 1):
            timestamp = log_file["timestamp"]
            try:
                dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                readable_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                readable_time = timestamp
                
            summary += f"{i}. {log_file['file_name']}\n"
            summary += f"   Time: {readable_time}\n"
            summary += f"   Port: {log_file['port']}\n"
            summary += f"   Size: {log_file['size']} bytes\n"
            
            # Add preview of last few lines
            preview = read_log_file_content(log_file["file_path"], tail_lines=3)
            if preview:
                summary += f"   Preview:\n"
                for line in preview.strip().split('\n'):
                    summary += f"     {line}\n"
            summary += "\n"
            
        return summary
        
    except Exception as e:
        logger.error(f"Error reading recent PROBE logs: {e}")
        return f"Error accessing recent PROBE logs: {e}"

@mcp.resource("device-log://session/status")
def get_session_status() -> str:
    """Current device session status and log information.
    
    Provides overview of active device connections and their log file status.
    Useful for understanding the current testing setup and available data.
    """
    try:
        current_session = get_current_session_logs()
        
        status = "=== Device Session Status ===\n\n"
        
        # DUT Status
        status += "DUT (Device Under Test):\n"
        if current_session["dut"]:
            dut_file = os.path.basename(current_session["dut"])
            file_size = os.path.getsize(current_session["dut"]) if os.path.exists(current_session["dut"]) else 0
            status += f"  ✅ Active session: {dut_file}\n"
            status += f"  📁 Log size: {file_size} bytes\n"
            
            # Get device info from device manager if available
            dut_device = device_manager.get_device(DeviceRole.DUT)
            if dut_device:
                status += f"  🔌 Port: {dut_device.serial_monitor.port}\n"
                status += f"  📡 Monitoring: {'Active' if dut_device.serial_monitor.is_monitoring else 'Inactive'}\n"
        else:
            status += "  ❌ No active session\n"
            
        status += "\n"
        
        # PROBE Status  
        status += "PROBE (Test Device):\n"
        if current_session["probe"]:
            probe_file = os.path.basename(current_session["probe"])
            file_size = os.path.getsize(current_session["probe"]) if os.path.exists(current_session["probe"]) else 0
            status += f"  ✅ Active session: {probe_file}\n"
            status += f"  📁 Log size: {file_size} bytes\n"
            
            # Get device info from device manager if available
            probe_device = device_manager.get_device(DeviceRole.PROBE)
            if probe_device:
                status += f"  🔌 Port: {probe_device.serial_monitor.port}\n"
                status += f"  📡 Monitoring: {'Active' if probe_device.serial_monitor.is_monitoring else 'Inactive'}\n"
        else:
            status += "  ❌ No active session\n"
            
        # Summary of available logs
        all_logs = get_device_log_files(limit=10)
        status += f"\n📊 Total log files available: {len(all_logs)}\n"
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        return f"Error accessing session status: {e}"

# Convenience tool for quick log access
@mcp.tool(name="get_current_device_logs")
def get_current_device_logs(tail_lines: int = 100) -> Dict[str, Any]:
    """Get the current active session logs for both DUT and PROBE devices.
    
    Convenience tool to quickly access the most recent log content from
    currently connected devices.
    
    Args:
        tail_lines: Number of recent lines to return from each log (default: 100)
        
    Returns:
        Dict containing current log content for active devices
    """
    try:
        current_session = get_current_session_logs()
        result = {
            "success": True,
            "dut_log": None,
            "probe_log": None,
            "session_info": current_session
        }
        
        # Read DUT log if available
        if current_session["dut"]:
            content = read_log_file_content(current_session["dut"], tail_lines)
            result["dut_log"] = {
                "file_path": current_session["dut"],
                "content": content,
                "lines_shown": len(content.splitlines()),
                "truncated": True
            }
            
        # Read PROBE log if available  
        if current_session["probe"]:
            content = read_log_file_content(current_session["probe"], tail_lines)
            result["probe_log"] = {
                "file_path": current_session["probe"],
                "content": content,
                "lines_shown": len(content.splitlines()),
                "truncated": True
            }
            
        return result
        
    except Exception as e:
        logger.error(f"Error getting current device logs: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(name="list_serial_ports")
def list_serial_ports() -> Dict[str, Any]:
    """List available serial ports that are likely ESP32 devices.

    This tool scans the system for serial ports and filters for devices that match ESP32 specific 
    patterns (USB-to-UART bridges like CP210x, CH340, FTDI). Essential for device discovery
    before establishing connections.

    Returns:
        Dict with success status and list of available ports with descriptions
    """
    try:
        if not SERIAL_AVAILABLE:
            return {
                "success": True,
                "ports": [],
                "message": "Serial support not available"
            }

        all_ports = []
        for port in serial.tools.list_ports.comports():
            all_ports.append({
                "device": port.device,
                "name": port.name or "Unknown",
                "description": port.description or "Unknown",
                "manufacturer": port.manufacturer or "Unknown"
            })

        # Filter for ESP32-related ports
        esp32_ports = []
        for port in all_ports:
            device = (port["device"] or "").lower()
            description = (port["description"] or "").lower()
            manufacturer = (port["manufacturer"] or "").lower()

            # Skip known non-ESP32 ports
            skip_patterns = [
                "debug-console",
                "wlan-debug",
                "bluetooth",
                "incoming-port"
            ]

            if any(pattern in device or pattern in description for pattern in skip_patterns):
                continue

            # Include ports that are likely ESP32 devices
            esp32_patterns = [
                "esp32",
                "esp",
                "silicon labs",
                "cp210",
                "ch340",
                "ch341",
                "ftdi",
                "usb serial",
                "uart",
                "tty.usb",
                "ttyusb",
                "cu.usb",
                "com"
            ]

            # Check if it matches ESP32 patterns or has a known ESP32 manufacturer
            is_esp32_related = (
                any(pattern in device or pattern in description or pattern in manufacturer
                    for pattern in esp32_patterns) or
                manufacturer in ["silicon labs", "ftdi", "qinheng electronics"]
            )

            if is_esp32_related:
                esp32_ports.append(port)

        # Log tool usage
        db.record_tool_call(
            tool_name="list_serial_ports",
            parameters={},
            result={"ports_found": len(esp32_ports), "total_ports_scanned": len(all_ports)},
            status="success"
        )

        output.info(f"Found {len(esp32_ports)} ESP32-related ports out of {len(all_ports)} total ports")

        return {
            "success": True,
            "ports": esp32_ports,
            "total_scanned": len(all_ports),
            "message": f"Found {len(esp32_ports)} ESP32-related ports"
        }

    except Exception as e:
        error_message = f"Failed to list serial ports: {str(e)}"

        # Log error
        db.record_tool_call(
            tool_name="list_serial_ports",
            parameters={},
            status="error",
            error_message=error_message
        )

        output.error(error_message)

        return {
            "success": False,
            "error": error_message,
            "ports": []
        }

@mcp.tool(name="connect")
def connect(dut_port: str, probe_port: Optional[str] = None, baudrate: int = 115200, auto_detect_chip: bool = True) -> Dict[str, Any]:
    """Connect to ESP32 devices via serial ports.

    Establishes serial connections to ESP32 devices for testing. Supports dual-device setups
    with Device Under Test (DUT) and optional protocol monitoring Probe device. The Probe can 
    monitor multiple protocols (I2C, UART, PWM, SPI, RMT, GPIO, ADC) as configured. 
    Auto-detects chip type for optimal communication settings and initializes serial monitoring.

    Args:
        dut_port: Device Under Test serial port (e.g., '/dev/ttyUSB0', '/dev/tty.usbserial-10')
        probe_port: Protocol monitoring probe serial port (optional, for multi-protocol bus monitoring)
        baudrate: Serial baudrate (default: 115200, auto-optimized if chip detected)
        auto_detect_chip: Whether to auto-detect chip type for baud rate optimization (default: True)

    Returns:
        Connection status information with device details and chip identification
    """
    try:
        # Validate input ports
        if not dut_port or not dut_port.strip():
            error_msg = "DUT port cannot be empty"
            db.record_tool_call(
                tool_name="connect",
                parameters={"dut_port": dut_port, "probe_port": probe_port, "baudrate": baudrate},
                status="error",
                error_message=error_msg
            )
            output.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
        
        if probe_port and dut_port == probe_port:
            error_msg = "DUT and Probe ports must be different. Please specify different serial ports for each device."
            db.record_tool_call(
                tool_name="connect",
                parameters={"dut_port": dut_port, "probe_port": probe_port, "baudrate": baudrate},
                status="error",
                error_message=error_msg
            )
            output.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

        # Connect DUT first (always required)
        logger.info(f"Connecting DUT to {dut_port}...")
        dut_result = device_manager.connect_device(DeviceRole.DUT, dut_port, baudrate, auto_detect_chip)
        
        if not dut_result["success"]:
            # Log DUT connection failure
            db.record_tool_call(
                tool_name="connect",
                parameters={
                    "dut_port": dut_port, 
                    "probe_port": probe_port, 
                    "baudrate": baudrate, 
                    "auto_detect_chip": auto_detect_chip,
                    "dut_error": dut_result["error"]
                },
                status="error",
                error_message=f"DUT connection failed: {dut_result['error']}"
            )
            output.error(f"Failed to connect DUT: {dut_result['error']}")
            return {
                "success": False,
                "error": f"DUT connection failed: {dut_result['error']}",
                "dut": dut_result,
                "probe": None
            }

        # Connect Probe if requested
        probe_result = None
        if probe_port:
            logger.info(f"Connecting Probe to {probe_port}...")
            probe_result = device_manager.connect_device(DeviceRole.PROBE, probe_port, baudrate, auto_detect_chip)
            
            if not probe_result["success"]:
                logger.warning(f"Probe connection failed: {probe_result['error']}")
                # Don't fail the entire operation if only probe fails
        
        # Determine overall success status
        overall_success = dut_result["success"] and (not probe_port or (probe_result and probe_result["success"]))
        
        # Log complete connection attempt
        log_params = {
            "dut_port": dut_port,
            "probe_port": probe_port,
            "baudrate": baudrate,
            "auto_detect_chip": auto_detect_chip,
            "dut_success": dut_result["success"],
            "dut_baudrate": dut_result.get("baudrate"),
            "dut_chip_type": dut_result.get("chip_type"),
            "dut_already_connected": dut_result.get("already_connected", False)
        }
        
        if probe_result:
            log_params.update({
                "probe_success": probe_result["success"],
                "probe_baudrate": probe_result.get("baudrate"),
                "probe_chip_type": probe_result.get("chip_type"),
                "probe_already_connected": probe_result.get("already_connected", False),
                "probe_error": probe_result.get("error") if not probe_result["success"] else None
            })
        
        db.record_tool_call(
            tool_name="connect",
            parameters=log_params,
            status="success" if overall_success else "partial_success",
            error_message=f"Probe connection failed: {probe_result['error']}" if probe_result and not probe_result["success"] else None
        )

            # Prepare response message
        message = f"Successfully connected DUT to {dut_port}"
        if dut_result.get("already_connected"):
            message += " (already connected)"
        
            if probe_result:
                if probe_result["success"]:
                    message += f" and Probe to {probe_port}"
                if probe_result.get("already_connected"):
                    message += " (already connected)"
                else:
                    message += f" (Probe connection to {probe_port} failed: {probe_result['error']})"
        
        # Output based on overall success
        if overall_success:
            output.success(message)
        else:
            output.warning(message)  # DUT success but probe failed

        return {
            "success": overall_success,
            "dut": dut_result,
            "probe": probe_result,
            "message": message,
            "partial_success": not overall_success and dut_result["success"]  # DUT ok, probe failed
        }

    except Exception as e:
        # Provide user-friendly error messages
        error_str = str(e)
        if "could not open port" in error_str.lower() or "no such file or directory" in error_str.lower():
            friendly_error = f"Device not found: Cannot connect to {dut_port}. Please check that the device is connected and the port path is correct. Use 'list_serial_ports' to see available devices."
        elif "permission denied" in error_str.lower():
            friendly_error = f"Permission denied: Cannot access {dut_port}. You may need to add your user to the dialout group or run with sudo."
        else:
            friendly_error = f"Connection failed: {error_str}"

        # Log error
        db.record_tool_call(
            tool_name="connect",
            parameters={
                "dut_port": dut_port, 
                "probe_port": probe_port, 
                "baudrate": baudrate, 
                "auto_detect_chip": auto_detect_chip,
                "error": error_str
            },
            status="error",
            error_message=friendly_error
        )

        output.error(friendly_error)

        return {
            "success": False,
            "error": friendly_error
        }

@mcp.tool(name="disconnect")
def disconnect(device_role: str = None) -> Dict[str, Any]:
    """Disconnect from the current serial port.

    Safely closes serial connection for specified device role (DUT or PROBE). 
    Stops monitoring threads, cleans up resources, and resets connection state.
    Use when switching devices or ending test sessions.

    Args:
        device_role: Which device to disconnect - 'dut' (Device Under Test) or 'probe'

    Returns:
        Disconnection status information with cleanup details
    """

    if device_role is None:
        return {
            "success": False,
            "error": "Device role is required"
        }
    
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        # Log that no connection was active
        db.record_tool_call(
            tool_name="disconnect",
            parameters={
                "device_role": device_role.value,
                "port": "none"
            },
            status="success"
        )
        
        output.info(f"No {device_role.value.upper()} connection was active")
        
        return {
            "success": True,
            "message": f"No {device_role.value.upper()} serial connection was active",
            "device_role": device_role.value
        }

    try:
        port = device.serial_monitor.port

        # Let DeviceManager handle proper cleanup
        device_manager.clear_device(device_role)

        # Log success with proper parameters
        db.record_tool_call(
            tool_name="disconnect",
            parameters={
                "device_role": device_role.value,
                "port": port
            },
            status="success"
        )

        output.success(f"Disconnected {device_role.value.upper()} from {port}")

        return {
            "success": True,
            "message": f"Successfully disconnected {device_role.value.upper()} from {port}",
            "port": port,
            "device_role": device_role.value
        }

    except Exception as e:
        # Log error with proper parameters
        db.record_tool_call(
            tool_name="disconnect",
            parameters={
                "device_role": device_role.value,
                "port": port if 'port' in locals() else "unknown"
            },
            status="error",
            error_message=str(e)
        )

        output.error(f"Error disconnecting {device_role.value.upper()}: {str(e)}")

        return {
            "success": False,
            "error": str(e),
            "device_role": device_role.value
        }

@mcp.tool(name="clear_log_buffer")
def clear_log_buffer(device_role: str) -> Dict[str, Any]:
    """Manually clear the log buffer (useful for starting fresh without reset).

    Clears accumulated serial data without resetting the ESP32 device. Useful for:
    - Starting clean log collection between test phases
    - Removing boot messages before running specific tests
    - Clearing noise/debug output before monitoring critical events

    Args:
        device_role: Which device's buffer to clear - 'dut' or 'probe'

    Returns:
        Status information about the buffer clearing with cleared data count
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": False,
            "error": "No serial monitor instance available"
        }

    try:
        # Get current stats before clearing
        old_lines = len(device.serial_monitor.received_data) if device.serial_monitor.received_data else 0

        # Clear the buffer
        device.serial_monitor.clear_data()

        # Log success
        db.record_tool_call(
            tool_name="clear_log_buffer",
            parameters={},
            result={"lines_cleared": old_lines},
            status="success"
        )

        output.success(f"Cleared log buffer ({old_lines} lines removed)")

        return {
            "success": True,
            "lines_cleared": old_lines,
            "message": f"Successfully cleared {old_lines} lines from log buffer"
        }

    except Exception as e:
        # Log error
        db.record_tool_call(
            tool_name="clear_log_buffer",
            parameters={},
            status="error",
            error_message=str(e)
        )

        output.error(f"Error clearing log buffer: {str(e)}")

        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(name="start_serial_monitor")
def start_serial_monitor(device_role: str, auto_reset: bool = False) -> Dict[str, Any]:
    """Start monitoring serial data or reset ESP32 if requested.

    Initiates continuous serial data monitoring from the specified ESP32 device. Creates a 
    background thread that captures all UART output with timestamps. Essential for:
    - Capturing boot sequences and initialization logs
    - Monitoring application output during test execution
    - Detecting specific log patterns or error conditions
    - Real-time debugging of ESP32 firmware behavior
    
    The monitor maintains a circular buffer of recent data and supports pattern searching.
    Can optionally reset the device before starting monitoring to capture clean boot sequence.

    Args:
        device_role: The device role to start monitoring - 'dut' (Device Under Test) or 'probe'
        auto_reset: If True, performs hardware reset before monitoring (useful for capturing 
                   complete boot sequence). If False, continues from current device state 
                   (better for continuous operation monitoring)

    Returns:
        Status information about the monitoring
    """

    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": False,
            "error": "No serial connection established",
        }

    # Handle reset request
    if auto_reset:
        output.info("Performing ESP32 reset (continuous logging maintained)...")
        reset_success = device.serial_monitor.reset_esp32()
        if reset_success:
            message = "ESP32 reset completed, continuous logging maintained"
        else:
            message = "ESP32 reset failed, continuous logging continues"
    elif device.serial_monitor.is_monitoring:
        message = "Continuous monitoring already active"
    else:
        # This shouldn't happen with continuous monitoring, but handle it
        output.info("Starting continuous monitoring...")
        device.serial_monitor._start_continuous_monitoring()
        message = "Continuous monitoring started"

    try:
        # Log success
        db.record_tool_call(
            tool_name="start_serial_monitor",
            parameters={"auto_reset": auto_reset},
            status="success"
        )

        output.success(message)

        return {
            "success": True,
            "message": message,
            "auto_reset": auto_reset
        }

    except Exception as e:
        # Log error
        db.record_tool_call(
            tool_name="start_serial_monitor",
            parameters={"auto_reset": auto_reset},
            status="error",
            error_message=str(e)
        )

        output.error(f"Error with serial monitor: {str(e)}")

        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(name="reset_device")
def reset_device(device_role: str) -> Dict[str, Any]:
    """Reset the connected ESP32 device.

    Performs a hardware reset of the ESP32 device by toggling the DTR and RTS lines 
    on the serial connection. This triggers a complete system restart equivalent to 
    power-cycling the device. Use cases include:
    - Restarting device
    - Recovering from hung or crashed states  
    - Triggering fresh boot sequence for testing
    - Clearing runtime state and memory
    - Testing boot-time initialization code
    
    The reset is immediate and the device will begin its boot sequence. Some ESP32 variants may 
    have slight timing differences in reset behavior.

    Args:
        device_role: Which device to reset - 'dut' (Device Under Test) or 'probe'

    Returns:
        Status information about the reset operation
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": False,
            "error": "No serial connection established",
        }

    try:
        reset_success = device.serial_monitor.reset_esp32()

        # Log the operation
        db.record_tool_call(
            tool_name="reset_device",
            parameters={},
            status="success" if reset_success else "error",
            error_message=None if reset_success else "Reset operation failed"
        )

        if reset_success:
            output.success("ESP32 reset completed successfully")
            return {
                "success": True,
                "message": "ESP32 reset completed successfully",
            }
        else:
            output.error("ESP32 reset failed")
            return {
                "success": False,
                "error": "ESP32 reset operation failed"
            }

    except Exception as e:
        # Log error
        db.record_tool_call(
            tool_name="reset_device",
            parameters={},
            status="error",
            error_message=str(e)
        )

        output.error(f"Error resetting ESP32: {str(e)}")

        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(name="stop_serial_monitor")
def stop_serial_monitor(device_role: str) -> Dict[str, Any]:
    """Stop monitoring serial data.

    Gracefully stops the serial monitoring thread for the specified device. This:
    - Terminates the background data collection thread
    - Preserves existing buffered data for final analysis
    - Releases monitoring resources while keeping connection active
    - Allows for configuration changes or switching monitoring modes
    
    Use when you need to:
    - Temporarily pause monitoring during device configuration
    - Switch between different monitoring parameters
    - Reduce system load during non-critical periods
    - Prepare for device disconnection or test completion
    
    Note: This does NOT disconnect the serial port - the connection remains active.
    Use disconnect() to fully close the serial connection.

    Args:
        device_role: Which device to stop monitoring - 'dut' (Device Under Test) or 'probe'

    Returns:
        Status information about stopping the monitor including final data statistics
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": True,
            "message": "No serial monitor was running"
        }

    try:
        device.serial_monitor.stop_monitoring()

        # Log success
        db.record_tool_call(
            tool_name="stop_serial_monitor",
            parameters={},
            status="success"
        )

        output.success("Serial monitoring stopped")

        return {
            "success": True,
            "message": "Serial monitoring stopped successfully"
        }

    except Exception as e:
        # Log error
        db.record_tool_call(
            tool_name="stop_serial_monitor",
            parameters={},
            status="error",
            error_message=str(e)
        )

        output.error(f"Error stopping serial monitor: {str(e)}")

        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(name="get_serial_data")
def get_serial_data(device_role: str, seconds: float = 10.0) -> Dict[str, Any]:
    """Get recent serial data.

    Retrieves timestamped serial data from the device's monitoring buffer within the 
    specified time window. The data includes:
    - Raw UART output with original formatting preserved
    - Precise timestamps for each line (useful for timing analysis)
    - Boot messages, application logs, debug output, error messages
    - ESP-IDF system logs and custom application prints
    
    Useful for:
    - Analyzing device behavior and application flow
    - Debugging firmware issues and timing problems  
    - Searching for specific log patterns or error conditions
    - Verifying expected output after test operations
    - Capturing crash dumps and exception traces
    
    The buffer maintains a circular history, so older data may be overwritten in 
    high-throughput scenarios. Adjust the time window based on logging volume.

    Args:
        device_role: Which device's data to retrieve - 'dut' (Device Under Test) or 'probe'
        seconds: Number of seconds of recent data to retrieve (default: 10.0). 
                Higher values capture more history but may include less relevant data

    Returns:
        Recent serial data with timestamps
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        output.warning("No serial connection established")
        return {
            "success": False,
            "error": "No serial connection established",
            "data": []
        }

    try:
        data = device.serial_monitor.get_recent_data(seconds)

        # Log success
        db.record_tool_call(
            tool_name="get_serial_data",
            parameters={"seconds": seconds},
            result={"lines_retrieved": len(data)},
            status="success"
        )

        output.info(f"Retrieved {len(data)} lines of serial data")

        return {
            "success": True,
            "data": data,
            "lines_count": len(data),
            "timeframe_seconds": seconds
        }

    except Exception as e:
        # Log error
        db.record_tool_call(
            tool_name="get_serial_data",
            parameters={"seconds": seconds},
            status="error",
            error_message=str(e)
        )

        output.error(f"Error getting serial data: {str(e)}")

        return {
            "success": False,
            "error": str(e),
            "data": []
        }

async def run_command_async(cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> tuple[str, int]:
    """Run a command asynchronously and return stdout/stderr and exit code."""
    logger.info(f"Running command: {' '.join(cmd)}")
    if cwd:
        logger.info(f"Working directory: {cwd}")

    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd,
            env=env
        )
        stdout, _ = await process.communicate()
        output_str = stdout.decode('utf-8')
        logger.info(f"Command completed with return code: {process.returncode}")

        return output_str, process.returncode

    except asyncio.CancelledError:
        # Handle task cancellation gracefully
        if process and process.returncode is None:
            logger.warning("Command cancelled, terminating process...")
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Process didn't terminate gracefully, killing...")
                process.kill()
            except Exception as e:
                logger.warning(f"Error during process cleanup: {e}")
        raise

    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        if process and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except Exception:
                pass
        raise

def parse_flash_args(flash_args_path: str) -> Dict[str, Any]:
    """Parse the flash_args file to extract file mappings, skipping the first line.

    Args:
        flash_args_path: Path to the flash_args file

    Returns:
        Dictionary containing file mappings (first line is ignored)
    """
    if not os.path.exists(flash_args_path):
        raise FileNotFoundError(f"Flash args file not found: {flash_args_path}")

    with open(flash_args_path, 'r') as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]

    if len(lines) < 2:
        raise ValueError("Flash args file must have at least 2 lines (first line is skipped)")

    # Skip the first line entirely and process remaining lines for address and file mappings
    file_mappings = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2:
            address = parts[0]
            filename = parts[1]
            file_mappings.append({"address": address, "file": filename})

    return {
        "flash_params": [],  # No flash parameters since we skip the first line
        "file_mappings": file_mappings
    }

async def find_esptool() -> Optional[str]:
    """Find esptool.py in common locations, prioritizing venv installation."""
    # PRIORITY 1: Try current Python's esptool module (venv installation)
    try:
        import esptool
        esptool_module_path = esptool.__file__
        # esptool.__file__ points to __init__.py, we need esptool.py
        esptool_dir = os.path.dirname(esptool_module_path)
        esptool_script = os.path.join(esptool_dir, "esptool.py")
        if os.path.exists(esptool_script):
            logger.info(f"Using esptool from venv: {esptool_script}")
            return esptool_script
        # If esptool.py doesn't exist, use as module
        logger.info("Using esptool as Python module from venv")
        return "python3 -m esptool"
    except ImportError:
        pass

    # PRIORITY 2: Try direct command first (if esptool is in PATH)
    try:
        result = await run_command_async(["which", "esptool.py"])
        if result[1] == 0 and result[0].strip():
            esptool_path = result[0].strip()
            if os.path.exists(esptool_path):
                logger.info(f"Using esptool from PATH: {esptool_path}")
                return esptool_path
    except:
        pass

    # PRIORITY 3: Try esptool as a command (might be installed via pip)
    try:
        result = await run_command_async(["esptool.py", "--help"])
        if result[1] == 0:
            logger.info("Using esptool.py as command")
            return "esptool.py"  # Available as command
    except:
        pass

    # PRIORITY 4: Try to find in IDF_PATH (correct path structure)
    idf_path = os.environ.get("IDF_PATH")
    if idf_path:
        # Correct path in ESP-IDF
        esptool_path = os.path.join(idf_path, "components", "esptool_py", "esptool", "esptool.py")
        if os.path.exists(esptool_path):
            logger.info(f"Using esptool from IDF_PATH: {esptool_path}")
            return esptool_path

    # Try common system locations
    common_paths = [
        "/usr/local/bin/esptool.py",
        "/usr/bin/esptool.py",
        os.path.expanduser("~/.local/bin/esptool.py"),
        # Homebrew locations on macOS
        "/opt/homebrew/bin/esptool.py",
        "/usr/local/Cellar/esptool/*/bin/esptool.py",
    ]

    for path in common_paths:
        # Handle glob patterns
        if "*" in path:
            import glob
            matches = glob.glob(path)
            for match in matches:
                if os.path.exists(match):
                    return match
        elif os.path.exists(path):
            return path

    # Try to find using python -m esptool
    try:
        result = await run_command_async(["python", "-m", "esptool", "--help"])
        if result[1] == 0:
            return "python -m esptool"  # Available as module
    except:
        pass

    # Try python3 -m esptool
    try:
        result = await run_command_async(["python3", "-m", "esptool", "--help"])
        if result[1] == 0:
            return "python3 -m esptool"  # Available as module
    except:
        pass

    return None

async def flash_firmware(project_dir: str, port: Optional[str] = None) -> Dict[str, Any]:
    """Flash firmware to ESP32 device using flash_args file.

    Args:
        project_dir: Path to the project directory containing build/flash_args
        port: Serial port to use for flashing (optional, will auto-detect if not provided)

    Returns:
        Dictionary with success status, message, and output
    """
    try:
        # Find flash_args file
        flash_args_path = os.path.join(project_dir, "build", "flash_args")
        if not os.path.exists(flash_args_path):
            return {
                "success": False,
                "error": f"Flash args file not found: {flash_args_path}",
                "output": ""
            }

        # Parse flash arguments
        flash_config = parse_flash_args(flash_args_path)

        # Find esptool
        esptool_path = await find_esptool()
        if not esptool_path:
            return {
                "success": False,
                "error": "esptool.py not found. Please install esptool or set IDF_PATH.",
                "output": ""
            }
        logger.info(f"esptool_path: {os.environ.get('PATH')}")
        # Build esptool command
        if esptool_path.startswith("python"):
            # Handle "python -m esptool" or "python3 -m esptool"
            cmd = esptool_path.split()
        elif esptool_path == "esptool.py":
            # Handle direct command
            cmd = ["esptool.py"]
        elif esptool_path.endswith(".py"):
            # Handle script path
            cmd = ["python3", esptool_path]
        else:
            # Handle binary/executable
            cmd = [esptool_path]

        # Add port if specified
        if port:
            cmd.extend(["--port", port])

        # Add write_flash command
        cmd.append("write_flash")

        # Add file mappings
        build_dir = os.path.join(project_dir, "build")
        for mapping in flash_config["file_mappings"]:
            cmd.append(mapping["address"])
            # Make file path absolute relative to build directory
            file_path = os.path.join(build_dir, mapping["file"])
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "error": f"Binary file not found: {file_path}",
                    "output": ""
                }
            cmd.append(file_path)

        # Execute flash command
        output_str, return_code = await run_command_async(cmd, cwd=project_dir)

        if return_code == 0:
            return {
                "success": True,
                "message": "Firmware flashed successfully",
                "flash_config": flash_config
            }
        else:
            return {
                "success": False,
                "error": f"Flash command failed with return code {return_code}",
                "output": output_str
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Flash operation failed: {str(e)}",
            "output": ""
        }

async def _flash_firmware_impl(project_dir: str) -> Dict[str, Any]:
    """Flash firmware to ESP32 device using the project's build/flash_args file.

    Args:
        project_dir: Path to the ESP32 project directory containing build/flash_args

    Returns:
        Flash operation result with success status and details
    """
    # Initialize variables that might be used in finally block
    was_connected = False
    saved_port = None
    saved_baudrate = None

    try:
        logger.info(f"Starting flash_firmware_tool for project_dir: {project_dir}")

        # Load device state from persistent storage
        device_under_test = device_manager.get_dut()
        if device_under_test is None:
            device_manager.load_state()
            device_under_test = device_manager.get_dut()

        logger.debug(f"After loading state - device_under_test = {device_under_test}")
        logger.debug(f"device_under_test type = {type(device_under_test)}")
        if device_under_test is not None:
            logger.debug(f"device_under_test.serial_monitor = {device_under_test.serial_monitor}")
            if device_under_test.serial_monitor:
                logger.debug(f"device_under_test.serial_monitor.port = {device_under_test.serial_monitor.port}")
                logger.debug(f"device_under_test.serial_monitor.serial_connection = {device_under_test.serial_monitor.serial_connection}")

        # Check if device_under_test is initialized
        if device_under_test is None:
            logger.error("device_under_test is None in flash_firmware_tool after loading state")
            return {
                "success": False,
                "error": "No device connected. Please connect a device first using the 'connect' tool.",
                "output": ""
            }

        # Disconnect serial monitor if connected to avoid conflicts

        if device_under_test.serial_monitor and device_under_test.serial_monitor.serial_connection:
            was_connected = True
            saved_port = device_under_test.serial_monitor.port
            saved_baudrate = device_under_test.serial_monitor.baudrate
            output.info("Disconnecting serial monitor for flashing...")
            device_under_test.serial_monitor.disconnect()

        # Perform the flash operation
        logger.debug("Calling flash_firmware function...")
        result = await flash_firmware(project_dir, saved_port)
        logger.debug(f"Flash_firmware completed with result: {result.get('success')}")

        # Record the tool call
        db.record_tool_call(
            tool_name="flash_firmware",
            parameters={"project_dir": project_dir, "port": saved_port},
            result=result,
            status="success" if result["success"] else "error",
            error_message=result.get("error") if not result["success"] else None
        )

        if result["success"]:
            output.success(f"Firmware flashed successfully to ESP32")
            if result.get("flash_config"):
                flash_config = result["flash_config"]
                output.info(f"Flashed {len(flash_config['file_mappings'])} binary files")
        else:
            output.error(f"Flash failed: {result.get('error', 'Unknown error')}")

        return result

    except Exception as e:
        error_msg = f"Flash operation failed: {str(e)}"
        logger.error(f"Flash operation exception: {error_msg}", exc_info=True)
        output.error(error_msg)

        # Handle specific TaskGroup errors
        if "TaskGroup" in str(e) or "unhandled errors" in str(e):
            logger.error("TaskGroup error detected in flash operation")
            # Try to get more details about the exception
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

        # Record the failed tool call
        try:
            db.record_tool_call(
                tool_name="flash_firmware",
                parameters={"project_dir": project_dir, "port": saved_port if 'saved_port' in locals() else None},
                status="error",
                error_message=error_msg
            )
        except Exception as db_error:
            logger.error(f"Failed to record tool call: {db_error}")

        return {
            "success": False,
            "error": error_msg,
            "output": ""
        }

    finally:
        # Automatically reconnect serial monitor if it was connected before
        if was_connected and saved_port and device_under_test is not None:
            output.info("Flash complete. Reconnecting serial monitor...")
            try:
                # Wait a moment for the device to be ready after flashing
                await asyncio.sleep(2)

                # Create a new serial monitor with the saved connection info
                device_under_test.serial_monitor = SerialMonitor(saved_port, saved_baudrate)

                if await device_under_test.serial_monitor.connect_async():
                    output.success(f"Serial monitor reconnected to {saved_port}")
                else:
                    output.warning(f"Failed to reconnect serial monitor to {saved_port}. You may need to reconnect manually.")
            except asyncio.CancelledError:
                # Handle task cancellation gracefully
                output.warning("Reconnection cancelled during cleanup")
            except Exception as e:
                output.warning(f"Failed to reconnect serial monitor: {e}. You may need to reconnect manually.")
                logger.debug(f"Reconnection error details: {str(e)}", exc_info=True)
        elif was_connected and saved_port:
            logger.warning("Could not reconnect serial monitor: device_under_test is None")

@mcp.tool(name="flash_firmware")
async def flash_firmware_tool(project_dir: str) -> Dict[str, Any]:
    """Flash firmware to ESP32 device using the project's build/flash_args file.

    Programs compiled firmware onto the connected ESP32 device using ESP-IDF's flashing 
    mechanism. This tool automates the complete firmware deployment process:
    
    Requirements:
    - ESP-IDF project with successful build
    - build/flash_args file containing flash parameters and binary mappings
    - Compatible esptool.py installation (automatically located)
    - Matching target chip configuration
    
    Process:
    1. Locates and validates ESP-IDF project structure
    2. Reads flash_args file for binary locations and flash parameters
    3. Auto-detects connected ESP32 device and chip type
    4. Programs bootloader, partition table, and application binaries
    5. Verifies flash success and provides detailed status
    
    Use cases:
    - Deploying new firmware builds to development devices
    - Updating application code during iterative testing
    - Programming factory firmware or recovery images
    - Batch programming multiple devices with same firmware
    
    Note: Device will automatically reset after successful flashing and begin running
    the new firmware. Monitor serial output to verify proper boot sequence.

    Args:
        project_dir: Path to ESP-IDF project directory containing CMakeLists.txt and build/

    Returns:
        Detailed flash operation results
    """
    try:
        # Call the implementation with timeout protection
        result = await asyncio.wait_for(_flash_firmware_impl(project_dir), timeout=300.0)
        return result
    except asyncio.TimeoutError:
        error_msg = "Flash operation timed out after 5 minutes"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "output": ""
        }
    except Exception as e:
        # Handle any unhandled exceptions including TaskGroup errors
        error_msg = f"Flash operation failed with exception: {str(e)}"
        error_type = type(e).__name__

        logger.error(f"Flash tool wrapper caught {error_type}: {error_msg}")

        # Special handling for TaskGroup or ExceptionGroup errors
        if "TaskGroup" in error_type or "ExceptionGroup" in error_type or "unhandled errors" in str(e):
            logger.error("Detected async context management error")
            try:
                # Try to extract more details
                if hasattr(e, 'exceptions'):
                    logger.error(f"Sub-exceptions: {[str(ex) for ex in e.exceptions]}")
            except Exception:
                pass

        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")

        return {
            "success": False,
            "error": f"Flash operation failed due to {error_type}: {str(e)}",
            "output": ""
        }

@mcp.tool(name="flash_probe_config")
async def flash_probe_config(config_json_path: str, offset: int = 0x9000) -> Dict[str, Any]:
    """Flash probe configuration to ESP32 device's NVS partition.
    
    This tool validates, generates, and flashes a probe configuration JSON to the device's
    NVS partition. It's designed for the uart_probe project which uses runtime configuration
    stored in NVS to dynamically enable/disable protocol probes (UART, I2C, PWM, SPI, RMT, GPIO, ADC).
    
    The tool performs three steps automatically:
    1. Validates the JSON configuration (schema, pin ranges, conflicts)
    2. Generates an NVS partition binary with minified JSON
    3. Flashes the binary to the specified NVS offset
    
    Configuration Format:
    The JSON should contain a "probes" array with probe configurations. Each probe can be
    enabled/disabled and configured with specific pins and parameters. Example:
    
    {
      "version": 1,
      "device": {"name": "my-probe", "board": "esp32", "log": {"baud": 115200}},
      "probes": [
        {"type": "I2C", "enable": true, "scl_gpio": 22, "sda_gpio": 21},
        {"type": "UART", "enable": false, ...}
      ]
    }
    
    Requirements:
    - Device must be connected via connect() tool
    - ESP-IDF environment with nvs_partition_gen.py available
    - Valid probe configuration JSON
    - Matching partition table with NVS at specified offset
    
    Args:
        config_json_path: Path to the JSON file containing probe configuration
        offset: NVS partition flash offset in hex (default: 0x9000)
        
    Returns:
        Dict with success status, validation results, and flash output
    """
    try:
        # Import nvs_partition_gen
        try:
            import esp_idf_nvs_partition_gen.nvs_partition_gen as nvs_partition_gen
        except ImportError:
            return {
                "success": False,
                "error": "esp_idf_nvs_partition_gen not found. Please install ESP-IDF and activate the environment.",
                "output": ""
            }

        device = device_manager.get_device(DeviceRole.PROBE)
        if not device:
            return {
                "success": False,
                "error": f"No device connected. Use connect() first.",
                "output": ""
            }
        
        port = device.serial_monitor.port
        logger.info(f"Flashing probe config on port {port}")

        result = configure_probe(config_json_path, port, offset)
        if result != 0:
            return {
                "success": False,
                "error": "Failed to configure probe",
                "output": ""
            }

        return {
            "success": True,
            "message": "Probe configuration flashed successfully",
            "output": ""
        }

    except Exception as e:
        logger.error(f"flash_probe_config failed: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "output": ""
        }

@mcp.tool(name="get_monitor_status")
def get_monitor_status(device_role: str) -> Dict[str, Any]:
    """Get detailed status of the serial monitor including thread information.

    Provides comprehensive diagnostics about the serial monitoring system state.
    Essential for troubleshooting connection issues, monitoring performance, and 
    understanding system behavior. Returns detailed information about:
    
    Connection Status:
    - Serial port connection state and parameters
    - Device identification and chip type information
    - Baudrate and communication settings
    
    Monitoring Health:
    - Background thread status and activity
    - Data buffer utilization and performance metrics
    - Error counts and communication issues
    - Timestamp accuracy and data flow rates
    
    System Resources:
    - Memory usage of monitoring buffers
    - Thread responsiveness and CPU utilization
    - Queue depths and processing latencies
    
    Use for troubleshooting:
    - Diagnosing why log data isn't being captured
    - Identifying communication bottlenecks or errors
    - Verifying proper system initialization
    - Monitoring long-running test performance

    Args:
        device_role: Which device to check status for - 'dut' (Device Under Test) or 'probe'

    Returns:
        Comprehensive monitoring status including connection state, thread health, buffer
        statistics, error counts, and performance metrics
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": False,
            "error": "No serial monitor instance available"
        }

    try:
        # Get basic stats
        stats = device.serial_monitor.get_stats()

        # Add thread information
        thread_info = {
            "monitor_thread_exists": device.serial_monitor.monitor_thread is not None,
            "monitor_thread_alive": device.serial_monitor.monitor_thread.is_alive() if device.serial_monitor.monitor_thread else False,
            "stop_event_set": device.serial_monitor.stop_event.is_set(),
        }

        # Add serial connection details
        serial_info = {}
        if device.serial_monitor.serial_connection:
            try:
                serial_info = {
                    "port": device.serial_monitor.serial_connection.port,
                    "baudrate": device.serial_monitor.serial_connection.baudrate,
                    "is_open": device.serial_monitor.serial_connection.is_open,
                    "in_waiting": device.serial_monitor.serial_connection.in_waiting,
                    "timeout": device.serial_monitor.serial_connection.timeout,
                }
            except Exception as e:
                serial_info = {"error": f"Failed to get serial info: {e}"}

        # Combine all information
        result = {
            "success": True,
            "stats": stats,
            "thread_info": thread_info,
            "serial_info": serial_info,
        }

        # Log the tool call
        db.record_tool_call(
            tool_name="get_monitor_status",
            parameters={},
            result=result,
            status="success"
        )

        return result

    except Exception as e:
        error_msg = f"Error getting monitor status: {str(e)}"

        # Log error
        db.record_tool_call(
            tool_name="get_monitor_status",
            parameters={},
            status="error",
            error_message=error_msg
        )

        return {
            "success": False,
            "error": error_msg
        }

@mcp.tool(name="check_immediate_data")
def check_immediate_data(wait_seconds: float = 1.0, device_role: str = "dut") -> Dict[str, Any]:
    """Check if data is received immediately after connection/reset.

    Specialized diagnostic tool for analyzing device boot timing and data flow issues.
    Particularly valuable for debugging fast-booting ESP32 devices that may start 
    transmitting data before monitoring systems are fully initialized.
    
    Timing Analysis:
    - Captures data that arrives immediately after connection or reset
    - Measures exact timing of first data reception  
    - Identifies boot sequence timing patterns
    - Detects missed boot messages due to initialization delays
    
    Common Use Cases:
    - Debugging "missing boot messages" problems
    - Verifying proper serial monitor initialization timing
    - Analyzing ESP32 boot sequence timing variations
    - Troubleshooting intermittent data capture issues
    - Optimizing monitoring system responsiveness
    
    ESP32-Specific Scenarios:
    - Some ESP32 variants boot very quickly (< 500ms)
    - Boot ROM messages may appear before monitor is ready
    - Different chip types have varying boot timing characteristics
    - Reset timing can affect data capture reliability
    
    The tool provides precise timing measurements to help optimize monitoring
    parameters and identify timing-related issues.

    Args:
        wait_seconds: Duration to monitor for immediate data (default: 1.0). 
                     Shorter values focus on boot timing, longer values capture 
                     more complete initialization sequences
        device_role: Which device to monitor - 'dut' (Device Under Test) or 'probe'

    Returns:
        Detailed timing information including data arrival patterns, exact timestamps,
        boot sequence analysis, and recommendations for timing optimization
    """
    if device_role == "dut":
        device_role = DeviceRole.DUT
    elif device_role == "probe":
        device_role = DeviceRole.PROBE
    else:
        return {
            "success": False,
            "error": "Invalid device role"
        }
    device = device_manager.get_device(device_role)

    if not device or not device.serial_monitor:
        return {
            "success": False,
            "error": "No serial monitor instance available"
        }

    try:
        # Record initial state
        initial_lines = len(device.serial_monitor.received_data) if device.serial_monitor.received_data else 0
        initial_bytes = device.serial_monitor.bytes_received
        start_time = time.time()

        output.info(f"Checking for immediate data reception over {wait_seconds} seconds...")
        output.info(f"Initial state: {initial_lines} lines, {initial_bytes} bytes")

        # Wait and periodically check for new data
        check_interval = 0.1  # Check every 100ms
        checks = int(wait_seconds / check_interval)
        data_timeline = []

        for i in range(checks):
            time.sleep(check_interval)
            current_time = time.time() - start_time
            current_lines = len(device.serial_monitor.received_data) if device.serial_monitor.received_data else 0
            current_bytes = device.serial_monitor.bytes_received

            new_lines = current_lines - initial_lines
            new_bytes = current_bytes - initial_bytes

            if new_lines > 0 or new_bytes > 0:
                data_timeline.append({
                    "time_seconds": round(current_time, 2),
                    "new_lines": new_lines,
                    "new_bytes": new_bytes,
                    "total_lines": current_lines,
                    "total_bytes": current_bytes
                })

        # Final state
        final_lines = len(device.serial_monitor.received_data) if device.serial_monitor.received_data else 0
        final_bytes = device.serial_monitor.bytes_received
        total_new_lines = final_lines - initial_lines
        total_new_bytes = final_bytes - initial_bytes

        # Get recent data for analysis
        recent_data = device.serial_monitor.get_recent_data(int(wait_seconds) + 1)

        result = {
            "success": True,
            "wait_seconds": wait_seconds,
            "initial_state": {
                "lines": initial_lines,
                "bytes": initial_bytes
            },
            "final_state": {
                "lines": final_lines,
                "bytes": final_bytes
            },
            "new_data": {
                "lines": total_new_lines,
                "bytes": total_new_bytes
            },
            "data_timeline": data_timeline,
            "recent_data_sample": recent_data[:5] if recent_data else [],
            "monitoring_active": device.serial_monitor.is_monitoring,
            "thread_alive": device.serial_monitor.monitor_thread.is_alive() if device.serial_monitor.monitor_thread else False
        }

        # Log the results
        if total_new_lines > 0:
            output.success(f"Received {total_new_lines} new lines and {total_new_bytes} new bytes")
            if data_timeline:
                first_data_time = data_timeline[0]["time_seconds"]
                output.info(f"First data received at {first_data_time}s after start")
        else:
            output.warning(f"No new data received in {wait_seconds} seconds")

        # Log tool usage
        db.record_tool_call(
            tool_name="check_immediate_data",
            parameters={"wait_seconds": wait_seconds},
            result=result,
            status="success"
        )

        return result

    except Exception as e:
        error_msg = f"Error checking immediate data: {str(e)}"
        output.error(error_msg)

        # Log error
        db.record_tool_call(
            tool_name="check_immediate_data",
            parameters={"wait_seconds": wait_seconds},
            status="error",
            error_message=error_msg
        )

        return {
            "success": False,
            "error": error_msg
        }

@mcp.tool(name="generate_merged_log")
def generate_merged_log(
    output_file: str = "merged_i2c.txt"
) -> Dict[str, Any]:
    """Generate merged protocol log from ALL data captured since monitoring started.
    
    This tool merges the COMPLETE capture history from both DUT (device under test) and PROBE 
    devices, creating a unified timeline of protocol transactions (I2C, UART, PWM, SPI, etc.), 
    and application behavior from the moment monitoring began. This provides full context for LLM analysis.
    
    Prerequisites:
    1. DUT device connected (device running your application)
    2. PROBE device connected (protocol monitoring probe with configurable protocols)
    3. Both devices actively monitoring via `start_serial_monitor`
    4. DUT logging in ESP-IDF format
    5. PROBE logging in protocol-specific formats:
       - I2C: +<us> <R/W> 0x<ADDR> [<DATA>]
       - UART: @<us> <CH> "<TEXT>" [<HEX>]
       - PWM: ~<us> PWM freq=<freq> duty=<duty> width=<width> period=<period>
       - SPI: *<us> SPI: [<HEX>,...]
       - ADC: ^<us> ADC: GPIO<gpio> val=<value>
       - RMT: &<us> RMT: n=<count> res=<resolution>Hz [...]
       - GPIO: #<us> GPIO: <pin>=<level>
    
    Workflow:
    1. `connect` - Connect DUT and PROBE ports
    2. `start_serial_monitor` - Start capturing on both devices (data accumulates)
    3. [Run your tests / let devices communicate]
    4. `generate_merged_log` - Generate complete merged log
    5. Read and analyze the merged.txt file
    
    Key Advantage:
    - Captures ENTIRE session from start of monitoring
    - LLM gets full timeline context, not just recent data
    - Can call multiple times to see progress (includes all historical data)
    
    Output Format:
    - Chronological text file with interleaved DUT and probe events
    - Format: [timestamp_us] <SOURCE> <content>
    - Complete timeline from monitoring start
    - Optimized for LLM consumption
    
    Use Cases:
    - Verify complete protocol initialization sequences (I2C, UART, etc.)
    - Debug peripheral communication from startup through failure
    - Analyze long-running test sessions with multiple protocols
    - Generate verification reports with full context
    - Correlate application behavior with bus/peripheral activity

    Args:
        output_file: Path for merged output file (default: merged_i2c.txt)

    Returns:
        Dict with success status, statistics, and output file path
    """
    logger.info(f"Generating merged protocol log from complete capture history")
    
    try:
        # Check if devices are connected and monitoring
        dut_device = device_manager.get_device(DeviceRole.DUT)
        probe_device = device_manager.get_device(DeviceRole.PROBE)
        
        if not dut_device:
            return {
                "success": False,
                "error": "DUT device not connected. Use 'connect' tool first with DUT port."
            }
        
        if not probe_device:
            return {
                "success": False,
                "error": "PROBE device not connected. Use 'connect' tool first with PROBE port (protocol monitoring probe)."
            }
        
        # Get ALL serial data from both devices since monitoring started (returns List[str])
        dut_data = dut_device.serial_monitor.get_all_data() if dut_device.serial_monitor else []
        probe_data = probe_device.serial_monitor.get_all_data() if probe_device.serial_monitor else []
        
        if not dut_data:
            return {
                "success": False,
                "error": "No data from DUT device. Ensure 'start_serial_monitor' was called for DUT."
            }
        
        if not probe_data:
            return {
                "success": False,
                "error": "No data from PROBE device. Ensure 'start_serial_monitor' was called for PROBE (protocol monitoring probe)."
            }
        
        # Parse data
        import re
        idf_pattern = re.compile(r"^[IWE] \((\d+)\)\s+([^:]+):\s+(.*)$")
        i2c_pattern = re.compile(r"^\+(\d+)\s+([RW])\s+0x([0-9A-Fa-f]{2})\s+\[([0-9A-Fa-f,]*)\]")
        uart_pattern = re.compile(r'^@(\d+)\s+([AB])\s+"((?:[^"\\]|\\.)*)"\s+\[([0-9A-F,]*)\]')
        pwm_pattern = re.compile(r'^~(\d+)\s+PWM\s+freq=([\d.]+)\s+duty=([\d.]+)\s+width=(\d+)\s+period=(\d+)')
        spi_pattern = re.compile(r'^\*(\d+)\s+SPI:\s+\[([0-9A-F,]+)\]')
        adc_pattern = re.compile(r'^\^(\d+)\s+ADC:\s+GPIO(\d+)\s+val=(\d+)')
        rmt_pattern = re.compile(r'^&(\d+)\s+RMT:\s+n=(\d+)\s+res=(\d+)Hz\s+\[(.+)\]')
        gpio_pattern = re.compile(r'^#(\d+)\s+GPIO:\s+(\d+)=(\d+)')
        
        # Parse DUT (master) logs (dut_data is already a list of lines)
        master_events = []
        for line in dut_data:
            line = line.rstrip("\r\n")
            if not line:
                continue
            
            m = idf_pattern.match(line)
            if not m:
                continue
            
            ts_ms = int(m.group(1))
            tag = m.group(2)
            msg = m.group(3)
            
            # Filter noise
            if msg.strip().replace("-", "") == "":
                continue
            
            master_events.append({
                "ts_us": ts_ms * 1000,
                "tag": tag,
                "msg": msg
            })
        
        # Parse PROBE (probe) logs (probe_data is already a list of lines)
        probe_events: List[Dict[str, Any]] = []
        i2c_txns: List[Dict[str, Any]] = []
        uart_msgs: List[Dict[str, Any]] = []
        pwm_events: List[Dict[str, Any]] = []
        spi_txns: List[Dict[str, Any]] = []
        adc_samples: List[Dict[str, Any]] = []
        rmt_events: List[Dict[str, Any]] = []
        gpio_events: List[Dict[str, Any]] = []
        for line in probe_data:
            line = line.strip()
            if not line:
                continue
            
            mi2c = i2c_pattern.match(line)
            if mi2c:
                rel_us = int(mi2c.group(1))
                rw = mi2c.group(2)
                addr = int(mi2c.group(3), 16)
                data = mi2c.group(4)
                evt_i2c = {
                    "type": "i2c",
                    "rel_us": rel_us,
                    "rw": rw,
                    "addr": addr,
                    "data": data
                }
                probe_events.append(evt_i2c)
                i2c_txns.append(evt_i2c)
                continue
            
            muart = uart_pattern.match(line)
            if muart:
                rel_us = int(muart.group(1))
                ch = muart.group(2)
                text = muart.group(3)
                data = muart.group(4)
                evt_uart = {
                    "type": "uart",
                    "rel_us": rel_us,
                    "ch": ch,
                    "text": text,
                    "data": data
                }
                probe_events.append(evt_uart)
                uart_msgs.append(evt_uart)
                continue
            
            mpwm = pwm_pattern.match(line)
            if mpwm:
                rel_us = int(mpwm.group(1))
                freq = float(mpwm.group(2))
                duty = float(mpwm.group(3))
                width = int(mpwm.group(4))
                period = int(mpwm.group(5))
                evt_pwm = {
                    "type": "pwm",
                    "rel_us": rel_us,
                    "freq": freq,
                    "duty": duty,
                    "width": width,
                    "period": period
                }
                probe_events.append(evt_pwm)
                pwm_events.append(evt_pwm)
                continue
            
            mspi = spi_pattern.match(line)
            if mspi:
                rel_us = int(mspi.group(1))
                data = mspi.group(2)
                evt_spi = {
                    "type": "spi",
                    "rel_us": rel_us,
                    "data": data
                }
                probe_events.append(evt_spi)
                spi_txns.append(evt_spi)
                continue
            
            madc = adc_pattern.match(line)
            if madc:
                rel_us = int(madc.group(1))
                gpio = int(madc.group(2))
                value = int(madc.group(3))
                evt_adc = {
                    "type": "adc",
                    "rel_us": rel_us,
                    "gpio": gpio,
                    "value": value
                }
                probe_events.append(evt_adc)
                adc_samples.append(evt_adc)
                continue
            
            mrmt = rmt_pattern.match(line)
            if mrmt:
                rel_us = int(mrmt.group(1))
                count = int(mrmt.group(2))
                resolution = int(mrmt.group(3))
                symbols = mrmt.group(4)
                evt_rmt = {
                    "type": "rmt",
                    "rel_us": rel_us,
                    "count": count,
                    "resolution": resolution,
                    "symbols": symbols
                }
                probe_events.append(evt_rmt)
                rmt_events.append(evt_rmt)
                continue
            
            mgpio = gpio_pattern.match(line)
            if mgpio:
                rel_us = int(mgpio.group(1))
                pin = int(mgpio.group(2))
                level = int(mgpio.group(3))
                evt_gpio = {
                    "type": "gpio",
                    "rel_us": rel_us,
                    "pin": pin,
                    "level": level
                }
                probe_events.append(evt_gpio)
                gpio_events.append(evt_gpio)
                continue
        
        if not master_events:
            return {
                "success": False,
                "error": "No master events parsed from DUT. Check that DUT is logging in ESP-IDF format."
            }
        
        if not probe_events:
            return {
                "success": False,
                "error": "No probe events parsed from PROBE. Expected protocol formats: I2C '+<us> <R/W> 0x<ADDR> [<DATA>]', UART '@<us> <A|B> \"<TEXT>\" [<HEX>]', PWM '~<us> PWM freq=... duty=...', SPI '*<us> SPI: [<HEX>]', ADC '^<us> ADC: GPIO<n> val=<n>', RMT '&<us> RMT: ...', GPIO '#<us> GPIO: <pin>=<level>', or other configured protocol formats."
            }
        
        # Calculate time alignment (align earliest probe event to first master event)
        earliest_probe_rel = min(evt["rel_us"] for evt in probe_events)
        offset_us = master_events[0]["ts_us"] - earliest_probe_rel
        
        # Merge events
        merged = []
        for ev in master_events:
            merged.append((ev["ts_us"], "master", ev))
        for evt in probe_events:
            aligned_ts = evt["rel_us"] + offset_us
            merged.append((aligned_ts, "probe", evt))
        
        merged.sort(key=lambda x: x[0])
        
        # Format output
        lines = []
        lines.append("=" * 80)
        lines.append("PROTOCOL TRANSACTION LOG (Multi-Protocol) - Complete Capture (DUT + PROBE)")
        lines.append("=" * 80)
        lines.append(f"DUT events: {len(master_events)}")
        lines.append(f"PROBE I2C transactions: {len(i2c_txns)}")
        lines.append(f"PROBE UART messages: {len(uart_msgs)}")
        lines.append(f"PROBE PWM events: {len(pwm_events)}")
        lines.append(f"PROBE SPI transactions: {len(spi_txns)}")
        lines.append(f"PROBE ADC samples: {len(adc_samples)}")
        lines.append(f"PROBE RMT events: {len(rmt_events)}")
        lines.append(f"PROBE GPIO events: {len(gpio_events)}")
        lines.append(f"Total merged events: {len(merged)}")
        lines.append(f"Time alignment offset: {offset_us} us")
        lines.append("Format: [timestamp_us] <SOURCE> <content>")
        lines.append("=" * 80)
        lines.append("")
        
        for ts_us, source, data in merged:
            if source == "master":
                tag = data.get("tag", "")
                msg = data.get("msg", "")
                lines.append(f"[{ts_us:12d}] DUT    {tag:15s} {msg}")
            else:
                if data.get("type") == "i2c":
                    rw = "READ " if data["rw"] == "R" else "WRITE"
                    addr = data["addr"]
                    data_bytes = data["data"]
                    lines.append(f"[{ts_us:12d}] PROBE  I2C   {rw:5s} 0x{addr:02X} [{data_bytes}]")
                elif data.get("type") == "uart":
                    ch = data.get("ch", "?")
                    text = data.get("text", "")
                    data_bytes = data.get("data", "")
                    lines.append(f"[{ts_us:12d}] PROBE  UART  {ch} \"{text}\" [{data_bytes}]")
                elif data.get("type") == "pwm":
                    freq = data.get("freq", 0)
                    duty = data.get("duty", 0)
                    width = data.get("width", 0)
                    period = data.get("period", 0)
                    lines.append(f"[{ts_us:12d}] PROBE  PWM   freq={freq:.2f} duty={duty:.2f} width={width} period={period}")
                elif data.get("type") == "spi":
                    data_bytes = data.get("data", "")
                    lines.append(f"[{ts_us:12d}] PROBE  SPI   [{data_bytes}]")
                elif data.get("type") == "adc":
                    gpio = data.get("gpio", 0)
                    value = data.get("value", 0)
                    lines.append(f"[{ts_us:12d}] PROBE  ADC   GPIO{gpio} val={value}")
                elif data.get("type") == "rmt":
                    count = data.get("count", 0)
                    resolution = data.get("resolution", 0)
                    symbols = data.get("symbols", "")
                    lines.append(f"[{ts_us:12d}] PROBE  RMT   n={count} res={resolution}Hz [{symbols}]")
                elif data.get("type") == "gpio":
                    pin = data.get("pin", 0)
                    level = data.get("level", 0)
                    lines.append(f"[{ts_us:12d}] PROBE  GPIO  {pin}={level}")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("END OF LOG")
        lines.append("=" * 80)
        
        # Write output
        output_text = "\n".join(lines)
        # Convert to absolute path
        output_path = os.path.abspath(output_file)
        with open(output_path, 'w') as f:
            f.write(output_text)
        
        logger.info(f"Successfully merged live logs to: {output_path}")
        
        return {
            "success": True,
            "output_file": output_path,
            "statistics": {
                "dut_events": len(master_events),
                "probe_i2c_transactions": len(i2c_txns),
                "probe_uart_messages": len(uart_msgs),
                "probe_pwm_events": len(pwm_events),
                "probe_spi_transactions": len(spi_txns),
                "probe_adc_samples": len(adc_samples),
                "probe_rmt_events": len(rmt_events),
                "probe_gpio_events": len(gpio_events),
                "total_merged_events": len(merged),
                "time_offset_us": offset_us
            },
            "message": f"Successfully merged {len(master_events)} DUT events with {len(probe_events)} probe protocol events (I2C:{len(i2c_txns)}, UART:{len(uart_msgs)}, PWM:{len(pwm_events)}, SPI:{len(spi_txns)}, ADC:{len(adc_samples)}, RMT:{len(rmt_events)}, GPIO:{len(gpio_events)}) from complete capture history"
        }
    
    except Exception as e:
        logger.error(f"Error merging live logs: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to merge live logs: {str(e)}"
        }

# ============================================================================
# MCP PROMPTS - Structured Testing Workflows
# ============================================================================

@mcp.prompt()
def develop_esp32_firmware(
    requirements: str,
    device_type: str = "sensor",
    communication_protocol: str = "i2c"
) -> str:
    """Complete ESP32 firmware development workflow from requirements to implementation.
    
    Steps: Understand → Plan → Implement → Patch → Build
    
    Args:
        requirements: User requirements or task description
        device_type: Type of device/driver (sensor, display, motor_driver, etc.)
        communication_protocol: Protocol to use (i2c, spi, uart, etc.)
    """
    return f"""Execute COMPLETE firmware development workflow:

REQUIREMENTS: {requirements}
DEVICE TYPE: {device_type}
PROTOCOL: {communication_protocol.upper()}

══════════════════════════════════════════════════════════════════════════
STEP 1: UNDERSTAND REQUIREMENTS
══════════════════════════════════════════════════════════════════════════
- Carefully read the user request, files, and references
- If unclear, ask clarifying questions
- Always request supporting documentation if not provided

**For file references (@filename):**
- Use read_file or search_file to access content

**For PDF datasheets:**
- Use extract_pdf to extract markdown and images
- Use get_image for critical diagrams (pinouts, timing, block diagrams)

**For websites:**
- Use web_page_reader to fetch content

**When creating drivers ({communication_protocol.upper()}/{device_type}):**
From extracted markdown, generate THREE files in docs/ folder:
1. **registers.md** - All register addresses, bit fields, default values
2. **commands.md** - Communication protocol details, command sequences
3. **summary.md** - Device overview, complete initialization sequence,
   pin configuration, power requirements, timing constraints

Only proceed after resources are fully understood.

══════════════════════════════════════════════════════════════════════════
STEP 2: PLAN
══════════════════════════════════════════════════════════════════════════
- Summarize requirements and constraints
- List design approach, dependencies, edge cases to handle
- Identify required ESP-IDF components

**CRITICAL FOR {communication_protocol.upper().upper()}:**
{'- MUST use clock frequency ≤10kHz to support probe capture' if communication_protocol.lower() == 'i2c' else ''}
{'- Mention this after testing, specifying correct operating frequency' if communication_protocol.lower() == 'i2c' else ''}

══════════════════════════════════════════════════════════════════════════
STEP 3: IMPLEMENT
══════════════════════════════════════════════════════════════════════════
- Generate C code using ESP-IDF APIs
- Organize into proper ESP-IDF project structure:
  * components/ - Reusable components
  * main/ - Application code
  * CMakeLists.txt - Build configuration
  * sdkconfig.defaults - Default SDK config
  * README.md - Project documentation
- Add required components (use idf-component-registry if needed)
- Use robust error handling, comments, follow ESP-IDF conventions

══════════════════════════════════════════════════════════════════════════
STEP 4: PATCH FILES (if modifying existing code)
══════════════════════════════════════════════════════════════════════════
- If modifying existing files, respond in patches
- Use apply_patch tool
- ALWAYS use absolute paths, no relative paths
- NEVER use backticks ``` inside patches

══════════════════════════════════════════════════════════════════════════
STEP 5: BUILD
══════════════════════════════════════════════════════════════════════════
- Build firmware using idf-builder MCP tools
- Confirm build succeeds before proceeding
- Always state build progress to user

**NEXT STEP:** After successful build, use /test_firmware_with_probe
to test and verify the implementation with protocol analysis.
"""

@mcp.prompt()
def test_firmware_with_probe(
    project_path: str,
    protocol: str = "i2c",
    dut_pins: str = "",
    probe_pins: str = "",
    skip_build: bool = False
) -> str:
    """Complete firmware testing workflow with protocol probe verification.
    
    Comprehensive workflow: build → probe config → connect → flash → monitor → analyze
    
    Args:
        project_path: Absolute path to ESP-IDF project
        protocol: Protocol to test (i2c, uart, spi, pwm, gpio, adc, rmt)
        dut_pins: DUT pin config (e.g., "SCL=22,SDA=21") - optional
        probe_pins: Probe pin config (e.g., "SCL=22,SDA=21") - optional  
        skip_build: Skip build step if firmware already built
    """
    return f"""Execute COMPLETE firmware testing workflow with {protocol.upper()} protocol verification:

PROJECT: {project_path}
PROTOCOL: {protocol.upper()}
DUT PINS: {dut_pins if dut_pins else "Will be determined from firmware"}
PROBE PINS: {probe_pins if probe_pins else "Will use recommended probe pins"}
SKIP BUILD: {'Yes (using existing build)' if skip_build else 'No (will build firmware)'}

CRITICAL: Probe logs are the SOURCE OF TRUTH for protocol verification.

══════════════════════════════════════════════════════════════════════════
STEP 1: BUILD FIRMWARE {'(SKIPPED)' if skip_build else ''}
══════════════════════════════════════════════════════════════════════════
{'''- Using existing build artifacts
- Verify build/ directory exists with .bin files''' if skip_build else '''- Use idf-builder MCP: build_project("{}")
- STOP if build fails - fix errors before proceeding
- Verify build succeeds before continuing'''.format(project_path)}

══════════════════════════════════════════════════════════════════════════
STEP 2: ANALYZE DUT FIRMWARE
══════════════════════════════════════════════════════════════════════════
- Read the DUT source code in {project_path}/main/
- Identify {protocol.upper()} configuration:
  * GPIO pins used (SCL/SDA for I2C, TX/RX for UART, etc.)
  * Communication parameters (clock speed, baud rate)
  * Expected behavior and transactions
- Note: This informs probe configuration

══════════════════════════════════════════════════════════════════════════
STEP 3: GENERATE PROBE CONFIGURATION
══════════════════════════════════════════════════════════════════════════
- Create probe JSON config matching DUT {protocol.upper()} settings
- Use RECOMMENDED PROBE PINS (unless {probe_pins}):
  * I2C: SCL=22, SDA=21
  * UART: Channel A RX=16, Channel B RX=17
  * SPI: CLK=18, MOSI=23, MISO=19, CS=5
  * PWM: GPIO=4
  * RMT: GPIO=25 (for IR/WS2812)
  * GPIO: 32,33,34,35 (input-only pins)
  * ADC: 34,35,36 (up to 8 channels)

- CRITICAL CONSTRAINTS:
  * NO GPIO 6-11 (flash pins cause boot loops!)
  * Each GPIO used only ONCE across all probes
  * Input-only pins (32-39): NO pull_up/pull_down
  * For I2C: clock ≤10kHz for reliable probe capture

- Config template for {protocol.upper()}:
  {_get_probe_config_template(protocol)}

- Save as: {project_path}/probe_config.json
- Use flash_probe_config("{project_path}/probe_config.json")

══════════════════════════════════════════════════════════════════════════
STEP 4: SETUP HARDWARE CONNECTIONS
══════════════════════════════════════════════════════════════════════════
- Generate WIRING DIAGRAM showing:
  * DUT GPIO X → Probe GPIO Y (for each signal)
  * Example: "DUT SCL (GPIO22) → Probe SCL (GPIO22)"
  * Example: "DUT TX (GPIO17) → Probe RX (GPIO16)"
  * ALWAYS: Common GND connection

- WAIT for user confirmation that wiring is complete
- User must verify all connections before proceeding

══════════════════════════════════════════════════════════════════════════
STEP 5: CONNECT DEVICES
══════════════════════════════════════════════════════════════════════════
- Use list_serial_ports() to show available ports
- ASK USER to identify which port is DUT and which is Probe
- Connect both: connect(dut_port="<user_specified>", probe_port="<user_specified>")
- Verify connection succeeds for both devices

══════════════════════════════════════════════════════════════════════════
STEP 6: FLASH DUT FIRMWARE  
══════════════════════════════════════════════════════════════════════════
- Flash firmware to DUT: flash_firmware("{project_path}")
- Confirm flash succeeds
- DUT will auto-reset after flashing

══════════════════════════════════════════════════════════════════════════
STEP 7: START DATA CAPTURE
══════════════════════════════════════════════════════════════════════════
- Start DUT monitor: start_serial_monitor("dut")
- Start Probe monitor: start_serial_monitor("probe") 
- Data accumulation begins NOW - all subsequent activity is captured

══════════════════════════════════════════════════════════════════════════
STEP 8: RESET AND RUN
══════════════════════════════════════════════════════════════════════════
- Reset DUT: reset_device("dut")
- Reset Probe: reset_device("probe")
- Wait 10-30 seconds for firmware to execute {protocol.upper()} transactions

══════════════════════════════════════════════════════════════════════════
STEP 9: GENERATE MERGED LOG
══════════════════════════════════════════════════════════════════════════
- Create merged log: generate_merged_log(output_file="{project_path}/merged.txt")
- This merges COMPLETE capture history:
  * DUT logs (application behavior)
  * Probe logs ({protocol.upper()} protocol transactions)
  * Chronologically ordered with microsecond timestamps
- Tool returns exact path where file was created

══════════════════════════════════════════════════════════════════════════
STEP 10: ANALYZE {protocol.upper().replace('_', ' ')} COMMUNICATION
══════════════════════════════════════════════════════════════════════════
- IMPORTANT: Probe works 100% correctly - trust probe logs as source of truth
- IMPORTANT: Assume hardware is properly connected
- Read {project_path}/merged.txt

**Merged Log Format:**
- Format: [timestamp_us] <SOURCE> <content>
- DUT lines: Application logs (sensor readings, calculations)
- PROBE lines: Protocol transactions (see formats below)
- Chronologically ordered for easy correlation

**Probe Log Formats:**
- I2C: "I2C READ/WRITE 0xADDR [DATA]" - Bus transactions
- UART: "UART A/B \\"TEXT\\" [HEX]" - Channel label, escaped text, hex bytes
- PWM: "PWM freq=X duty=Y width=Z period=W" - Signal characteristics
- SPI: "SPI [HEX]" - SPI transactions
- ADC: "ADC GPIOX val=Y" - Analog readings
- RMT: "RMT n=X res=YHz [symbols]" - IR/pulse data
- GPIO: "GPIO pin=level" - Digital state changes

**Example Analysis (I2C):**
```
[972225000] MASTER MAIN    Init sensor at 0x5A
[972225100] PROBE  I2C WRITE 0x5A [A0,01]  ← Write to config register
[972228000] MASTER MAIN    Reading temperature
[972228100] PROBE  I2C WRITE 0x5A [03]     ← Write register address
[972228500] PROBE  I2C READ  0x5A [18,09]  ← Read temperature data
[972229000] MASTER MAIN    Temperature: 23.5°C
```

**Example Analysis (UART):**
```
[1000000] MASTER MAIN    Querying module
[1000480] PROBE  UART A "AT+EVENT?\\n" [41,54,2B,45,56,45,4E,54,3F,0A]
[1000620] PROBE  UART B "OK\\r\\n" [4F,4B,0D,0A]
```

**Example Analysis (PWM):**
```
[500000] MASTER MAIN    Starting PWM at 1kHz, 50% duty
[500120] PROBE  PWM   freq=1000.00 duty=50.00 width=500 period=1000
[510000] MASTER MAIN    Adjusting duty to 75%
[510080] PROBE  PWM   freq=1000.00 duty=75.00 width=750 period=1000
```

**Example Analysis (GPIO):**
```
[200000] MASTER MAIN    Button pressed
[200015] PROBE  GPIO  5=0  ← Button pin went low
[205000] MASTER MAIN    Button released
[205012] PROBE  GPIO  5=1  ← Button pin went high
```

**Verification Checklist:**
✓ Protocol Compliance: Do transactions match sensor/device datasheet?
✓ Initialization: Is the init sequence correct?
✓ Addresses/Registers/Commands: Are correct targets accessed?
✓ Data Integrity: Are read/written values reasonable?
✓ Transaction Pairing: Does each command have expected response?
✓ No Spurious Traffic: Any unexpected transactions?
✓ Timing: Is timing appropriate for configured bus speed?

**Success Criteria:**
✓ All DUT operations have corresponding PROBE transactions
✓ Register addresses match datasheet specifications
✓ Data values are reasonable for sensor type
✓ Initialization follows datasheet sequence
✓ No communication errors or retries
✓ Timing is consistent with clock speed

══════════════════════════════════════════════════════════════════════════
STEP 11: TROUBLESHOOTING ISSUES
══════════════════════════════════════════════════════════════════════════

**No Probe Data in Merged Log:**

I2C (format: +<us> <R/W> 0x<ADDR> [<DATA>]):
- Check: Probe connected to I2C bus with 1-2kΩ resistors
- Verify: Pull-up resistors present on I2C lines
- Confirm: I2C clock speed ≤10kHz for reliable capture

UART (format: @<us> <A|B> "<TEXT>" [<HEX>]):
- Check: TX↔RX crossed and common GND between devices
- Verify: Correct baud rate configured on both ends
- Confirm: Probe RX pin wiring to DUT TX pin

PWM (format: ~<us> PWM freq=X duty=Y ...):
- Check: PWM signal connected to probe input pin
- Verify: Common GND between DUT and probe
- Confirm: Signal voltage within probe input range (0-3.3V)

SPI (format: *<us> SPI: [<HEX>]):
- Check: All SPI lines (CLK, MOSI, MISO, CS) connected
- Verify: Common GND and correct pin assignments
- Confirm: CS line properly triggering transactions

ADC (format: ^<us> ADC: GPIO<n> val=<value>):
- Check: ADC input connected (voltage divider if >3.3V needed)
- Verify: Signal voltage within ADC range (0-3.3V)
- Confirm: Correct GPIO pin and attenuation setting

RMT (format: &<us> RMT: n=X res=YHz ...):
- Check: RMT signal connected to probe input
- Verify: Signal timing within configured min/max range
- Confirm: Resolution appropriate for pulse widths

GPIO (format: #<us> GPIO: <pin>=<level>):
- Check: GPIO pin connected and common GND
- Verify: Pin configured as input on probe
- Confirm: Signal transitions occurring (not static)

**DUT Shows Operations But No PROBE Capture:**
- Issue: Protocol communication failing or wiring problem
- Check: Device addresses, baud rates, clock speeds match expectations
- Verify: Correct pin connections per wiring diagram
- Confirm: Device power, pull-ups/pull-downs as needed

**Wrong Data Values:**
- Check: Register addresses (refer to datasheet)
- Verify: Data endianness (MSB/LSB order)
- Confirm: CRC or checksum calculations if applicable
- Review: Timing requirements and delays

**DUT Crashes:**
- Fix code, rebuild using idf-builder, reflash, re-test
- Check: Error handling, buffer sizes, timeouts
- Review: Crash logs for root cause
- Verify: Stack sizes and memory allocation

**Recovery from Midpoint:**
If resuming testing from an intermediate step:
- Verify earlier steps were completed
- If not, rewind to earliest missing step
- Reconstruct missing context or ask for gaps
- State: "Resuming from Step X, but rewinding to Step Y to recover context"

**Fallback Rules:**
- Tool Unavailable → State limitation, provide manual commands
- Hardware Unavailable → Simulate expected behavior, mark [SIMULATED]
- File Missing/Corrupt → Request re-upload, attempt partial reconstruction
- Conflicting Instructions → Prioritize workflow integrity, flag in Report

══════════════════════════════════════════════════════════════════════════
STEP 12: REPORT RESULTS
══════════════════════════════════════════════════════════════════════════
Provide comprehensive test report with:

**Sensor/Device:**
- Name, bus address/identifier (e.g., I2C address 0x5A)
- Protocol version or firmware version if applicable

**Pin Configuration:**
- Pins used (DUT and Probe)
- Clock/baud rates configured

**Test Statistics:**
- Total probe events captured across all protocols
- DUT events logged
- Protocol breakdown:
  * I2C transactions (if applicable)
  * UART messages (if applicable)
  * PWM events (if applicable)
  * SPI transactions (if applicable)
  * ADC samples (if applicable)
  * RMT events (if applicable)
  * GPIO changes (if applicable)

**Verification Results:**
- Protocol compliance: ✓/✗ (matches datasheet?)
- Data integrity: ✓/✗ (values reasonable?)
- Initialization sequence: ✓/✗ (follows datasheet?)
- All features tested: ✓/✗

**Issues Found:**
- List any protocol violations
- Timing issues
- Data errors
- Communication failures

**Merged Log Path:**
- Full path to merged.txt for reference (e.g., {project_path}/merged.txt)

**Confidence Score:**
- 0.0-1.0 score on firmware reliability
- Justify the score based on verification results

**Recommendations:**
- Any hardware considerations
- Timing adjustments needed
- Code improvements suggested
- Next steps for development

══════════════════════════════════════════════════════════════════════════
STEP 13: DISCONNECT AND CLEANUP
══════════════════════════════════════════════════════════════════════════
- Disconnect DUT: disconnect("dut")
- Disconnect Probe: disconnect("probe")
- Merged log is saved in project directory for documentation

══════════════════════════════════════════════════════════════════════════
CRITICAL REMINDERS & RULES
══════════════════════════════════════════════════════════════════════════

**Probe Accuracy:**
- Probe logs are 100% accurate - trust them as source of truth
- If probe shows transactions, they actually happened on the bus
- If probe shows nothing, check wiring and configuration first

**Build Failure Strategy:**
If build fails at any point:
- Identify specific error from build logs
- Fix issue incrementally (don't make multiple changes at once)
- NEVER proceed with testing if build fails
- Document the fix applied in the Report step

**Protocol Constraints:**
- I2C: MUST use ≤10kHz clock for reliable probe capture
- GPIO 6-11: NEVER use (flash pins cause boot loops)
- Input-only pins (32-39): NO pull_up/pull_down allowed
- Each GPIO: Use only ONCE across all probes

**Quick Reference Tool Call Sequence:**
1. build_project() or skip if built
2. Analyze DUT firmware
3. flash_probe_config()
4. Provide wiring, wait for user confirmation
5. list_serial_ports() - ask user which port is which
6. connect(dut_port, probe_port)
7. flash_firmware(project_dir)
8. start_serial_monitor("dut")
9. start_serial_monitor("probe")
10. reset_device("dut")
11. reset_device("probe")
12. Wait 10-30 seconds
13. generate_merged_log(output_file="/absolute/path/merged.txt")
14. Read and analyze merged.txt
15. Report results with statistics and confidence score
16. disconnect("dut") and disconnect("probe")
"""

def _get_probe_config_template(protocol: str) -> str:
    """Get probe config template for specific protocol."""
    templates = {
        "i2c": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "I2C", "enable": true, "scl_gpio": 22, "sda_gpio": 21, 
      "glitch_filter_ns": 200, "queue_len": 4096}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "uart": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "UART", "enable": true, "channels": [
      {{"label": "A", "uart": 1, "rx_gpio": 16, "baud": 115200, "enable": true}}
    ], "interbyte_timeout_ms": 20, "max_msg_bytes": 256}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "uart_dual": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "UART", "enable": true, "channels": [
      {{"label": "A", "uart": 1, "rx_gpio": 16, "baud": 115200, "enable": true}},
      {{"label": "B", "uart": 2, "rx_gpio": 17, "baud": 9600, "enable": true}}
    ], "interbyte_timeout_ms": 20, "max_msg_bytes": 256}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "multi_i2c_uart": '''{{
  "version": 1,
  "device": {{"name": "i2c-uart-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "UART", "enable": true, "channels": [
      {{"label": "A", "uart": 1, "rx_gpio": 16, "baud": 115200, "enable": true}}
    ], "interbyte_timeout_ms": 20, "max_msg_bytes": 256}},
    {{"type": "I2C", "enable": true, "scl_gpio": 22, "sda_gpio": 21, 
      "glitch_filter_ns": 200, "queue_len": 4096}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "spi": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "SPI", "enable": true, "clk_gpio": 18, "mosi_gpio": 23,
      "miso_gpio": 19, "cs_gpio": 5, "mode": 0, "max_bytes": 64}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "pwm": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "PWM", "enable": true, "gpio": 4, "capture_clk_hz": 80000000,
      "freq_change_x100": 50, "duty_change_x100": 100}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "gpio": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "GPIO", "enable": true, "pins": [32, 33, 34, 35],
      "pull_up": false, "pull_down": false, "debounce_ms": 2}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "adc": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "ADC", "enable": true, "channels": [34, 35, 36],
      "sample_rate_hz": 100, "atten": 3}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}''',
        "rmt": '''{{
  "version": 1,
  "device": {{"name": "test-probe", "board": "esp32", "log": {{"baud": 115200}}}},
  "probes": [
    {{"type": "RMT", "enable": true, "gpio": 25, "resolution_hz": 10000000,
      "min_ns": 100, "max_ns": 100000, "mem_symbols": 256, "buf_symbols": 512}}
  ],
  "output": {{"prefix_protocol": true, "timestamps": "us", "hex_upper": true}}
}}'''
    }
    return templates.get(protocol.lower(), "# See documentation for config template")

def _get_probe_log_format(protocol: str) -> str:
    """Get expected probe log format for protocol."""
    formats = {
        "i2c": "  [timestamp_us] PROBE  I2C WRITE 0x5A [A0,01]  ← Write config\n  [timestamp_us] PROBE  I2C READ  0x5A [18,09]  ← Read data",
        "uart": "  [timestamp_us] PROBE  UART A \"AT+CMD\\n\" [41,54,2B,43,4D,44,0A]",
        "spi": "  [timestamp_us] PROBE  SPI: [01,02,03,04]",
        "pwm": "  [timestamp_us] PROBE  PWM freq=1000.00 duty=50.00 width=500 period=1000",
        "gpio": "  [timestamp_us] PROBE  GPIO 5=0  ← Pin went low",
        "adc": "  [timestamp_us] PROBE  ADC GPIO34 val=2048",
        "rmt": "  [timestamp_us] PROBE  RMT n=10 res=10000000Hz [...]"
    }
    return formats.get(protocol.lower(), "  [timestamp_us] PROBE  <protocol data>")

@mcp.prompt()
def flash_and_monitor(project_path: str, skip_build: bool = False) -> str:
    """Quick workflow: flash firmware and monitor serial output (no probe).
    
    Args:
        project_path: Path to ESP-IDF project
        skip_build: Skip build if firmware already built
    """
    return f"""Execute quick flash and monitor workflow (NO PROBE):

PROJECT: {project_path}

WORKFLOW:

1. {'**Skip Build**' if skip_build else '**Build Firmware**'}
   {f'- Using existing build' if skip_build else f'- build_project("{project_path}")'}
   {'' if skip_build else '- STOP if build fails'}

2. **List Ports**
   - list_serial_ports()
   - Identify DUT port

3. **Connect**
   - connect(dut_port="<user_specified>", probe_port=None)

4. **Flash**
   - flash_firmware("{project_path}")
   - Confirm success

5. **Monitor**
   - start_serial_monitor("dut")
   - reset_device("dut")
   - Observe output for 30 seconds

6. **Summarize**
   - Report device behavior
   - Note any errors or unexpected output
   - Provide recommendations

7. **Cleanup**
   - disconnect("dut")
"""

@mcp.prompt()
def analyze_protocol_logs(
    merged_log_path: str,
    protocol: str = "i2c",
    expected_behavior: str = ""
) -> str:
    """Analyze existing merged protocol logs for verification.
    
    Args:
        merged_log_path: Path to merged.txt file
        protocol: Protocol type (i2c, uart, spi, pwm, etc.)
        expected_behavior: Description of expected behavior
    """
    return f"""Analyze protocol communication log:

LOG FILE: {merged_log_path}
PROTOCOL: {protocol.upper()}
EXPECTED: {expected_behavior if expected_behavior else 'Correct protocol operation'}

ANALYSIS CHECKLIST:

1. **Read Log File**
   - Read {merged_log_path}
   - Identify DUT and PROBE lines
   - Note timestamp ranges

2. **Protocol Compliance**
   - Do {protocol.upper()} transactions follow specification?
   - Are addresses/commands correct?
   - Proper transaction formatting?

3. **Data Integrity**
   - Are data values reasonable?
   - Correct byte ordering?
   - Valid register addresses?
   - Expected data ranges?

4. **Timing Analysis**
   - Appropriate for configured speed?
   - No unexpected delays?
   - Consistent transaction timing?

5. **Error Detection**
   - Any NACKs or errors?
   - Unexpected transactions?
   - Missing expected operations?
   - Retry attempts?

6. **DUT-Probe Correlation**
   - Do DUT logs match probe transactions?
   - All DUT operations have probe evidence?
   - Timing alignment between logs?

7. **Provide Report**
   - Detailed findings for each category
   - List any issues discovered
   - Confidence score (0.0-1.0)
   - Recommendations for fixes

REMEMBER: Probe logs are the source of truth - they show what actually happened on the bus.
"""

@mcp.prompt()
def generate_probe_config_only(
    project_path: str,
    protocols: str = "i2c"
) -> str:
    """Generate and flash probe configuration (no testing).
    
    Args:
        project_path: Path to DUT firmware project
        protocols: Comma-separated protocols (i2c,uart,spi,pwm,gpio,adc,rmt)
    """
    protocol_list = [p.strip().lower() for p in protocols.split(',')]
    
    return f"""Generate probe configuration for monitoring:

DUT PROJECT: {project_path}
PROTOCOLS: {protocols.upper()}

WORKFLOW:

1. **Analyze DUT Firmware**
   - Read firmware in {project_path}/main/
   - For each protocol ({', '.join(protocol_list)}):
     * Identify GPIO pins used
     * Note communication parameters
     * Understand expected behavior

2. **Generate Probe JSON**
   - Create multi-protocol config if needed
   - Use recommended probe pins:
     * I2C: SCL=22, SDA=21
     * UART: RX=16 (ChA), RX=17 (ChB)
     * SPI: CLK=18, MOSI=23, MISO=19, CS=5  
     * PWM: GPIO=4
     * GPIO: 32,33,34,35
     * ADC: 34,35,36
     * RMT: GPIO=25

   - CONSTRAINTS:
     * NO GPIO 6-11 (flash pins!)
     * Each GPIO used ONCE
     * Input-only pins (32-39): NO pulls
     * I2C clock ≤10kHz

3. **Flash Configuration**
   - Save as {project_path}/probe_config.json
   - flash_probe_config("{project_path}/probe_config.json")
   - Verify flash succeeds

4. **Provide Wiring Diagram**
   - Show DUT pin X → Probe pin Y for each signal
   - Include common GND connection
   - Document any special requirements

RESULT: Probe is configured and ready for testing
"""

async def main():
    """Main entry point."""
    # Print available tools
    tools = await mcp.get_tools()
    tools_data = [{"name": t.name, "description": t.description} for t in tools.values()]
    output.print("Registered Tools:", color="green")
    output.output(tools_data)

    # Start the server using stdio transport
    output.info("Starting MCP server using stdio transport")
    await mcp.run_stdio_async()


def cleanup_on_exit():
    """Clean up resources when the server shuts down."""
    device_manager.clear_all()

if __name__ == "__main__":
    import asyncio
    import atexit

    # Register cleanup function
    atexit.register(cleanup_on_exit)

    asyncio.run(main())
