# MCP Components

This directory contains reusable components for building MCP (Model Context Protocol) tools.

## Available Components

- `path_setup.py`: Utility for setting up Python import paths correctly
- `database.py`: Database module with SQLite support for data storage and tool history
- `network.py`: HTTP client and API utilities for making external requests
- `output.py`: Output formatting utilities for consistent data presentation
- `async_utils.py`: Utilities for asynchronous operations and task management

## Usage

### Path Setup

```python
from mcp_tools.components.path_setup import setup_path

# Set up the Python path
setup_path()

# Now you can import other modules regardless of execution context
```

### Database

```python
from mcp_tools.components.database import ToolDatabase

# Create a database for your tool
db = ToolDatabase("path/to/your/tool/data.db")

# Store and retrieve data
db.store_data("config", {"api_key": "xyz123"}, "my-tool")
config = db.get_data("config", "my-tool")

# Record tool calls
db.record_tool_call(
    tool_name="my-function",
    parameters={"param1": "value1"},
    status="success"
)

# Get tool history
history = db.get_tool_history(tool_name="my-function", limit=10)
```

### Network

```python
import asyncio
from mcp_tools.components.network import ApiClient

async def fetch_data():
    async with ApiClient("https://api.example.com") as client:
        # Make API calls
        data = await client.get("/endpoint")
        response = await client.post("/create", json_data={"key": "value"})

        # Handle pagination
        all_items = await client.paginate("/items", page_size=50)

    return data

# Run the async function
asyncio.run(fetch_data())
```

### Output Formatting

```python
from mcp_tools.components.output import get_output_manager

# Create an output manager with desired format
output = get_output_manager(format="table", color=True)

# Display data in the selected format
data = [{"id": 1, "name": "Item 1"}, {"id": 2, "name": "Item 2"}]
output.output(data)

# Use status messages
output.info("Processing...")
output.success("Completed successfully")
output.error("An error occurred")
output.warning("Resource running low")
```

### Async Utilities

```python
import asyncio
from mcp_tools.components.async_utils import run_with_timeout, TaskManager

# Run a task with timeout
result = await run_with_timeout(my_async_function(), timeout=5.0)

# Manage multiple tasks
task_manager = TaskManager()
task_manager.add_task(task1())
task_manager.add_task(task2())
results = await task_manager.gather()
```

## Installation

```bash
pip install -r requirements.txt
```
