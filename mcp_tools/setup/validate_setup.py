#!/usr/bin/env python3
"""
Setup Validator for MCP Tools
Validates installation, dependencies, and configuration files.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Tuple

class SetupValidator:
    """Validates MCP tools setup."""
    
    def __init__(self):
        self.mcp_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_dir = os.path.join(self.mcp_tools_dir, "config")
        self.issues = []
        self.warnings = []
    
    def check_directory_structure(self) -> bool:
        """Verify core directory structure."""
        print("\nChecking directory structure...")
        
        required_dirs = [
            ("config", os.path.join(self.mcp_tools_dir, "config")),
            ("setup", os.path.join(self.mcp_tools_dir, "setup")),
            ("examples", os.path.join(self.mcp_tools_dir, "examples")),
            ("components", os.path.join(self.mcp_tools_dir, "components")),
        ]
        
        all_ok = True
        for name, path in required_dirs:
            if os.path.isdir(path):
                print(f"  ✓ {name}/")
            else:
                print(f"  ✗ {name}/ - NOT FOUND")
                self.issues.append(f"Missing directory: {path}")
                all_ok = False
        
        return all_ok
    
    def check_configuration_files(self) -> bool:
        """Verify configuration files exist."""
        print("\nChecking configuration files...")
        
        required_files = [
            ("Template", os.path.join(self.config_dir, "config.template.json")),
            ("Detected Env", os.path.join(self.config_dir, "detected_environment.json")),
            ("Generated Config", os.path.join(self.config_dir, "mcp.json")),
        ]
        
        all_ok = True
        for name, path in required_files:
            if os.path.isfile(path):
                print(f"  ✓ {os.path.basename(path)}")
            else:
                if name == "Generated Config":
                    print(f"  ⚠ {os.path.basename(path)} - Will be generated")
                else:
                    print(f"  ✗ {name} - NOT FOUND")
                    self.issues.append(f"Missing file: {path}")
                    all_ok = False
        
        return all_ok
    
    def check_generated_config(self) -> bool:
        """Verify generated MCP configuration."""
        print("\nChecking generated configuration...")
        
        config_path = os.path.join(self.config_dir, "mcp.json")
        
        if os.path.isfile(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                
                servers = config.get("mcpServers", {})
                tools = ["idf-builder", "device-test", "system"]
                
                missing = [t for t in tools if t not in servers]
                
                if missing:
                    print(f"  ⚠ Missing servers in generated config: {', '.join(missing)}")
                    self.warnings.append(f"Config missing servers: {missing}")
                else:
                    print(f"  ✓ All required servers in generated config")
                    
                # Check that tools were discovered
                for server_name in tools:
                    if server_name in servers:
                        server_tools = servers[server_name].get("tools", [])
                        if server_tools:
                            print(f"  ✓ {server_name}: {len(server_tools)} tools")
                        else:
                            print(f"  ⚠ {server_name}: No tools discovered")
                    
                return True
            except Exception as e:
                print(f"  ✗ Error reading generated config: {e}")
                self.issues.append(f"Invalid generated config: {e}")
                return False
        else:
            print(f"  ✗ Generated config not found at {config_path}")
            self.issues.append("Generated config file missing")
            return False
        
        return True
    
    def check_tool_structure(self) -> bool:
        """Verify tool directory structures."""
        print("\nChecking tool structures...")
        
        tools = ["idf-builder", "device-test", "system"]
        all_ok = True
        
        for tool in tools:
            tool_dir = os.path.join(self.mcp_tools_dir, "examples", tool)
            
            if not os.path.isdir(tool_dir):
                print(f"  ✗ {tool}/ - NOT FOUND")
                self.issues.append(f"Missing tool directory: {tool_dir}")
                all_ok = False
                continue
            
            # Check server.py
            server_py = os.path.join(tool_dir, "server.py")
            if not os.path.isfile(server_py):
                print(f"  ✗ {tool}/server.py - NOT FOUND")
                self.issues.append(f"Missing {tool} server.py")
                all_ok = False
            else:
                print(f"  ✓ {tool}/")
        
        return all_ok
    
    def check_dependencies(self) -> bool:
        """Verify critical dependencies are installed."""
        print("\nChecking dependencies...")
        
        packages = [
            ("fastmcp", "FastMCP framework"),
            ("pydantic", "Pydantic validation"),
            ("serial", "PySerial (device communication)"),  # Note: package 'pyserial' imports as 'serial'
        ]
        
        all_ok = True
        for package, name in packages:
            try:
                __import__(package)
                print(f"  ✓ {name}")
            except ImportError:
                print(f"  ✗ {name} - NOT INSTALLED")
                self.issues.append(f"Missing package: {package}")
                all_ok = False
        
        return all_ok
    
    def check_esp_idf(self) -> bool:
        """Check ESP-IDF installation (optional but recommended)."""
        print("\nChecking ESP-IDF (optional)...")
        
        detected_env_path = os.path.join(self.config_dir, "detected_environment.json")
        
        if os.path.isfile(detected_env_path):
            try:
                with open(detected_env_path, "r") as f:
                    env = json.load(f)
                
                if env.get("esp_idf"):
                    print(f"  ✓ ESP-IDF found: {env['esp_idf']}")
                    if env.get("esp_idf_version"):
                        print(f"    Version: {env['esp_idf_version']}")
                    return True
                else:
                    print(f"  ⚠ ESP-IDF not detected (needed for idf-builder tool)")
                    self.warnings.append("ESP-IDF not detected")
                    return False
            except Exception as e:
                print(f"  ⚠ Could not read environment: {e}")
        
        return True
    
    def validate_json_syntax(self) -> bool:
        """Validate JSON syntax of config files."""
        print("\nValidating JSON files...")
        
        json_files = [
            os.path.join(self.config_dir, "config.template.json"),
            os.path.join(self.config_dir, "mcp.json"),
        ]
        
        all_ok = True
        for json_file in json_files:
            if not os.path.isfile(json_file):
                continue
            
            try:
                with open(json_file, "r") as f:
                    json.load(f)
                print(f"  ✓ {os.path.basename(json_file)}")
            except json.JSONDecodeError as e:
                print(f"  ✗ {os.path.basename(json_file)}: {e}")
                self.issues.append(f"Invalid JSON in {json_file}: {e}")
                all_ok = False
            except Exception as e:
                print(f"  ✗ {os.path.basename(json_file)}: {e}")
                self.issues.append(f"Error reading {json_file}: {e}")
                all_ok = False
        
        return all_ok
    
    def validate_all(self) -> bool:
        """Run all validation checks."""
        all_ok = True
        
        all_ok &= self.check_directory_structure()
        all_ok &= self.check_configuration_files()
        all_ok &= self.check_tool_structure()
        all_ok &= self.check_dependencies()
        all_ok &= self.check_esp_idf()
        all_ok &= self.check_generated_config()
        all_ok &= self.validate_json_syntax()
        
        return all_ok
    
    def print_summary(self) -> None:
        """Print validation summary."""
        print("\n" + "=" * 50)
        
        if self.issues:
            print(f"\n✗ ISSUES FOUND ({len(self.issues)}):")
            for issue in self.issues:
                print(f"  - {issue}")
        
        if self.warnings:
            print(f"\n⚠ WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
        
        if not self.issues:
            print("\n✓ All validation checks passed!")
        
        print("=" * 50 + "\n")


def main():
    """Main entry point."""
    validator = SetupValidator()
    
    if not validator.validate_all():
        validator.print_summary()
        return 1
    
    validator.print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
