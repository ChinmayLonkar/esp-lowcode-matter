# MCP Tools Setup Guide

Complete guide for setting up MCP tools for Cursor integration on macOS and Linux systems.

## Quick Start

### 1. Prerequisites

Ensure you have the following installed:
- **Python 3.8+**: Check with `python3 --version`
- **pip**: Package manager (included with Python 3.4+)
- **git**: Version control (recommended)

### 2. Run Setup

```bash
cd PATH_TO_YOLO/yolo/mcp_tools
./setup.sh
```

The setup script will automatically:
1. Detect your system environment
2. Find ESP-IDF (if installed)
3. Create isolated virtual environments for each tool
4. Install all required dependencies
5. Generate configuration files
6. Validate the complete setup

### 3. Use the mcp.json in Cursor

After setup completes, copy paste the generated mcp.json file in "Tools & MCP" in cursor settings and restart Cursor to load the new MCP configuration:
- Close Cursor completely
- Reopen Cursor
- Check settings → Extensions → MCP to verify tools are loaded

### 4. Use the Tools

In Cursor, use the tools with the `@` prefix:
- `@idf-builder` - Build ESP32 projects
- `@device-test` - Test and flash ESP32 devices
- `@system` - File operations and documentation processing

## What Gets Set Up

### Directories Created

```
mcp_tools/
├── config/
│   ├── config.template.json          # Configuration template
│   ├── detected_environment.json      # Auto-detected environment
│   └── mcp.json                       # Generated portable config
├── setup/
│   └── (setup scripts)
├── examples/
│   ├── idf-builder/
│   │   └── venv/                      # Isolated Python environment
│   ├── device-test/
│   │   └── venv/                      # Isolated Python environment
│   └── system/
│       └── venv/                      # Isolated Python environment
└── ...
```

### Configuration Files

1. **`mcp_tools/config/mcp.json`** - Generated portable configuration
   - Auto-generated with your system paths
   - Contains all tool definitions with venv Python paths
   - Copy this to Cursor's MCP settings manually

2. **`mcp_tools/config/detected_environment.json`** - Environment info
   - Python path
   - ESP-IDF location and version
   - Tool locations (esptool, cmake, git)

3. **`mcp_tools/config/config.template.json`** - Configuration template
   - Base template used to generate mcp.json
   - Contains placeholders for environment-specific values

## Environment Detection

The setup script automatically detects:

### Python Environment
- Python 3 executable path
- Required version (3.8+)
- Virtual environment support

### ESP-IDF (Optional)
- Checks locally installed ESP-IDF versions
- Asks user to select the IDF version

### Tools
- **esptool.py**: ESP32 flashing tool
- **CMake**: Build system (optional)
- **Git**: Version control (optional)

## Dependency Installation

### Isolated Virtual Environments

Each MCP server runs in its own Python virtual environment to prevent dependency conflicts:

**Benefits:**
- ✅ No dependency conflicts between servers
- ✅ Clean system Python (no global pollution)
- ✅ Easy to update individual servers
- ✅ Portable - copy entire directory to another machine
- ✅ Each tool can have different library versions

### Environment Configuration

**Critical for venv isolation:** Each server that uses subprocess calls to external tools (like `esptool.py`) must have the correct `PATH` set in `mcp.json`:

```json
"env": {
  "PATH": "/path/to/esp-idf/tools:/path/to/system/path",
  "IDF_PATH": "/path/to/esp-idf"
}
```

**Why this matters:**
- When a server runs in its venv, subprocess calls inherit the venv's environment
- Without proper `PATH` configuration, tools like `esptool.py` won't be found
- The setup script automatically generates the correct `PATH` with ESP-IDF tools
- `device-test` includes `esptool` in its venv AND sets PATH as a fallback

**Tool Priority** (for `device-test` flashing):
1. Venv's `esptool` (installed via pip in venv)
2. System PATH's `esptool.py`
3. ESP-IDF's esptool (`$IDF_PATH/components/esptool_py/esptool/esptool.py`)
4. Common system locations

## Troubleshooting

### Issue: Setup fails to find Python

**Symptom**: `Python 3 is not installed` error

**Solution**:
```bash
# Install Python 3.12+ from https://www.python.org or Homebrew
brew install python3

# Verify installation
python3 --version
```

### Issue: Cursor doesn't show the MCP tools

**Symptom**: `@idf-builder`, `@device-test`, `@system` not available

**Solutions**:

1. **Restart Cursor completely**
   - Close Cursor from dock (not just window)
   - Reopen Cursor

2. **Check configuration file**
   ```bash
   cat ~/.cursor/mcp.json
   ```
   Should show the three tools configured.

3. **Re-run setup**
   ```bash
   cd PATH_TO_YOLO/yolo/mcp_tools
   bash setup.sh
   ```

4. **Check Cursor settings**
   - Open Cursor settings
   - Go to Extensions → MCP
   - Verify tools are listed and enabled

### Issue: idf-builder tool shows "ESP-IDF not found"

**Symptom**: idf-builder unavailable or errors about ESP-IDF

**Solution**: Set IDF_PATH environment variable
```bash
# Find your ESP-IDF location
find ~ -name "idf.py" -path "*/tools/*" 2>/dev/null

# Export the path (add to ~/.zshrc or ~/.bash_profile)
export IDF_PATH="/path/to/your/esp-idf"

# Re-run setup
cd PATH_TO_YOLO/yolo/mcp_tools
bash setup.sh
```

### Issue: Device-test tool can't find serial ports

**Symptom**: `list_serial_ports` returns empty list

**Solution**:
1. Connect ESP32 device via USB
2. Wait 2 seconds for driver initialization
3. Try again

On macOS, common serial port patterns:
- `/dev/tty.usbserial-*` (FTDI chips)
- `/dev/tty.SLAB_USBtoUART*` (CP210x chips)
- `/dev/tty.CH34*` (CH340 chips)

### Issue: Dependency installation fails

**Symptom**: `pip install` errors during setup

**Solutions**:

1. **Ensure pip is up to date**
   ```bash
   python3 -m pip install --upgrade pip
   ```

2. **Check internet connection**
   ```bash
   ping pypi.org
   ```

3. **Clear pip cache**
   ```bash
   python3 -m pip cache purge
   ```

4. **Recreate virtual environments**
   ```bash
   cd PATH_TO_YOLO/yolo/mcp_tools
   python3 setup/create_server_venvs.py
   ```

### Issue: Virtual environment not working

**Symptom**: Tools can't find installed packages

**Solutions**:

1. **Check venv exists**
   ```bash
   ls -la examples/*/venv/bin/python3
   ```

2. **Recreate venvs**
   ```bash
   cd PATH_TO_YOLO/yolo/mcp_tools
   rm -rf examples/*/venv
   python3 setup/create_server_venvs.py
   ```

3. **Verify Python paths in config**
   ```bash
   cat config/mcp.json | grep "command"
   ```
   Should show paths like `examples/idf-builder/venv/bin/python3`

### Issue: Configuration file shows empty values

**Symptom**: Generated `mcp.json` has empty paths or values

**Solution**: This is often expected if tools aren't installed. The setup validates that critical paths exist:
- ESP-IDF is optional (if not found, idf-builder is still configured but may warn)
- esptool is installed via pip automatically
- Other tools are optional enhancements

## Re-running Setup

You can safely re-run setup at any time:

```bash
cd PATH_TO_YOLO/yolo/mcp_tools
bash setup.sh
```

The setup will:
- Detect any changes in your environment
- Recreate virtual environments for each server
- Update dependencies in each venv
- Update configuration with new paths
- Regenerate `mcp_tools/config/mcp.json` with latest environment
- Reinstall dependencies (safe operation)

## Manual Configuration

### Manual Setup Without Script

If you prefer to set up manually:

1. **Create virtual environments**
   ```bash
   cd PATH_TO_YOLO/yolo/mcp_tools
   python3 setup/create_server_venvs.py
   ```

2. **Generate configuration**
   ```bash
   python3 config/generate_config.py
   ```

3. **Copy config to Cursor**
   ```bash
   # Copy the generated config to Cursor's MCP settings
   cat config/mcp.json
   # Paste into Cursor Settings → MCP Configuration
   ```

4. **Restart Cursor**

### Editing Configuration

If you need to manually edit the configuration:

1. **Edit the generated config**
   ```bash
   nano config/mcp.json
   # or use your preferred editor
   ```

2. **Validate JSON syntax**
   ```bash
   python3 -m json.tool config/mcp.json > /dev/null && echo "Valid"
   ```

3. **Copy to Cursor** and restart

**Note**: Each server's `command` should point to its venv Python:
```json
"command": "/absolute/path/to/examples/idf-builder/venv/bin/python3"
```

## Environment Variables

### IDF_PATH
Specifies the ESP-IDF installation directory.

```bash
export IDF_PATH="$HOME/esp/esp-idf"
```

### IDF_PYTHON_ENV_PATH
Path to Python environment for ESP-IDF tools (auto-detected by setup).

### PATH
Setup augments your PATH with ESP-IDF tool locations.

## Supported Operating Systems

- **macOS** 10.15+ (Darwin)
  - Intel and Apple Silicon (M1/M2/M3) supported
  
- **Linux**
  - Ubuntu 18.04+
  - Debian 10+
  - Fedora 30+
  - Other distributions with Python 3.8+

## Support and Issues

If you encounter problems:

1. **Check the Troubleshooting section above**

2. **Review setup output**
   ```bash
   cd PATH_TO_YOLO/yolo/mcp_tools
   bash setup.sh 2>&1 | tee setup.log
   ```

3. **Validate the setup**
   ```bash
   python3 setup/validate_setup.py
   ```

4. **Check MCP tool logs** in Cursor

## Advanced: Custom Configuration

### Using a Custom ESP-IDF Installation

If you have multiple ESP-IDF versions:

```bash
# Set the specific version before running setup
export IDF_PATH="/path/to/your/custom/esp-idf"
bash setup.sh
```

### Disabling Specific Tools

Edit `~/.cursor/mcp.json` and remove the tool from `mcpServers`:

```json
{
  "mcpServers": {
    // Remove "idf-builder" entry to disable it
    "device-test": { ... },
    "system": { ... }
  }
}
```

## Next Steps

After successful setup:

1. **Read tool documentation**
   - `mcp_tools/examples/idf-builder/README.md`
   - `mcp_tools/examples/device-test/README.md`
   - `mcp_tools/examples/system/README.md`

2. **Try example commands**
   - Start with `@system` to explore file operations
   - Move to `@device-test` for device operations
   - Use `@idf-builder` for firmware builds

3. **Explore the MCP Framework**
   - https://modelcontextprotocol.io/
   - Understand tool capabilities and limitations

## FAQ

**Q: Do I need to re-run setup after updating tools?**
A: Yes, for major updates. Run `bash setup.sh` to refresh dependencies and recreate venvs.

**Q: Can I use setup.sh on a different machine?**
A: Yes! Each machine will auto-detect its own environment. Virtual environments are recreated locally.

**Q: What if I don't have ESP-IDF installed?**
A: That's fine. The `device-test` and `system` tools work without it. You'll get a warning for `idf-builder`.

**Q: How do I remove/uninstall the tools?**
A: Remove the MCP configuration from Cursor settings. Optionally delete the `examples/*/venv/` directories to free up space.

**Q: Can I run multiple versions of the tools?**
A: Yes. You can have multiple MCP tool installations and configure each in Cursor with different identifiers. Each has isolated venvs.

**Q: Why use virtual environments for each tool?**
A: Prevents dependency conflicts. Each tool can have different library versions without interfering with others or your system Python.

**Q: Can I copy the entire directory to another machine?**
A: Yes! Run `setup.sh` on the new machine to recreate venvs for that system's Python environment.
