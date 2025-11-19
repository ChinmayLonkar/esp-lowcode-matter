# Number Adder MCP Tool

This is a simple MCP tool that adds two numbers together. It demonstrates how to create a basic MCP tool that performs a mathematical operation.

## Features

- Add two numbers (integers or floats) together
- Handles various number formats
- Returns a detailed JSON response with input values and result
- Automatically converts results to integers when appropriate
- Includes both stdio and HTTP interfaces

## Installation

To use this tool, follow these steps:

1. Clone the repository
2. Navigate to the tool directory
3. Ensure you have Python 3.6+ installed

## Usage

### Command Line Interface

Run the server:

```bash
python3 server.py
```

Run the client:

```bash
python3 client.py
```

In the client, you can add numbers using:

```
Command> add 5 7
```

Or directly on the command line:

```bash
python3 client.py 5 7
```

### HTTP Interface

Run the HTTP server:

```bash
python3 server_http.py
```

Run the HTTP client:

```bash
python3 client_http.py
```

Or directly add numbers via command line:

```bash
python3 client_http.py 5 7
```

## API Reference

### add_numbers

Adds two numbers together.

**Parameters:**
- `num1` (number): First number to add
- `num2` (number): Second number to add

**Returns:**
- JSON object containing:
  - `success` (boolean): Whether the operation was successful
  - `num1` (number): First input number
  - `num2` (number): Second input number
  - `result` (number): The sum of num1 and num2

## Development

### Directory Structure

```
number-adder/
├── server.py           # Main server implementation
├── client.py           # Command-line client
├── server_http.py      # HTTP server implementation
├── client_http.py      # HTTP client
├── configs/            # Tool configurations
└── data/               # Database storage (created at runtime)
```

### Extending the Tool

To add more mathematical operations:

1. Add a new tool function in `server.py`
2. Update the client interfaces
3. Update the config files

## Configuration

The tool includes configuration files for various LLM platforms:

- `configs/cursor.json` - Configuration for Cursor
- `configs/openai.json` - Configuration for OpenAI
- `configs/claude_desktop.json` - Configuration for Claude Desktop
- `configs/mcp_standard.json` - Standard MCP configuration

## License

[MIT License](LICENSE)
