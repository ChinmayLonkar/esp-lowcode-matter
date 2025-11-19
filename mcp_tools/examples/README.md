# MCP Tool Templates and Examples

This directory contains templates and examples for creating new MCP tools.

## Available Templates

- `template/`: Basic template for creating a new MCP tool

## Available Examples

- `number-adder/`: Simple example of a tool that adds two numbers together

## Using a Template

The easiest way to use a template is with the `create_tool.py` script:

```bash
# Run from the examples directory
python create_tool.py my-tool
```

Or you can manually copy a template directory and customize it:

```bash
# Copy the template
cp -r template my-tool

# Customize the files
# - Replace "custom-tool" with your tool name
# - Update class names
# - Implement your tools
```

## Running an Example

To run the number-adder example:

```bash
# Change to the example directory
cd number-adder

# Start the server
python server.py

# In another terminal, run the client
python client.py
```

## Creating Your Own Templates

To create your own template:

1. Create a new directory in this directory
2. Add the necessary files for your template
3. Use placeholders for values that should be replaced when creating a tool:
   - "custom-tool" for the tool name
   - "Custom Tool" for the display name
   - "CustomTool" for class name prefixes
   - "ToolCommand" for command handler class names

The `create_tool.py` script will replace these placeholders with the appropriate values when creating a new tool.
