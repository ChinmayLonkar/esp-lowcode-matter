#!/usr/bin/env python3
"""
Script to create a new MCP tool from the template.
"""

import os
import sys
import shutil
import re
import argparse
import json

def create_tool(tool_name, tool_display_name=None):
    """
    Create a new MCP tool from the template.

    Args:
        tool_name: Name of the tool (lowercase, hyphenated)
        tool_display_name: Display name of the tool (if different from tool_name)
    """
    # Get the script directory and base MCP directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_dir = os.path.dirname(os.path.dirname(script_dir))

    # Get correct paths
    examples_dir = os.path.join(mcp_dir, "mcp_tools", "examples")
    template_dir = os.path.join(examples_dir, "template")

    # Check if the template directory exists
    if not os.path.exists(template_dir):
        print(f"ERROR: Template directory not found: {template_dir}")
        return False

    # Create the new tool directory in examples folder
    new_tool_dir = os.path.join(examples_dir, tool_name)

    # Check if the new tool directory already exists
    if os.path.exists(new_tool_dir):
        print(f"ERROR: Tool directory already exists: {new_tool_dir}")
        return False

    # Create the new tool directory
    os.makedirs(new_tool_dir)

    # Set the display name if not provided
    if not tool_display_name:
        tool_display_name = tool_name.replace("-", " ").title()

    # Copy and update the template files
    for filename in os.listdir(template_dir):
        src_path = os.path.join(template_dir, filename)
        dst_path = os.path.join(new_tool_dir, filename)

        if os.path.isfile(src_path):
            # Read the template file
            with open(src_path, "r") as f:
                content = f.read()

            # Replace the placeholders with the new tool name
            content = content.replace("custom-tool", tool_name)
            content = content.replace("Custom Tool", tool_display_name)

            # Update class names
            content = content.replace("CustomTool", "".join(word.capitalize() for word in tool_name.split("-")))
            content = content.replace("ToolCommand", "".join(word.capitalize() for word in tool_name.split("-")) + "Command")

            # Write the updated content to the new file
            with open(dst_path, "w") as f:
                f.write(content)

            print(f"Created {dst_path}")
        elif os.path.isdir(src_path):
            # Handle directories
            if filename == "config":
                # Create config directory
                os.makedirs(dst_path, exist_ok=True)
                print(f"Created directory {dst_path}")

                # Copy and update config files
                for config_file in os.listdir(src_path):
                    src_config = os.path.join(src_path, config_file)
                    dst_config = os.path.join(dst_path, config_file)

                    if os.path.isfile(src_config) and config_file == "mcp.json":
                        # Handle mcp.json specially
                        try:
                            with open(src_config, "r") as f:
                                mcp_config = json.load(f)

                            # Update the configuration with correct tool name and path
                            if "mcpServers" in mcp_config:
                                # Remove the existing template entry and add our new one
                                mcp_config["mcpServers"] = {
                                    tool_name: {
                                        "command": "python3",
                                        "args": [
                                            os.path.join(new_tool_dir, "server.py")
                                        ]
                                    }
                                }

                            # Write the updated JSON
                            with open(dst_config, "w") as f:
                                json.dump(mcp_config, f, indent=4)

                            print(f"Created and configured {dst_config}")
                        except Exception as e:
                            print(f"WARNING: Error updating mcp.json: {e}")
                            # Fallback to simple copy if JSON processing fails
                            with open(src_config, "r") as f:
                                content = f.read()
                            content = content.replace("custom-tool", tool_name)
                            content = content.replace("/Users/chirag/work/gitlab/extra_repos/yolo/mcp_tools/examples/template", new_tool_dir)
                            with open(dst_config, "w") as f:
                                f.write(content)
                            print(f"Created {dst_config} (fallback method)")
                    elif os.path.isfile(src_config):
                        # Copy and update other config files
                        with open(src_config, "r") as f:
                            content = f.read()

                        # Replace placeholders in config files
                        content = content.replace("custom-tool", tool_name)
                        content = content.replace("Custom Tool", tool_display_name)

                        with open(dst_config, "w") as f:
                            f.write(content)

                        print(f"Created {dst_config}")
            else:
                # Copy other directories
                shutil.copytree(src_path, dst_path)
                print(f"Copied directory {dst_path}")

    # Copy README template and customize it
    readme_template = os.path.join(script_dir, "README_TEMPLATE.md")
    if os.path.exists(readme_template):
        with open(readme_template, "r") as f:
            readme_content = f.read()

        # Replace placeholders
        readme_content = readme_content.replace("[Your Tool Name]", tool_display_name)

        # Write the README file
        readme_path = os.path.join(new_tool_dir, "README.md")
        with open(readme_path, "w") as f:
            f.write(readme_content)

        print(f"Created {readme_path}")

    print(f"\nSuccessfully created new MCP tool: {tool_name}")
    print(f"Tool directory: {new_tool_dir}")
    print("\nNext steps:")
    print(f"1. Implement your tools in {new_tool_dir}/server.py")
    print(f"2. Update the client interface in {new_tool_dir}/client.py")
    print(f"3. Update the config files in {new_tool_dir}/config/")
    print(f"4. Customize the README.md file with your tool's documentation")
    print(f"5. Run the server with 'python {new_tool_dir}/server.py'")
    print(f"6. Run the client with 'python {new_tool_dir}/client.py'")

    return True

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Create a new MCP tool from the template.")
    parser.add_argument("tool_name", help="Name of the tool (lowercase, hyphenated)")
    parser.add_argument("--display-name", help="Display name of the tool (if different from tool_name)")

    args = parser.parse_args()

    # Validate the tool name
    if not re.match(r'^[a-z][a-z0-9-_]*$', args.tool_name):
        print("ERROR: Tool name must be lowercase, hyphenated, and start with a letter.")
        sys.exit(1)

    # Create the tool
    success = create_tool(args.tool_name, args.display_name)

    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
