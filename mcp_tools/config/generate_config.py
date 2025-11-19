#!/usr/bin/env python3
"""
Configuration Generator for MCP Tools
Generates Cursor-compatible mcp.json configuration from template using detected_environment.json.
"""

import os
import sys
import json
from typing import Dict, Any


class ConfigGenerator:
    """Generates MCP configuration files from template using detected environment."""

    def __init__(self):
        self.config_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(self.config_dir, "config.template.json")
        self.detected_env_path = os.path.join(self.config_dir, "detected_environment.json")
        self.env = self._load_detected_environment()

    # ------------------------------------------------------------
    # Environment and path helpers
    # ------------------------------------------------------------
    def _load_detected_environment(self) -> Dict[str, Any]:
        """Load detected environment from JSON file."""
        if os.path.isfile(self.detected_env_path):
            try:
                with open(self.detected_env_path, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load detected environment: {e}")
        return {}

    def _get_idf_version(self) -> str:
        """Return ESP-IDF version from detected environment."""
        return self.env.get("esp_idf_version", "")

    def _get_python_env_path(self) -> str:
        """Return the directory of the Python executable from detected environment."""
        python_path = self.env.get("python", "")
        return os.path.dirname(python_path) if python_path else ""

    def _build_base_path_env(self) -> str:
        """Construct a base PATH containing IDF tools and current system PATH."""
        idf_path = self.env.get("esp_idf", "")
        current_path = os.environ.get("PATH", "")
        path_elements = []

        # Always include IDF tools if known
        if idf_path:
            tools_dir = os.path.join(idf_path, "tools")
            path_elements.append(tools_dir)

            # Add key IDF components if they exist
            for comp in ["components/espcoredump", "components/partition_table", "components/app_update"]:
                path_elements.append(os.path.join(idf_path, comp))

        return os.pathsep.join(path_elements + [current_path])

    # ------------------------------------------------------------
    # Template substitution
    # ------------------------------------------------------------
    def _substitute_variables(self, text: str) -> str:
        """Substitute placeholders with detected environment values."""
        substitutions = {
            "{MCP_TOOLS_DIR}": os.path.dirname(self.config_dir),
            "{ESP_IDF_PATH}": self.env.get("esp_idf", ""),
            "{IDF_PYTHON_ENV_PATH}": self.env.get("idf_python_env_path", ""),
            "{PATH_WITH_IDF_TOOLS}": self._build_base_path_env(),
            "{PYTHON_EXECUTABLE}": self.env.get("python", sys.executable),
            "{ESPTOOL_PATH}": self.env.get("esptool", ""),
            "{CMAKE_PATH}": self.env.get("cmake", ""),
            "{GIT_PATH}": self.env.get("git", ""),
        }

        result = text
        for placeholder, value in substitutions.items():
            result = result.replace(placeholder, value)
        return result

    # ------------------------------------------------------------
    # Config construction
    # ------------------------------------------------------------
    def generate_from_template(self) -> Dict[str, Any]:
        """Load template and generate configuration with substitutions."""
        if not os.path.isfile(self.template_path):
            raise FileNotFoundError(f"Template not found: {self.template_path}")

        with open(self.template_path, "r") as f:
            template_content = f.read()

        substituted = self._substitute_variables(template_content)
        config = json.loads(substituted)

        # Add per-server PATH modifications
        self._inject_venv_paths(config)
        return config

    def _inject_venv_paths(self, config: Dict[str, Any]) -> None:
        """
        For each server, prepend its venv/bin path to PATH in env.
        Example:
          venv = /path/to/examples/device-test/venv/bin
          PATH = /path/to/examples/device-test/venv/bin:<idf_tools>:<system_path>
        """
        base_path = self._build_base_path_env()

        servers = config.get("servers", {})
        for name, server in servers.items():
            command = server.get("command", "")
            if not command:
                continue

            # venv/bin directory is where the python executable lives
            venv_bin = os.path.dirname(command)

            env_section = server.setdefault("env", {})
            existing_path = env_section.get("PATH", base_path)
            env_section["PATH"] = os.pathsep.join([venv_bin, base_path])

            # Fill IDF environment if missing
            env_section.setdefault("IDF_PATH", self.env.get("esp_idf", ""))
            env_section.setdefault("IDF_PYTHON_ENV_PATH", self.env.get("idf_python_env_path", ""))

    # ------------------------------------------------------------
    # Output
    # ------------------------------------------------------------
    def save_config(self, config: Dict[str, Any], output_path: str) -> None:
        """Save configuration to file."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(config, f, indent=2)
        print(f"✓ Configuration saved to {output_path}")

    def generate(self) -> None:
        """Generate portable configuration file."""
        print("\nGenerating configuration...")

        config = self.generate_from_template()
        base_config_path = os.path.join(self.config_dir, "mcp.json")
        self.save_config(config, base_config_path)

        print(f"\n{'='*60}")
        print(f"✓ Configuration generated: {base_config_path}")
        print(f"{'='*60}")
        print("\nTo use this configuration in Cursor:")
        print("1. Open Cursor Settings → Extensions → Model Context Protocol")
        print("2. Click 'Edit Config' or open ~/.cursor/mcp.json")
        print("3. Copy the mcpServers section from:")
        print(f"   {base_config_path}")
        print("4. Paste into your ~/.cursor/mcp.json and restart Cursor")
        print(f"{'='*60}\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main():
    """Main entry point."""
    try:
        generator = ConfigGenerator()
        generator.generate()
        return 0
    except Exception as e:
        print(f"✗ Configuration generation failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
