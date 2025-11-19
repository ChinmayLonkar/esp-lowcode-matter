# MCP

Servers of the format of the Model Context Protocol (MCP).

https://modelcontextprotocol.io/quickstart/server

Cursor or other LLMs don't understand what MCP is. It is better to give the above link in the first prompt.

## Quick Setup

Get started with MCP tools in minutes:

```bash
cd /PATH_TO_MCP_TOOLS/mcp_tools
bash setup.sh
```

This will:
- Auto-detect your environment (Python, ESP-IDF, tools)
- Install all dependencies automatically
- Generate MCP configuration json file
- Validate complete setup

**After setup:** Copy the generated config to Cursor's mcp.json, restart, and use the tools!

For detailed setup instructions and troubleshooting, see **[SETUP_GUIDE.md](./SETUP_GUIDE.md)**.

## Claude Desktop

Append the `configs/claude_desktop.json` from the respective folder to the `claude_desktop_config.json` file in the claude desktop config directory in your root directory.

## Cursor

The setup script generates a portable configuration file. After running `bash setup.sh`:

1. Open the generated config: `cat mcp_tools/config/mcp.json`
2. Go to Cursor Settings → Extensions → MCP → Edit Config
3. Copy the `mcpServers` section
4. Paste into your `~/.cursor/mcp.json`
5. Save and restart Cursor

The three tools will then be available:
- `@idf-builder` - ESP-IDF build system
- `@device-test` - Device testing and flashing
- `@system` - File operations and documentation

**Portable config**: The generated `mcp_tools/config/mcp.json` can be copied to any machine or shared with team members.

# MCP Tools

Tools built using the Model Context Protocol (MCP) framework.

https://modelcontextprotocol.io/quickstart/server

## Available Tools

Each tool runs in its own **isolated virtual environment** to prevent dependency conflicts.

### idf-builder
Build and manage ESP32 projects using ESP-IDF.
- Build projects
- Set target chip
- View build logs
- Clean builds

**Environment:** `examples/idf-builder/venv/`  
**Requires:** ESP-IDF installation

### device-test
Test and flash ESP32 devices with dual-device support.
- Serial port management
- Device connection/flashing
- I2C bus monitoring and merging
- Log analysis and verification

**Environment:** `examples/device-test/venv/`  
**Requires:** Connected ESP32 devices via serial ports

### system
File system operations and documentation processing.
- File listing and reading
- Text search across files
- PDF extraction and analysis
- Web page reading
- Patch application

**Environment:** `examples/system/venv/`

## Client Configuration

### Claude Desktop

Append the `configs/claude_desktop.json` from the respective tool folder to the `claude_desktop_config.json` file in the Claude Desktop config directory.

### Cursor

Append the `configs/cursor.json` from the respective tool folder to the `mcp.json` file in the Cursor config directory (usually `~/.cursor/mcp.json`).

Or use the automated setup: `bash setup.sh`

## Components

The `components/` directory contains reusable components for building MCP tools:

- `path_setup.py`: Utility for setting up Python import paths correctly
- `database.py`: Database module with SQLite support
- `network.py`: HTTP client and API utilities
- `output.py`: Output formatting utilities
- `async_utils.py`: Utilities for asynchronous operations

## Creating a New Tool

The easiest way to create a new MCP tool is to use the provided script:

```bash
python mcp_tools/tools/create_tool.py my-new-tool
```

This will create a new directory at `mcp_tools/examples/my-new-tool/` with all the necessary files:

- `server.py`: Server implementation
- `server_http.py`: HTTP server implementation
- `client.py`: Client implementation
- `client_http.py`: HTTP client implementation
- `configs/`: Configuration templates for different clients
- `README.md`: Documentation for your tool

## Tool Development

When developing tools, please follow the guidelines in `CURSOR_RULES.md`. Key points include:

1. Use the components from `mcp_tools/components/`
2. Follow MCP standards for tool definitions
3. Include comprehensive tests for your tools
4. Document your tools thoroughly

## Testing

Run tests for all components and tools using:

```bash
python mcp_tools/tests/run_tests.py
```

## Directory Structure

```
mcp_tools/
├── setup.sh                    # Automated setup script (RUN THIS FIRST!)
├── config/
│   ├── config.template.json   # Configuration template
│   ├── environment_detector.py # Auto-environment detection
│   └── generate_config.py      # Config file generator
├── setup/
│   ├── install_dependencies.py # Dependency installer
│   └── validate_setup.py       # Setup validator
├── components/                 # Reusable components
│   ├── path_setup.py           # Import path utilities
│   ├── database.py             # Database module
│   ├── network.py              # HTTP client utilities
│   ├── output.py               # Output formatting
│   └── async_utils.py          # Async utilities
├── examples/                   # Examples and tools
│   ├── idf-builder/            # Build system integration
│   ├── device-test/            # Device testing tool
│   ├── system/                 # System operations tool
│   └── template/               # Basic template for new tools
├── tools/                      # MCP tools scripts
│   ├── create_tool.py          # Script to create new tools
│   └── README_TEMPLATE.md      # Template for tool README files
├── tests/                      # Test suite
│   ├── run_tests.py            # Test runner
│   ├── test_components.py      # Tests for components
│   ├── test_examples.py        # Tests for example tools
│   └── test_path_setup.py      # Tests for path setup
├── SETUP_GUIDE.md              # Detailed setup documentation
└── README.md                   # This file
```

## Getting Started

### Automated Setup (Recommended)

```bash
cd /Users/chinmay/esp/yolo/mcp_tools
bash setup.sh
```

### Manual Setup

1. Create virtual environments for each server:
   ```bash
   python3 mcp_tools/setup/create_server_venvs.py
   ```
   This creates isolated Python environments:
   - `examples/idf-builder/venv/`
   - `examples/device-test/venv/`
   - `examples/system/venv/`

2. Generate configuration:
   ```bash
   python3 mcp_tools/config/generate_config.py
   ```

3. Validate the setup:
   ```bash
   python3 mcp_tools/setup/validate_setup.py
   ```

4. Copy `mcp_tools/config/mcp.json` to Cursor's MCP settings

5. Restart Cursor

## Troubleshooting

### Setup Issues

See **[SETUP_GUIDE.md](./SETUP_GUIDE.md)** for comprehensive troubleshooting.

Common issues:
- Python not found → Install Python 3.8+
- Dependencies fail → Update pip: `python3 -m pip install --upgrade pip`
- Cursor doesn't show tools → Restart Cursor completely

### Tool-Specific Issues

- **idf-builder**: See `examples/idf-builder/README.md`
- **device-test**: See `examples/device-test/README.md`
- **system**: See `examples/system/README.md`

## Isolated Virtual Environments

Each MCP server runs in its own Python virtual environment:

**Benefits:**
- ✅ No dependency conflicts between servers
- ✅ Clean system Python (no global pollution)
- ✅ Easy to update individual servers
- ✅ Portable - copy entire directory to another machine
- ✅ Self-contained - delete server → delete directory
- ✅ Each venv has its own copy of critical tools (like esptool)

**Location:**
```
mcp_tools/examples/
  ├── idf-builder/venv/  ← Isolated Python + ESP-IDF dependencies
  ├── device-test/venv/  ← Isolated Python + esptool + pyserial
  └── system/venv/       ← Isolated Python + PDF/web tools
```

**Environment Variables:**
The `mcp.json` configuration explicitly sets `PATH` and `IDF_PATH` for servers that need ESP-IDF tools:
- `idf-builder` → Full ESP-IDF environment (build tools, Python env)
- `device-test` → ESP-IDF tools (esptool for flashing)
- `system` → No ESP-IDF dependency

**Why This Matters:**
Each server's subprocess calls (like `esptool.py` for flashing) need to find the right tools. By setting `env.PATH` in the config, we ensure tools are found even when running in isolated venvs.

## Re-running Setup

You can safely re-run setup at any time:

```bash
bash setup.sh
```

It will:
- Recreate virtual environments
- Detect any environment changes
- Update dependencies
- Refresh configuration (preserving custom additions)
- Validate everything

## Environment Variables

Setup respects these environment variables:

- `IDF_PATH` - ESP-IDF installation directory
- `PATH` - Updated to include tool locations
- `PYTHON_EXECUTABLE` - Python interpreter location

## Supported Platforms

- **macOS** 10.15+ (Darwin)
  - Intel and Apple Silicon (M1/M2/M3)
  
- **Linux**
  - Ubuntu 18.04+
  - Debian 10+
  - Fedora 30+

## Support

For help:

1. Check the **[SETUP_GUIDE.md](./SETUP_GUIDE.md)** troubleshooting section
2. Review individual tool READMEs in `examples/*/README.md`
3. Validate setup with `python3 setup/validate_setup.py`
4. Check Cursor extension logs
