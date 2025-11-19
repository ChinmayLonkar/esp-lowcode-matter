#!/usr/bin/env python3
"""
Device Test MCP client.
This client provides an interactive interface for testing ESP32 devices through serial monitoring
and automated test execution.
"""

import os
import sys
import json
import logging
import argparse
import asyncio
import time
import shlex
import readline
from typing import Dict, List, Any, Optional

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
from mcp_tools.components.path_setup import setup_path
setup_path()

# Import MCP client
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat

def parse_tool_result(result):
    """Parse tool call result from FastMCP client."""
    if not result:
        return {}
    
    # Handle different result structures
    if hasattr(result, 'content'):
        # New FastMCP structure
        if isinstance(result.content, list) and len(result.content) > 0:
            content_item = result.content[0]
            if hasattr(content_item, 'text'):
                return json.loads(content_item.text)
        elif hasattr(result.content, 'text'):
            return json.loads(result.content.text)
    elif hasattr(result, 'text'):
        # Direct text attribute
        return json.loads(result.text)
    elif isinstance(result, list) and len(result) > 0:
        # Old structure - list with text
        if hasattr(result[0], 'text'):
            return parse_tool_result(result)
    
    # Fallback - try to convert directly
    try:
        return json.loads(str(result))
    except:
        return {}


def parse_device_role(parts, default_role="dut"):
    """Parse device role from command parts.
    
    Returns:
        tuple: (device_role_str, remaining_parts)
    """
    # Check if any part contains --dut or --tester
    role = default_role
    filtered_parts = []
    
    for part in parts:
        if part.lower() in ["--dut", "-d"]:
            role = "dut"
        elif part.lower() in ["--tester", "-t"]:
            role = "tester"
        else:
            filtered_parts.append(part)
    
    return role, filtered_parts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "client.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Parse command line arguments
parser = argparse.ArgumentParser(description="Device Test Client")
parser.add_argument(
    "--format",
    choices=["text", "json", "csv", "table"],
    default="text",
    help="Output format"
)
parser.add_argument(
    "--server",
    default="subprocess",
    choices=["subprocess", "http"],
    help="Server connection type"
)
parser.add_argument(
    "--color",
    action="store_true",
    default=True,
    help="Enable colored output"
)
args = parser.parse_args()

# Initialize output manager with selected format
output = get_output_manager(format=args.format, color=args.color)


def print_help():
    """Print available commands."""
    output.print("Available commands:", color="cyan")
    output.print("")
    output.print("Device Role Options:", color="magenta")
    output.print("  Most commands support --dut or --tester flags to target specific devices")
    output.print("  --dut or -d: Target the Device Under Test (default)")
    output.print("  --tester or -t: Target the Tester device")
    output.print("")
    output.print("Serial Port Management:", color="yellow")
    output.print("  list_ports - List available serial ports")
    output.print("  connect PORT [BAUDRATE] [--dut|--tester] - Connect to serial port")
    output.print("  disconnect [--dut|--tester] - Disconnect from serial port")
    output.print("  reset [--dut|--tester] - Reset the connected device")
    output.print("")
    output.print("Serial Monitoring:", color="yellow")
    output.print("  start_monitor [--no-reset] [--dut|--tester] - Start monitoring serial data")
    output.print("  stop_monitor [--dut|--tester] - Stop monitoring serial data")
    output.print("  get_data [SECONDS] [--dut|--tester] - Get recent serial data")
    output.print("  get_stats [--dut|--tester] - Get serial monitoring statistics")
    output.print("")
    output.print("Debugging & Diagnostics:", color="yellow")
    output.print("  monitor_status [--dut|--tester] - Get detailed monitoring status")
    output.print("  add_test_data \"LINE1\" [\"LINE2\" ...] [--dut|--tester] - Add test data")
    output.print("  test_search \"PATTERN\" [TIMEOUT] - Test search functionality")
    output.print("  check_immediate_data [SECONDS] [--dut|--tester] - Check for data reception")
    output.print("  clear_log_buffer [--dut|--tester] - Clear the log buffer")
    output.print("")
    output.print("Step-Based Testing:", color="yellow")
    output.print("  run_test - Create and run step-based test sequence")
    output.print("  test_log \"PATTERN\" [TIMEOUT] [\"DESCRIPTION\"] - Quick log pattern test")
    output.print("  test_gpio PIN VALUE [TIMEOUT] - Quick GPIO test")
    output.print("")
    output.print("GPIO Testing:", color="yellow")
    output.print("  gpio_set PIN VALUE [TIMEOUT] - Set GPIO pin to value via tester")
    output.print("  gpio_expect PIN VALUE [TIMEOUT] - Expect GPIO pin to have value via tester")
    output.print("")
    output.print("I2C Testing:", color="yellow")
    output.print("  i2c_master_write ADDR REG DATA [TIMEOUT] - Write data to I2C device as master")
    output.print("  i2c_master_read ADDR REG [TIMEOUT] - Read data from I2C device as master")
    output.print("  i2c_slave_write ADDR REG DATA [TIMEOUT] - Act as I2C slave, expect write operation")
    output.print("  i2c_slave_read ADDR REG DATA [TIMEOUT] - Act as I2C slave, respond when master reads, send data")
    output.print("  test_i2c COMMAND - Quick I2C test using step-based testing")
    output.print("")
    output.print("Test Steps (for run_test):", color="yellow")
    output.print("  reset [wait_seconds] - Reset ESP32 device, optionally wait specified seconds")
    output.print("  delay seconds - Wait for specified number of seconds")
    output.print("  flash project_dir - Flash firmware from project directory")
    output.print("  search log \"pattern\" [timeout] - Search for log pattern (use quotes for patterns with spaces)")
    output.print("  wait log \"pattern\" [timeout] - Alias for search log (use quotes for patterns with spaces)")
    output.print("  gpio set pin value [timeout] - Set GPIO pin to value via tester")
    output.print("  gpio expect pin value [timeout] - Expect GPIO pin to have value via tester")
    output.print("  i2c write addr data [role] - I2C write operation (addr in hex, data: reg:0xXX,data:0xYY or just 0xYY)")
    output.print("  i2c read addr [reg] [role] - I2C read operation (addr and reg in hex)")
    output.print("")
    output.print("Step Examples:", color="yellow")
    output.print("  reset 2")
    output.print("  delay 1.5")
    output.print("  flash ./my_project")
    output.print("  search log \"ESP32 ready\"")
    output.print("  search log \"factory_reset: Reboot count: 1\" 15")
    output.print("  wait log \".*WiFi.*\" 30")
    output.print("  gpio set 2 1 5      # Set GPIO pin 2 to HIGH with 5s timeout")
    output.print("  gpio expect 18 0 1  # Expect GPIO pin 18 to be LOW with 1s timeout")
    output.print("  i2c write 0x77 reg:0x12,data:0x34  # Master write to device 0x77")
    output.print("  i2c read 0x77 0x12  # Master read from device 0x77, register 0x12")
    output.print("  i2c write 0x77 reg:0x12,data:0x34 slave  # Slave mode: expect write")
    output.print("  i2c read 0x77 reg:0x12,data:0xAB slave   # Slave mode: respond when master reads, send 0xAB")
    output.print("")
    output.print("Debugging Examples:", color="yellow")
    output.print("  monitor_status")
    output.print("  add_test_data \"ESP32 starting up\" \"System ready\"")
    output.print("  test_search \"ready\" 5")
    output.print("  check_immediate_data 2.0")
    output.print("  clear_log_buffer")
    output.print("")
    output.print("Examples:", color="yellow")
    output.print("  example_workflow - Run example ESP32 testing workflow")
    output.print("  flash ./my_project - Flash firmware from project directory")
    output.print("  gpio_set 2 1 10 - Set GPIO pin 2 to HIGH with 10s timeout")
    output.print("  gpio_expect 18 0 5 - Expect GPIO pin 18 to be LOW with 5s timeout")
    output.print("  test_gpio 2 1 - Quick test: expect GPIO pin 2 to be HIGH")
    output.print("  i2c_master_write 0x77 0x12 0x34 - Master write 0x34 to reg 0x12 of device 0x77")
    output.print("  i2c_master_read 0x77 0x12 - Master read from reg 0x12 of device 0x77")
    output.print("  i2c_slave_write 0x77 0x12 0x34 - Slave mode: expect write of 0x34 to reg 0x12")
    output.print("  i2c_slave_read 0x77 0x12 0xAB - Slave mode: respond when master reads reg 0x12, send 0xAB")
    output.print("")
    output.print("Dual-Device Examples:", color="yellow")
    output.print("  connect /dev/ttyUSB0 --dut - Connect DUT device")
    output.print("  connect /dev/ttyUSB1 --tester - Connect tester device")
    output.print("  start_monitor --dut - Start monitoring DUT")
    output.print("  start_monitor --tester - Start monitoring tester")
    output.print("  get_data 5 --dut - Get 5 seconds of DUT data")
    output.print("  reset --tester - Reset tester device")
    output.print("")
    output.print("Firmware Management:", color="yellow")
    output.print("  flash PROJECT_DIR - Flash firmware from project directory")
    output.print("")
    output.print("General:", color="yellow")
    output.print("  history [TOOL_NAME] - Get local tool call history (client-side only)")
    output.print("  help - Show this help")
    output.print("  exit/quit - Exit the client")


async def run_example_workflow(client):
    """Run an example workflow for ESP32 device testing."""
    output.print("Running Example ESP32 Testing Workflow", color="green")
    output.print("=" * 50, color="green")

    try:
        # Step 1: List available ports
        output.print("Step 1: Listing available serial ports...", color="cyan")
        result = await client.call_tool("list_serial_ports", {})
        ports = parse_tool_result(result)

        if not ports:
            output.warning("No serial ports found. Please connect an ESP32 device.")
            return

        output.print("Available ports:", color="blue")
        for i, port in enumerate(ports):
            output.print(f"  {i+1}. {port['device']} - {port['description']}")

        # For demo purposes, use the first port
        selected_port = ports[0]['device']
        output.print(f"Using port: {selected_port}", color="green")

        # Step 2: Connect to the port
        output.print("Step 2: Connecting to serial port...", color="cyan")
        result = await client.call_tool("connect", {
            "port": selected_port,
            "baudrate": 115200,
            "device_role": "dut"
        })
        connection_result = parse_tool_result(result)

        if not connection_result.get("success"):
            output.error(f"Failed to connect: {connection_result.get('error', 'Unknown error')}")
            return

        output.success("Connected successfully!")

        # Step 3: Start monitoring
        output.print("Step 3: Starting serial monitor...", color="cyan")
        result = await client.call_tool("start_serial_monitor", {
            "device_role": "dut"
        })
        monitor_result = parse_tool_result(result)

        if monitor_result.get("success"):
            output.success("Serial monitoring started!")

            # Wait a bit for data to accumulate
            output.print("Waiting 5 seconds for data to accumulate...", color="yellow")
            await asyncio.sleep(5)

            # Step 4: Get some data
            output.print("Step 4: Getting recent serial data...", color="cyan")
            result = await client.call_tool("get_serial_data", {
                "seconds": 10.0,
                "device_role": "dut"
            })
            data_result = parse_tool_result(result)

            if data_result.get("success"):
                data = data_result.get("data", [])
                output.print(f"Captured {len(data)} lines of data:", color="blue")
                for line in data[-5:]:  # Show last 5 lines
                    output.print(f"  {line}")

            # Step 5: Run example command-based tests
            output.print("Step 5: Running example step-based tests...", color="cyan")
            example_steps = [
                "reset 2",  # Reset and wait 2 seconds
                "delay 1",  # Wait 1 second
                "search log .*"  # Search for any log output
                # Note: GPIO and I2C tests require a connected tester device
                # "gpio set 2 1 5",    # Set GPIO pin 2 HIGH (requires tester)
                # "gpio expect 2 1 3"  # Expect GPIO pin 2 to be HIGH (requires tester)
                # "i2c write 0x77 reg:0x12,data:0x34",  # I2C master write (requires tester)
                # "i2c read 0x77 0x12",                 # I2C master read (requires tester)
            ]

            result = await client.call_tool("execute_tests", {"steps": example_steps})
            test_result = parse_tool_result(result)

            if test_result.get("success"):
                output.success(f"Step tests completed: {test_result.get('passed_steps', 0)}/{test_result.get('total_steps', 0)} passed")

                # Show step results
                for result_detail in test_result.get("results", []):
                    status = "✓" if result_detail.get("success") else "✗"
                    output.print(f"  {status} {result_detail.get('description', 'Step')}")
            else:
                output.warning("Step tests failed or had issues")

            # Step 6: Stop monitoring
            output.print("Step 6: Stopping serial monitor...", color="cyan")
            await client.call_tool("stop_serial_monitor", {
                "device_role": "dut"
            })

        # Step 7: Disconnect
        output.print("Step 7: Disconnecting...", color="cyan")
        await client.call_tool("disconnect", {
            "device_role": "dut"
        })
        output.success("Workflow completed!")

    except Exception as e:
        output.error(f"Workflow failed: {str(e)}")


async def interactive_loop():
    """Run an interactive loop for the client."""
    # Configure readline for better command line editing
    try:
        # Enable history file
        history_file = os.path.expanduser("~/.device_test_client_history")
        if os.path.exists(history_file):
            readline.read_history_file(history_file)
        readline.set_history_length(1000)
        
        # Set up tab completion (basic)
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set editing-mode emacs")
        
    except Exception as e:
        # If readline setup fails, continue without it
        logger.warning(f"Failed to configure readline: {e}")
    
    output.print("Device Test Client - ESP32 Testing Tool", color="green")
    output.print("Type 'help' for available commands or 'exit' to quit", color="green")
    print_help()

    # Create transport and client
    script_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(script_dir, "server.py")

    # Create the transport
    transport = PythonStdioTransport(
        script_path=server_path,
        python_cmd="python3"
    )

    # Use client as an async context manager
    async with Client(transport) as client:
        # List available tools
        tools = await client.list_tools()
        
        # # Display tools in a structured format
        # output.print("Available MCP Tools:", color="blue")
        # output.print("=" * 100, color="blue")
        
        # if tools:
        #     for i, tool in enumerate(tools, 1):
        #         # Extract tool information
        #         name = getattr(tool, 'name', 'Unknown')
        #         description = getattr(tool, 'description', 'No description available')
                
        #         # Format tool header
        #         output.print(f"{i:2d}. {name}", color="cyan")
        #         output.print(f"    Description: {description}", color="white")
                
        #         # Show input schema if available
        #         if hasattr(tool, 'inputSchema') and tool.inputSchema:
        #             schema = tool.inputSchema
        #             if hasattr(schema, 'properties') and schema.properties:
        #                 output.print("    Parameters:", color="yellow")
        #                 for param_name, param_info in schema.properties.items():
        #                     param_type = getattr(param_info, 'type', 'unknown')
        #                     param_desc = getattr(param_info, 'description', 'No description')
        #                     required = param_name in getattr(schema, 'required', [])
        #                     req_marker = " *" if required else ""
        #                     output.print(f"      - {param_name} ({param_type}){req_marker}: {param_desc}", color="gray")
                
        #         output.print("")  # Empty line between tools
            
        #     output.print("=" * 100, color="blue")
        #     output.info(f"Total: {len(tools)} tools available")
        #     output.print("* = Required parameter", color="yellow")
        # else:
        #     output.warning("No tools available")
        while True:
            try:
                # Get user input
                user_input = input("\nDevice-Test> ").strip()

                # Check for exit command
                if user_input.lower() in ["exit", "quit"]:
                    output.print("Exiting...", color="yellow")
                    # Save command history
                    try:
                        history_file = os.path.expanduser("~/.device_test_client_history")
                        readline.write_history_file(history_file)
                    except Exception as e:
                        logger.warning(f"Failed to save command history: {e}")
                    break

                # Process commands using shlex to handle quoted strings properly
                try:
                    parts = shlex.split(user_input)
                except ValueError as e:
                    output.error(f"Invalid command syntax: {e}")
                    continue

                command = parts[0].lower() if parts else ""

                if command == "help":
                    print_help()

                elif command == "list_ports":
                    output.info("Listing available serial ports...")
                    result = await client.call_tool("list_serial_ports", {})
                    ports = parse_tool_result(result)

                    if ports:
                        output.print("Available serial ports:", color="blue")
                        for i, port in enumerate(ports):
                            output.print(f"  {i+1}. {port['device']} - {port['description']} ({port['manufacturer']})")
                    else:
                        output.warning("No serial ports found")

                elif command == "connect":
                    device_role, filtered_parts = parse_device_role(parts[1:])
                    
                    if len(filtered_parts) < 1:
                        output.error("Missing port parameter. Usage: connect PORT [BAUDRATE] [--dut|--tester]")
                        continue

                    port = filtered_parts[0]
                    baudrate = int(filtered_parts[1]) if len(filtered_parts) > 1 else 115200

                    output.info(f"Connecting to {port} at {baudrate} baud ({device_role.upper()})...")
                    result = await client.call_tool("connect", {
                        "port": port,
                        "baudrate": baudrate,
                        "device_role": device_role
                    })
                    connection_result = parse_tool_result(result)

                    if connection_result.get("success"):
                        output.success(f"Connected {device_role.upper()} to {port}")
                    else:
                        output.error(f"Connection failed: {connection_result.get('error', 'Unknown error')}")

                elif command == "disconnect":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Disconnecting from {device_role.upper()} serial port...")
                    result = await client.call_tool("disconnect", {
                        "device_role": device_role
                    })
                    disconnect_result = parse_tool_result(result)

                    if disconnect_result.get("success"):
                        output.success(f"Disconnected {device_role.upper()} successfully")
                    else:
                        output.warning(f"No active {device_role.upper()} connection to disconnect")

                elif command == "reset":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Resetting {device_role.upper()} device...")
                    result = await client.call_tool("reset_device", {
                        "device_role": device_role
                    })
                    reset_result = parse_tool_result(result)

                    if reset_result.get("success"):
                        output.success(f"{device_role.upper()} reset completed successfully")
                    else:
                        output.error(f"Reset failed: {reset_result.get('error', 'Unknown error')}")

                elif command == "start_monitor":
                    # Check for --no-reset flag and device role
                    auto_reset = True
                    filtered_parts = []
                    for part in parts[1:]:
                        if part == "--no-reset":
                            auto_reset = False
                        else:
                            filtered_parts.append(part)
                    
                    device_role, _ = parse_device_role(filtered_parts)
                    
                    if auto_reset:
                        output.info(f"Starting {device_role.upper()} serial monitor with auto-reset...")
                    else:
                        output.info(f"Starting {device_role.upper()} serial monitor without auto-reset...")

                    result = await client.call_tool("start_serial_monitor", {
                        "auto_reset": auto_reset,
                        "device_role": device_role
                    })
                    monitor_result = parse_tool_result(result)

                    if monitor_result.get("success"):
                        message = monitor_result.get("message", "Serial monitoring started")
                        output.success(f"{device_role.upper()}: {message}")
                    else:
                        output.error(f"Failed to start {device_role.upper()} monitoring: {monitor_result.get('error', 'Unknown error')}")

                elif command == "stop_monitor":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Stopping {device_role.upper()} serial monitor...")
                    result = await client.call_tool("stop_serial_monitor", {
                        "device_role": device_role
                    })
                    monitor_result = parse_tool_result(result)

                    if monitor_result.get("success"):
                        output.success(f"{device_role.upper()} serial monitoring stopped")
                    else:
                        output.warning(f"No active {device_role.upper()} monitoring to stop")

                elif command == "get_data":
                    device_role, filtered_parts = parse_device_role(parts[1:])
                    seconds = float(filtered_parts[0]) if len(filtered_parts) > 0 else 10.0

                    output.info(f"Getting {device_role.upper()} serial data from last {seconds} seconds...")
                    result = await client.call_tool("get_serial_data", {
                        "seconds": seconds,
                        "device_role": device_role
                    })
                    data_result = parse_tool_result(result)

                    if data_result.get("success"):
                        data = data_result.get("data", [])
                        output.print(f"Retrieved {len(data)} lines from {device_role.upper()}:", color="blue")
                        for line in data:
                            output.print(f"  {line}")
                    else:
                        output.error(f"Failed to get {device_role.upper()} data: {data_result.get('error', 'Unknown error')}")

                elif command == "get_stats":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Getting {device_role.upper()} monitoring statistics...")
                    result = await client.call_tool("get_monitor_status", {
                        "device_role": device_role
                    })
                    stats_result = parse_tool_result(result)

                    if stats_result.get("success"):
                        stats = stats_result.get("stats", {})
                        output.print(f"{device_role.upper()} Serial Connection Statistics:", color="blue")
                        output.print(f"  Port: {stats.get('port', 'N/A')}")
                        output.print(f"  Baud Rate: {stats.get('baudrate', 'N/A')}")
                        output.print(f"  Connected: {stats.get('connected', False)}")
                        output.print(f"  Port Open: {stats.get('port_open', False)}")
                        output.print(f"  Monitoring Active: {stats.get('is_monitoring', False)}")
                        output.print(f"  Total Lines Received: {stats.get('lines_received', 0)}")
                        output.print(f"  Total Bytes Received: {stats.get('bytes_received', 0)}")
                        output.print(f"  Lines in Buffer: {stats.get('total_lines', 0)}")

                        # Provide troubleshooting hints
                        if stats.get('connected') and stats.get('port_open') and stats.get('is_monitoring'):
                            if stats.get('bytes_received', 0) == 0:
                                output.warning("No data received. Possible issues:")
                                output.print("  - ESP32 might not be sending data")
                                output.print("  - Wrong baud rate (try 9600, 38400, or 230400)")
                                output.print("  - ESP32 might be in deep sleep")
                                output.print("  - Try pressing the reset button on ESP32")
                            elif stats.get('lines_received', 0) == 0:
                                output.warning("Bytes received but no complete lines. Check line endings.")
                        else:
                            output.error("Connection or monitoring issue detected!")
                    else:
                        output.error(f"Failed to get stats: {stats_result.get('error', 'Unknown error')}")

                elif command == "test_log":
                    if len(parts) < 2:
                        output.error("Missing pattern parameter. Usage: test_log \"PATTERN\" [TIMEOUT] [\"DESCRIPTION\"]")
                        continue

                    pattern = parts[1]

                    # Parse timeout (if provided and is a number)
                    timeout = 10.0
                    description_start_idx = 2
                    if len(parts) > 2:
                        try:
                            timeout = float(parts[2])
                            description_start_idx = 3
                        except ValueError:
                            # parts[2] is not a number, so it's part of description
                            description_start_idx = 2

                    # Parse description (remaining parts joined)
                    if len(parts) > description_start_idx:
                        description = " ".join(parts[description_start_idx:])
                    else:
                        description = f"Check for pattern: {pattern}"

                    # Create step command for log search
                    step_command = f"search log {pattern} {timeout}"

                    output.info(f"Running log test: {description}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"Test passed: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Captured: {test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"Test failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"Test execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "test_gpio":
                    if len(parts) < 3:
                        output.error("Missing parameters. Usage: test_gpio PIN VALUE [TIMEOUT]")
                        continue

                    try:
                        pin = int(parts[1])
                        value = int(parts[2])
                        if value not in [0, 1]:
                            output.error("GPIO value must be 0 or 1")
                            continue
                    except ValueError:
                        output.error("Invalid pin or value. Pin and value must be integers.")
                        continue

                    timeout = float(parts[3]) if len(parts) > 3 else 10.0

                    # Create step command for GPIO test (using expect since it's a test)
                    step_command = f"gpio expect {pin} {value} {timeout}"

                    output.info(f"Running GPIO test: expect pin {pin} to be {'HIGH' if value else 'LOW'}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"GPIO test passed: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"GPIO test failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"GPIO test execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "gpio_set":
                    if len(parts) < 3:
                        output.error("Missing parameters. Usage: gpio_set PIN VALUE [TIMEOUT]")
                        continue

                    try:
                        pin = int(parts[1])
                        value = int(parts[2])
                        if value not in [0, 1]:
                            output.error("GPIO value must be 0 or 1")
                            continue
                    except ValueError:
                        output.error("Invalid pin or value. Pin and value must be integers.")
                        continue

                    timeout = float(parts[3]) if len(parts) > 3 else 10.0

                    # Create step command for GPIO set
                    step_command = f"gpio set {pin} {value} {timeout}"

                    output.info(f"Setting GPIO pin {pin} to {'HIGH' if value else 'LOW'}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"GPIO set completed: {test_details.get('message', 'Success')}")
                        else:
                            output.error(f"GPIO set failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"GPIO set execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "gpio_expect":
                    if len(parts) < 3:
                        output.error("Missing parameters. Usage: gpio_expect PIN VALUE [TIMEOUT]")
                        continue

                    try:
                        pin = int(parts[1])
                        value = int(parts[2])
                        if value not in [0, 1]:
                            output.error("GPIO value must be 0 or 1")
                            continue
                    except ValueError:
                        output.error("Invalid pin or value. Pin and value must be integers.")
                        continue

                    timeout = float(parts[3]) if len(parts) > 3 else 10.0

                    # Create step command for GPIO expect
                    step_command = f"gpio expect {pin} {value} {timeout}"

                    output.info(f"Expecting GPIO pin {pin} to be {'HIGH' if value else 'LOW'}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"GPIO expectation met: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"GPIO expectation failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"GPIO expectation execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "i2c_master_write":
                    if len(parts) < 4:
                        output.error("Missing parameters. Usage: i2c_master_write ADDR REG DATA [TIMEOUT]")
                        continue

                    try:
                        addr = int(parts[1], 16) if parts[1].startswith('0x') else int(parts[1], 16)
                        reg = int(parts[2], 16) if parts[2].startswith('0x') else int(parts[2], 16)
                        data = int(parts[3], 16) if parts[3].startswith('0x') else int(parts[3], 16)
                    except ValueError:
                        output.error("Invalid address, register, or data. Use hex format like 0x77 or decimal.")
                        continue

                    timeout = float(parts[4]) if len(parts) > 4 else 10.0

                    # Create step command for I2C master write
                    step_command = f"i2c write 0x{addr:02X} reg:0x{reg:02X},data:0x{data:02X} master"

                    output.info(f"I2C Master Write: addr=0x{addr:02X}, reg=0x{reg:02X}, data=0x{data:02X}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"I2C master write successful: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"I2C master write failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"I2C master write execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "i2c_master_read":
                    if len(parts) < 3:
                        output.error("Missing parameters. Usage: i2c_master_read ADDR REG [TIMEOUT]")
                        continue

                    try:
                        addr = int(parts[1], 16) if parts[1].startswith('0x') else int(parts[1], 16)
                        reg = int(parts[2], 16) if parts[2].startswith('0x') else int(parts[2], 16)
                    except ValueError:
                        output.error("Invalid address or register. Use hex format like 0x77 or decimal.")
                        continue

                    timeout = float(parts[3]) if len(parts) > 3 else 10.0

                    # Create step command for I2C master read
                    step_command = f"i2c read 0x{addr:02X} 0x{reg:02X} master"

                    output.info(f"I2C Master Read: addr=0x{addr:02X}, reg=0x{reg:02X}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"I2C master read successful: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"I2C master read failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"I2C master read execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "i2c_slave_write":
                    if len(parts) < 4:
                        output.error("Missing parameters. Usage: i2c_slave_write ADDR REG DATA [TIMEOUT]")
                        continue

                    try:
                        addr = int(parts[1], 16) if parts[1].startswith('0x') else int(parts[1], 16)
                        reg = int(parts[2], 16) if parts[2].startswith('0x') else int(parts[2], 16)
                        data = int(parts[3], 16) if parts[3].startswith('0x') else int(parts[3], 16)
                    except ValueError:
                        output.error("Invalid address, register, or data. Use hex format like 0x77 or decimal.")
                        continue

                    timeout = float(parts[4]) if len(parts) > 4 else 10.0

                    # Create step command for I2C slave write expectation
                    step_command = f"i2c write 0x{addr:02X} reg:0x{reg:02X},data:0x{data:02X} slave"

                    output.info(f"I2C Slave Mode: expecting write to addr=0x{addr:02X}, reg=0x{reg:02X}, data=0x{data:02X}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"I2C slave write expectation met: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"I2C slave write expectation failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"I2C slave write execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "i2c_slave_read":
                    if len(parts) < 4:
                        output.error("Missing parameters. Usage: i2c_slave_read ADDR REG DATA [TIMEOUT]")
                        continue

                    try:
                        addr = int(parts[1], 16) if parts[1].startswith('0x') else int(parts[1], 16)
                        reg = int(parts[2], 16) if parts[2].startswith('0x') else int(parts[2], 16)
                        data = int(parts[3], 16) if parts[3].startswith('0x') else int(parts[3], 16)
                    except ValueError:
                        output.error("Invalid address, register, or data. Use hex format like 0x77 or decimal.")
                        continue

                    timeout = float(parts[4]) if len(parts) > 4 else 10.0

                    # Create step command for I2C slave read expectation
                    step_command = f"i2c read 0x{addr:02X} reg:0x{reg:02X},data:0x{data:02X} slave"

                    output.info(f"I2C Slave Mode: will respond when master reads from addr=0x{addr:02X}, reg=0x{reg:02X}, will send data=0x{data:02X}")
                    result = await client.call_tool("execute_tests", {"steps": [step_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"I2C slave read expectation met: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"I2C slave read expectation failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"I2C slave read execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "test_i2c":
                    if len(parts) < 2:
                        output.error("Missing I2C command. Usage: test_i2c COMMAND")
                        output.print("Examples:", color="yellow")
                        output.print("  test_i2c \"i2c write 0x77 reg:0x12,data:0x34\"")
                        output.print("  test_i2c \"i2c read 0x77 0x12\"")
                        output.print("  test_i2c \"i2c write 0x77 reg:0x12,data:0x34 slave\"")
                        continue

                    # Join the remaining parts as the I2C command
                    i2c_command = " ".join(parts[1:])

                    output.info(f"Running I2C test: {i2c_command}")
                    result = await client.call_tool("execute_tests", {"steps": [i2c_command]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        test_details = test_result.get("results", [{}])[0]
                        if test_details.get("success"):
                            output.success(f"I2C test passed: {test_details.get('message', 'Success')}")
                            if test_details.get("captured_data"):
                                output.print(f"Test logs:\n{test_details['captured_data']}", color="blue")
                        else:
                            output.error(f"I2C test failed: {test_details.get('message', 'Unknown error')}")
                    else:
                        output.error(f"I2C test execution failed: {test_result.get('error', 'Unknown error')}")

                elif command == "run_test":
                    output.print("Step-Based Test Sequence", color="cyan")
                    output.print("Enter test steps one by one. Type 'done' when finished.", color="yellow")
                    output.print("Supported steps:", color="blue")
                    output.print("  reset [wait_seconds] - Reset ESP32 device")
                    output.print("  delay seconds - Wait for specified seconds")
                    output.print("  flash project_dir - Flash firmware from project directory")
                    output.print("  search log \"pattern\" [timeout] - Search for log pattern")
                    output.print("  wait log \"pattern\" [timeout] - Alias for search log")
                    output.print("  gpio set pin value [timeout] - Set GPIO pin to value")
                    output.print("  gpio expect pin value [timeout] - Expect GPIO pin to have value")
                    output.print("  i2c write addr data [role] - I2C write operation")
                    output.print("  i2c read addr [reg] [role] - I2C read operation")
                    output.print("")
                    output.print("I2C Examples:", color="blue")
                    output.print("  i2c write 0x77 reg:0x12,data:0x34 - Master write")
                    output.print("  i2c read 0x77 0x12 - Master read")
                    output.print("  i2c write 0x77 reg:0x12,data:0x34 slave - Slave expect write")
                    output.print("  i2c read 0x77 reg:0x12,data:0xAB slave - Slave respond when master reads, send data")
                    output.print("")

                    steps = []
                    while True:
                        step_input = input(f"Step {len(steps)+1}> ").strip()

                        if step_input.lower() == 'done':
                            break
                        elif step_input.lower() == 'cancel':
                            output.warning("Test sequence cancelled")
                            steps = []
                            break
                        elif step_input:
                            steps.append(step_input)
                            output.print(f"Added: {step_input}", color="green")

                    if steps:
                        output.info(f"Running {len(steps)} test steps...")
                        result = await client.call_tool("execute_tests", {"steps": steps})
                        test_result = parse_tool_result(result)

                        if test_result.get("success"):
                            passed = test_result.get("passed_steps", 0)
                            total = test_result.get("total_steps", 0)
                            output.success(f"Test sequence completed: {passed}/{total} steps passed")

                            # Show individual results
                            for result_detail in test_result.get("results", []):
                                status = "✓" if result_detail.get("success") else "✗"
                                output.print(f"  {status} {result_detail.get('description', 'Step')}")
                                if result_detail.get("captured_data"):
                                    output.print(f"    Captured: {result_detail['captured_data']}", color="blue")
                        else:
                            output.error(f"Test sequence failed: {test_result.get('error', 'Unknown error')}")
                    else:
                        output.warning("No steps to execute")

                elif command == "example_workflow":
                    await run_example_workflow(client)

                elif command == "history":
                    tool_name = parts[1] if len(parts) > 1 else None
                    params = {"limit": 10}
                    if tool_name:
                        params["tool_name"] = tool_name

                    output.info("Getting tool history...")
                    # Note: get_history tool was removed from server, so we'll show local history
                    history = db.get_tool_history(tool_name, 10)
                    output.print("Local Tool Call History:", color="blue")
                    output.output(history)

                elif command == "monitor_status":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Getting detailed {device_role.upper()} monitoring thread and connection status...")
                    result = await client.call_tool("get_monitor_status", {
                        "device_role": device_role
                    })
                    status_result = parse_tool_result(result)

                    if status_result.get("success"):
                        output.print(f"{device_role.upper()} Monitoring Status:", color="blue")

                        # Display basic stats
                        stats = status_result.get("stats", {})
                        output.print("Basic Stats:", color="cyan")
                        output.print(f"  Is Monitoring: {stats.get('is_monitoring', False)}")
                        output.print(f"  Port: {stats.get('port', 'N/A')}")
                        output.print(f"  Baudrate: {stats.get('baudrate', 'N/A')}")
                        output.print(f"  Total Lines: {stats.get('total_lines', 0)}")
                        output.print(f"  Bytes Received: {stats.get('bytes_received', 0)}")
                        output.print(f"  Lines Received: {stats.get('lines_received', 0)}")

                        # Display thread info
                        thread_info = status_result.get("thread_info", {})
                        output.print("Thread Info:", color="cyan")
                        output.print(f"  Monitor Thread Exists: {thread_info.get('monitor_thread_exists', False)}")
                        output.print(f"  Monitor Thread Alive: {thread_info.get('monitor_thread_alive', False)}")
                        output.print(f"  Stop Event Set: {thread_info.get('stop_event_set', False)}")

                        # Display serial connection info
                        serial_info = status_result.get("serial_info", {})
                        output.print("Serial Connection:", color="cyan")
                        if "error" in serial_info:
                            output.print(f"  Error: {serial_info['error']}")
                        else:
                            output.print(f"  Port: {serial_info.get('port', 'N/A')}")
                            output.print(f"  Baudrate: {serial_info.get('baudrate', 'N/A')}")
                            output.print(f"  Is Open: {serial_info.get('is_open', False)}")
                            output.print(f"  Bytes Waiting: {serial_info.get('in_waiting', 0)}")
                            output.print(f"  Timeout: {serial_info.get('timeout', 'N/A')}")
                    else:
                        output.error(f"Failed to get monitoring status: {status_result.get('error', 'Unknown error')}")

                elif command == "add_test_data":
                    device_role, filtered_parts = parse_device_role(parts[1:])
                    
                    if len(filtered_parts) < 1:
                        output.error("Missing test data parameter. Usage: add_test_data \"LINE1\" [\"LINE2\" ...] [--dut|--tester]")
                        continue

                    # Collect all the lines (filtered_parts are the individual lines)
                    test_lines = filtered_parts
                    output.info(f"Adding {len(test_lines)} test lines to {device_role.upper()}...")
                    result = await client.call_tool("add_test_data", {
                        "lines": test_lines,
                        "device_role": device_role
                    })
                    add_result = parse_tool_result(result)

                    if add_result.get("success"):
                        lines_added = add_result.get("lines_added", 0)
                        total_lines = add_result.get("total_lines", 0)
                        output.success(f"Added {lines_added} test lines to {device_role.upper()}. Total lines in buffer: {total_lines}")
                    else:
                        output.error(f"Failed to add test data to {device_role.upper()}: {add_result.get('error', 'Unknown error')}")

                elif command == "test_search":
                    if len(parts) < 2:
                        output.error("Missing pattern parameter. Usage: test_search \"PATTERN\" [TIMEOUT]")
                        continue

                    pattern = parts[1]
                    timeout = float(parts[2]) if len(parts) > 2 else 10.0

                    output.info(f"Testing search for pattern '{pattern}' with timeout {timeout}s...")

                    # Use the execute_tests tool to test search functionality
                    test_step = f"search log \"{pattern}\" {timeout}"
                    result = await client.call_tool("execute_tests", {"steps": [test_step]})
                    test_result = parse_tool_result(result)

                    if test_result.get("success"):
                        step_result = test_result.get("results", [{}])[0]
                        if step_result.get("success"):
                            output.success(f"Pattern found: {step_result.get('message', 'Success')}")
                            if step_result.get("captured_data"):
                                output.print(f"Matched line: {step_result['captured_data']}", color="blue")
                        else:
                            output.warning(f"Pattern not found: {step_result.get('message', 'No match')}")
                    else:
                        output.error(f"Search test failed: {test_result.get('error', 'Unknown error')}")

                elif command == "check_immediate_data":
                    device_role, filtered_parts = parse_device_role(parts[1:])
                    # Default to 1.0 seconds if no parameter provided
                    wait_seconds = float(filtered_parts[0]) if len(filtered_parts) > 0 else 1.0

                    output.info(f"Checking {device_role.upper()} for immediate data reception for {wait_seconds} seconds...")
                    result = await client.call_tool("check_immediate_data", {
                        "wait_seconds": wait_seconds,
                        "device_role": device_role
                    })
                    check_result = parse_tool_result(result)

                    if check_result.get("success"):
                        new_data = check_result.get("new_data", {})
                        new_lines = new_data.get("lines", 0)
                        new_bytes = new_data.get("bytes", 0)

                        if new_lines > 0:
                            output.success(f"Data received: {new_lines} lines, {new_bytes} bytes")

                            # Show timeline if available
                            timeline = check_result.get("data_timeline", [])
                            if timeline:
                                first_data_time = timeline[0]["time_seconds"]
                                output.info(f"First data received at {first_data_time}s")

                            # Show sample data
                            sample_data = check_result.get("recent_data_sample", [])
                            if sample_data:
                                output.print("Sample data received:", color="blue")
                                for line in sample_data[:3]:  # Show first 3 lines
                                    output.print(f"  {line}")
                        else:
                            output.warning(f"No data received in {wait_seconds} seconds")

                        # Show monitoring status
                        monitoring_active = check_result.get("monitoring_active", False)
                        thread_alive = check_result.get("thread_alive", False)
                        output.info(f"Monitoring active: {monitoring_active}, Thread alive: {thread_alive}")
                    else:
                        output.error(f"Failed to check immediate data: {check_result.get('error', 'Unknown error')}")

                elif command == "clear_log_buffer":
                    device_role, _ = parse_device_role(parts[1:])
                    
                    output.info(f"Clearing {device_role.upper()} log buffer...")
                    result = await client.call_tool("clear_log_buffer", {
                        "device_role": device_role
                    })
                    clear_result = parse_tool_result(result)

                    if clear_result.get("success"):
                        output.success(f"{device_role.upper()} log buffer cleared successfully")
                    else:
                        output.error(f"Failed to clear {device_role.upper()} log buffer: {clear_result.get('error', 'Unknown error')}")

                elif command == "flash":
                    if len(parts) < 2:
                        output.error("Missing project directory parameter. Usage: flash PROJECT_DIR")
                        continue

                    project_dir = parts[1]
                    output.info(f"Flashing firmware from {project_dir}...")
                    result = await client.call_tool("flash_firmware", {"project_dir": project_dir})
                    flash_result = parse_tool_result(result)

                    if flash_result.get("success"):
                        output.success("Firmware flashed successfully")
                        flash_info = flash_result.get("flash_info", {})
                        if flash_info:
                            output.print("Flash details:", color="blue")
                            for key, value in flash_info.items():
                                output.print(f"  {key}: {value}")
                    else:
                        output.error(f"Flash failed: {flash_result.get('error', 'Unknown error')}")
                        if flash_result.get("details"):
                            output.print(f"Details: {flash_result['details']}", color="red")

                else:
                    output.error(f"Unknown command: {command}")
                    output.print("Type 'help' for available commands", color="yellow")

            except KeyboardInterrupt:
                output.print("\nUse 'exit' or 'quit' to exit gracefully", color="yellow")
                # Save command history on interrupt
                try:
                    history_file = os.path.expanduser("~/.device_test_client_history")
                    readline.write_history_file(history_file)
                except Exception as e:
                    logger.warning(f"Failed to save command history: {e}")
            except Exception as e:
                output.error(f"Error: {str(e)}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(interactive_loop())
