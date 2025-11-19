# ESP-IDF Builder

## Overview
A Model Context Protocol (MCP) server for building ESP32 projects using ESP-IDF. This tool provides functionality for detecting connected ESP32 chips, automatically setting build targets, and building projects with comprehensive error reporting.

## Features
- **Automatic Chip Detection**: Detect connected ESP32 chips using esptool
- **Automatic Target Setting**: Automatically set the correct ESP-IDF target based on detected chip
- **Project Building**: Build ESP32 projects with detailed error and warning reporting
- **Build Log Management**: Access full build logs and summaries
- **MCP Integration**: Full Model Context Protocol support for AI assistant integration

## Installation

```bash
# Navigate to the tool directory
cd mcp_tools/examples/idf-builder

# Install dependencies
pip install -r requirements.txt
```

## Prerequisites
- ESP-IDF installed and configured
- `idf.py` available in PATH
- `esptool.py` available (usually comes with ESP-IDF)

## Usage

### Running the Server
```bash
python server.py
```

The server will start using stdio transport for MCP communication.

## Available Tools

### Chip Detection

#### `detect_chip`
Auto-detect connected ESP32 chip using esptool.py.

**Parameters:** None

**Response:**
```json
{
  "success": true,
  "chip_type": "ESP32-S3",
  "features": "WiFi, BLE",
  "mac": "24:6f:28:xx:xx:xx",
  "raw_output": "esptool.py output..."
}
```

### Target Management

#### `set_target`
Set the ESP-IDF target for a project, with automatic chip detection.

**Parameters:**
- `project_path` (string): Path to the ESP32 project containing CMakeLists.txt
- `target` (string, optional): Specific target to set (e.g., esp32, esp32s3, esp32c3). If None, will auto-detect.
- `auto_detect` (boolean, optional): If True and target is None, automatically detect connected chip and set target (default: True)

**Example:**
```json
{
  "project_path": "/path/to/esp32/project",
  "auto_detect": true
}
```

**Response:**
```json
{
  "success": true,
  "target": "esp32s3",
  "detected_target": "esp32s3",
  "auto_detected": true,
  "message": "Target successfully set to esp32s3",
  "output": "idf.py set-target output..."
}
```

**Supported Targets:**
- `esp32` - Original ESP32
- `esp32s2` - ESP32-S2
- `esp32s3` - ESP32-S3
- `esp32c2` - ESP32-C2
- `esp32c3` - ESP32-C3
- `esp32c6` - ESP32-C6
- `esp32h2` - ESP32-H2

### Project Building

#### `build_project`
Build ESP32 project at the specified path with automatic target detection and setting.

**Parameters:**
- `project_path` (string): Path to the ESP32 project containing CMakeLists.txt
- `auto_set_target` (boolean, optional): If True, automatically detect chip and set target before building (default: True)

**Example:**
```json
{
  "project_path": "/path/to/esp32/project",
  "auto_set_target": true
}
```

**Response:**
```json
{
  "success": true,
  "error_count": 0,
  "warning_count": 2,
  "summary": "TARGET SET: esp32s3 (auto-detected)\nBUILD SUCCESSFUL: Project build complete.",
  "error_files": [],
  "target_set": true,
  "detected_target": "esp32s3"
}
```

### Build Log Management

#### `get_full_build_log`
Get the complete build log from the last build operation.

**Parameters:** None

**Response:** String containing the full build output

#### `get_build_summary`
Get a summary of the last build with errors, warnings, and key information.

**Parameters:** None

**Response:** String containing the build summary

## Workflow Examples

### Basic Build with Auto-Target Detection
```json
{
  "tool": "build_project",
  "parameters": {
    "project_path": "/Users/dev/my-esp32-project"
  }
}
```

This will:
1. Detect the connected ESP32 chip
2. Map the chip type to the appropriate ESP-IDF target
3. Set the target using `idf.py set-target`
4. Build the project using `idf.py build`

### Manual Target Setting
```json
{
  "tool": "set_target",
  "parameters": {
    "project_path": "/Users/dev/my-esp32-project",
    "target": "esp32c3"
  }
}
```

### Build Without Auto-Target
```json
{
  "tool": "build_project",
  "parameters": {
    "project_path": "/Users/dev/my-esp32-project",
    "auto_set_target": false
  }
}
```

## Chip Detection and Target Mapping

The tool automatically maps detected chip types to ESP-IDF targets:

| Detected Chip | ESP-IDF Target |
|---------------|----------------|
| ESP32 | esp32 |
| ESP32-S2 | esp32s2 |
| ESP32-S3 | esp32s3 |
| ESP32-C2 | esp32c2 |
| ESP32-C3 | esp32c3 |
| ESP32-C6 | esp32c6 |
| ESP32-H2 | esp32h2 |

## Error Handling
- Graceful handling of missing ESP-IDF tools
- Detailed error reporting for build failures
- Automatic fallback when chip detection fails
- Comprehensive logging for debugging

## Data Storage
- Build results and tool calls are stored in SQLite database (`data/tool.db`)
- Build logs are temporarily stored in memory for quick access
- All operations are logged with parameters, results, and timestamps

## Development

### Project Structure
```
idf-builder/
├── server.py         # Main MCP server with build functionality
├── requirements.txt  # Dependencies (fastmcp)
├── data/             # SQLite database storage
├── config/           # MCP client configuration
└── README.md         # This documentation
```

### Dependencies
- `fastmcp`: Model Context Protocol framework
- ESP-IDF tools (`idf.py`, `esptool.py`)

## License
Part of the MCP Tools collection.

## Contact
For questions or support, please refer to the main MCP Tools documentation.
