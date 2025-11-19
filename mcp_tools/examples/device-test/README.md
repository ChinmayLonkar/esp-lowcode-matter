# Device Test

## Overview
A Model Context Protocol (MCP) server for testing ESP32 devices through serial monitoring, automated test execution, and firmware flashing. This tool provides comprehensive functionality for connecting to ESP32 devices via serial ports, monitoring their output, executing automated tests to verify device behavior (including GPIO and I2C communication), and flashing firmware binaries.

## Features
- **Serial Port Management**: List, connect, and monitor ESP32 devices via serial ports
- **Real-time Serial Monitoring**: Capture and analyze serial output from connected devices
- **Automated Test Execution**: Run structured tests to verify device functionality
- **Firmware Flashing**: Flash ESP32 firmware using project build files
- **Extensible Test Framework**: Support for multiple test types (log, GPIO, I2C, UART, CLI, flash)
- **Data Storage**: Store test results and device data for analysis
- **MCP Integration**: Full Model Context Protocol support for AI assistant integration

## Installation

```bash
# Navigate to the tool directory
cd mcp_tools/examples/device-test

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Running the Server
```bash
python server.py
```

The server will start using stdio transport for MCP communication.

### Configuration

#### Client Configuration
Configuration templates for various AI assistants are available in the `config` directory:

- `mcp.json`: For use with MCP-compatible clients

## Available Tools

### Serial Port Management

#### `list_serial_ports`
List all available serial ports on the system.

**Parameters:** None

**Response:**
```json
[
  {
    "device": "/dev/ttyUSB0",
    "name": "ttyUSB0",
    "description": "USB Serial Device",
    "manufacturer": "FTDI"
  }
]
```

#### `connect_serial`
Connect to a specific serial port for monitoring.

**Parameters:**
- `port` (string): Serial port device path (e.g., `/dev/ttyUSB0`, `COM3`)
- `baudrate` (integer, optional): Baud rate for communication (default: 115200)

**Example:**
```json
{
  "port": "/dev/ttyUSB0",
  "baudrate": 115200
}
```

#### `disconnect_serial`
Disconnect from the current serial port.

**Parameters:** None

### Serial Monitoring

#### `start_serial_monitor`
Start monitoring serial data from the connected device.

**Parameters:** None

#### `stop_serial_monitor`
Stop monitoring serial data.

**Parameters:** None

#### `get_serial_data`
Retrieve recent serial data from the connected device.

**Parameters:**
- `seconds` (float, optional): Number of seconds of recent data to retrieve (default: 10.0)

**Response:**
```json
{
  "success": true,
  "data": ["ESP32 Boot", "WiFi connected", "Application started"],
  "lines_count": 3,
  "timeframe_seconds": 10.0
}
```

### Test Execution

#### `execute_tests`
Execute a series of automated tests on the connected device.

**Parameters:**
- `steps` (array): List of test step commands

Each test step can be one of:
- `"reset [wait_seconds]"` - Reset ESP32 device, optionally wait specified seconds
- `"delay seconds"` - Wait for specified number of seconds
- `"search log pattern [timeout]"` - Search for log pattern with optional timeout
- `"wait log pattern [timeout]"` - Alias for search log
- `"flash [project_dir]"` - Flash firmware using build/flash_args file
- `"gpio set pin value [timeout]"` - Set GPIO pin to value via tester device
- `"gpio expect pin value [timeout]"` - Expect GPIO pin to have value via tester device
- `"i2c write addr data [role]"` - I2C write operation (master/slave mode)
- `"i2c read addr [reg] [role]"` - I2C read operation (master/slave mode)

**Example:**
```json
{
  "steps": [
    "flash /path/to/project",
    "reset 3",
    "search log \"WiFi connected\" 15",
    "search log \"Application started\" 5",
    "gpio set 2 1 5",
    "gpio expect 18 0 3",
    "i2c write 0x77 reg:0x12,data:0x34",
    "i2c read 0x77 0x12"
  ]
}
```

**Response:**
```json
{
  "success": true,
  "total_tests": 2,
  "passed_tests": 2,
  "failed_tests": 0,
  "results": [
    {
      "test_index": 0,
      "description": "Check WiFi connection",
      "type": "log",
      "action": "check",
      "value": "WiFi connected",
      "success": true,
      "message": "Found expected log pattern: WiFi connected",
      "execution_time": 2.1,
      "captured_data": "I (2345) wifi: WiFi connected"
    }
  ]
}
```

### Data Management

#### `save_data`
Save data to the database.

**Parameters:**
- `key` (string): The key to store the data under
- `value` (any): The value to store

#### `get_data`
Retrieve data from the database.

**Parameters:**
- `key` (string): The key to retrieve

#### `get_history`
Get the history of tool calls.

**Parameters:**
- `tool_name` (string, optional): Filter by tool name
- `limit` (integer, optional): Maximum number of records to return (default: 10)

### Firmware Flashing

#### `flash_firmware`
Flash firmware to ESP32 device using the project's build/flash_args file.

**Parameters:**
- `project_dir` (string): Path to the ESP32 project directory containing build/flash_args
- `port` (string, optional): Serial port to use for flashing (will auto-detect if not provided)

**Example:**
```json
{
  "project_dir": "/path/to/esp32/project",
  "port": "/dev/ttyUSB0"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Firmware flashed successfully",
  "output": "esptool.py output...",
  "flash_config": {
    "flash_params": ["--flash_mode", "dio", "--flash_freq", "40m", "--flash_size", "2MB"],
    "file_mappings": [
      {"address": "0x1000", "file": "bootloader/bootloader.bin"},
      {"address": "0x10000", "file": "app.bin"},
      {"address": "0x8000", "file": "partition_table/partition-table.bin"}
    ]
  }
}
```

## Test Types

### Log Tests
- **Type**: `"log"`
- **Action**: `"check"` - Wait for a specific log pattern
- **Value**: Regular expression pattern to match in serial output
- **Use Case**: Verify device startup messages, error conditions, status updates

### Flash Tests
- **Type**: `"flash"`
- **Action**: `"action"` - Flash firmware to the device
- **Value**: Project directory path containing build/flash_args file
- **Use Case**: Deploy new firmware before running tests

### GPIO Tests
- **Type**: `"gpio"`
- **Actions**: `"write"` (set pin state), `"read"` (expect pin state)
- **Value**: Pin number and expected/target state (0 or 1)
- **Use Case**: Hardware interface validation, signal verification

### I2C Tests
- **Type**: `"i2c"`
- **Actions**: `"write"` (send data), `"read"` (receive data)
- **Modes**: Master (initiate communication) or Slave (respond to requests)
- **Parameters**: Device address, register address, data values
- **Use Case**: Inter-device communication testing, sensor validation

### Future Test Types (Planned)
- **UART Tests**: Test UART communication protocols
- **CLI Tests**: Execute command-line interface commands

## Data Storage
- Test results and device data are stored in SQLite database (`data/tool.db`)
- All tool calls are logged with parameters, results, and timestamps
- Serial data is temporarily stored in memory during monitoring sessions

## Error Handling
- Graceful handling of serial connection failures
- Timeout management for test execution
- Detailed error messages with context
- Automatic cleanup of resources on disconnection

## Development

### Project Structure
```
device-test/
├── server.py         # Main MCP server with serial monitoring
├── requirements.txt  # Dependencies (fastmcp, pyserial)
├── data/             # SQLite database storage
├── config/           # MCP client configuration
└── README.md         # This documentation
```

### Dependencies
- `fastmcp`: Model Context Protocol framework
- `pyserial>=3.5`: Serial communication library

### Running Tests
Connect an ESP32 device and run:
```bash
python server.py
```

Then use an MCP client to test the functionality.

## Example Workflow

1. **Flash new firmware**: Use `flash_firmware` to deploy updated code
2. **List available ports**: Use `list_serial_ports` to find your ESP32 devices
3. **Connect to devices**: Use `connect_serial` to establish connections (DUT and Tester)
4. **Start monitoring**: Use `start_serial_monitor` to capture output from both devices
5. **Run tests**: Use `execute_tests` with a sequence of test steps (log, GPIO, I2C)
6. **Analyze results**: Review test outcomes and captured data

### Complete Test Sequence Example

```json
{
  "steps": [
    "flash /Users/dev/esp32-project",
    "reset 5",
    "search log \"ESP32 Boot\" 10",
    "search log \"WiFi connected\" 30",
    "search log \"Application ready\" 15",
    "delay 2",
    "search log \"Sensor data\" 10"
  ]
}
```

## License
Part of the MCP Tools collection.

## Contact
For questions or support, please refer to the main MCP Tools documentation.

## Flash Args File Format

The tool uses the ESP-IDF generated `build/flash_args` file to determine flash parameters and binary file locations. This file format is:

```
--flash_mode dio --flash_freq 40m --flash_size 2MB
0x1000 bootloader/bootloader.bin
0x10000 app.bin
0x8000 partition_table/partition-table.bin
```

- **First line**: Flash parameters (mode, frequency, size)
- **Subsequent lines**: Address and binary file pairs

The tool automatically:
- Parses flash parameters and file mappings
- Locates esptool.py (from PATH, IDF_PATH, or common locations)
- Disconnects serial monitoring during flash to avoid conflicts
- Validates that all binary files exist before flashing

## Example Workflow

1. **Flash new firmware**: Use `flash_firmware` to deploy updated code
2. **List available ports**: Use `list_serial_ports` to find your ESP32
3. **Connect to device**: Use `connect_serial` to establish connection
4. **Start monitoring**: Use `start_serial_monitor` to capture output
5. **Run tests**: Use `execute_tests` with a sequence of test steps
6. **Analyze results**: Review test outcomes and captured data

### Complete Test Sequence Example

```json
{
  "steps": [
    "flash /Users/dev/esp32-project",
    "reset 5",
    "search log \"ESP32 Boot\" 10",
    "search log \"WiFi connected\" 30",
    "search log \"Application ready\" 15",
    "delay 2",
    "search log \"Sensor data\" 10"
  ]
}
```
