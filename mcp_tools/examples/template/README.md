# MCP Tool Template

This directory contains a template for creating a custom tool that follows the [Model Context Protocol (MCP)](https://github.com/ai-extensions/model-context-protocol). The template provides a starting point for creating both a server (which exposes your tools via MCP) and a client (which can call those tools).

## Structure

- `server.py` - MCP server that exposes your tools via stdio
- `client.py` - Client that can call tools on the server via stdio
- `server_http.py` - HTTP version of the MCP server
- `client_http.py` - HTTP client for connecting to the server
- `README.md` - This file

## Usage

### Running the Server

The server script exposes several tools via the Model Context Protocol:

```bash
python server.py
```

The server will start listening for MCP commands via stdio transport.

For HTTP access, you can run:

```bash
python server_http.py
```

This will start an HTTP server on port 8000 by default. You can configure the host and port:

```bash
python server_http.py --host 127.0.0.1 --port 8080
```

### Running the Client

The client script provides an interactive interface to call tools on the server:

```bash
python client.py
```

The client supports the following commands:
- `process TEXT` - Process text (sample tool)
- `save KEY VALUE` - Save data to the database
- `get KEY` - Get data from the database
- `fetch URL` - Fetch data from a URL
- `history [TOOL_NAME]` - Get tool history from server
- `local_history [TOOL_NAME]` - Get local tool call history
- `help` - Show help information

For HTTP access, you can run:

```bash
python client_http.py --url http://localhost:8000
```

The HTTP client has the same interface as the stdio client but connects to the server over HTTP.

> **Important**: When connecting to the HTTP server, the client automatically appends `/sse` to the URL if not already present. This is required for Server-Sent Events (SSE) communication in the MCP protocol.

You can also specify the output format:

```bash
python client_http.py --url http://localhost:8000 --format json
```

### Using with Large Language Models

These MCP tools are designed to be used with LLMs that support the Model Context Protocol, such as Claude and other assistants.

#### Configuring Claude Desktop

To add the tools to Claude Desktop, edit the `claude_desktop_config.json` file:

```json
{
  "mcpServers": {
    "custom-tool": {
      "command": "python",
      "args": [
        "/absolute/path/to/your/tool/server.py"
      ]
    }
  }
}
```

#### Configuring Cursor

To add the tools to Cursor, edit the tools configuration file:

```json
{
  "tools": [
    {
      "name": "custom-tool",
      "command": "python",
      "args": [
        "/absolute/path/to/your/tool/server.py"
      ]
    }
  ]
}
```

## Customizing the Template

### Adding a New Tool

To add a new tool to your MCP server, follow these steps:

1. Open `server.py`
2. Add a new function with the `@mcp.tool()` decorator:

```python
@mcp.tool(name="your_tool_name")
def your_tool_name(param1: str, param2: int) -> Dict[str, Any]:
    """Description of your tool.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Result information
    """
    # Your tool implementation
    result = do_something(param1, param2)

    # Log to database if needed
    db.record_tool_call(
        tool_name="your_tool_name",
        parameters={"param1": param1, "param2": param2},
        status="success"
    )

    return result
```

### Updating the Client

If you add a new tool to the server, you may want to add a corresponding command to the client. To do so, add a new condition to the command handler in `client.py` and `client_http.py`:

```python
elif command == "your_command":
    if len(parts) < 3:
        output.error("Missing parameters")
        continue

    param1 = parts[1]
    param2 = int(parts[2])

    output.info(f"Calling your tool with {param1} and {param2}")
    result = await client.call_tool("your_tool_name", {"param1": param1, "param2": param2})
    output.output(json.loads(result[0].text) if result else {})
```

## Database and Storage

The template includes a SQLite database for storing tool call history and other data. The database files are stored in the `data/` directory.

## Networking

The template also includes a simple `ApiClient` for making HTTP requests, which you can use in your tools to fetch data from external services.

## HTTP vs. Stdio Transport

The template provides two transport methods for MCP:

1. **Stdio Transport** (server.py, client.py): This uses standard input/output for communication between the client and server. This is the preferred method for integrating with LLMs.

2. **HTTP Transport** (server_http.py, client_http.py): This uses HTTP for communication, allowing you to host the server on a different machine or expose it as a web service. This can be useful for:
   - Remote access to tools
   - Integrating with web applications
   - Scaling across multiple machines
   - Load balancing and high availability
