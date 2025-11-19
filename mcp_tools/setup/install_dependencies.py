#!/usr/bin/env python3
"""
Dependency Installer for MCP Tools
Installs and validates all required packages for MCP servers and tools.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import List, Tuple

class DependencyInstaller:
    """Manages installation of MCP tool dependencies."""
    
    def __init__(self):
        self.mcp_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.python_exe = sys.executable
    
    def _find_requirements_files(self) -> List[Tuple[str, str]]:
        """Find all requirements.txt files in the project."""
        files = []
        
        # Core requirements
        core_req = os.path.join(self.mcp_tools_dir, "requirements.txt")
        if os.path.isfile(core_req):
            files.append(("Core MCP Framework", core_req))
        
        # Component requirements
        components_req = os.path.join(self.mcp_tools_dir, "components", "requirements.txt")
        if os.path.isfile(components_req):
            files.append(("MCP Components", components_req))
        
        # Tool-specific requirements
        examples_dir = os.path.join(self.mcp_tools_dir, "examples")
        if os.path.isdir(examples_dir):
            for tool_dir in os.listdir(examples_dir):
                tool_path = os.path.join(examples_dir, tool_dir)
                if not os.path.isdir(tool_path):
                    continue
                
                tool_req = os.path.join(tool_path, "requirements.txt")
                if os.path.isfile(tool_req):
                    tool_name = tool_dir.replace("-", " ").title()
                    files.append((f"Tool: {tool_name}", tool_req))
        
        return files
    
    def _install_requirements(self, label: str, requirements_file: str) -> bool:
        """Install packages from a requirements.txt file."""
        print(f"\n  Installing {label}...")
        
        try:
            result = subprocess.run(
                [self.python_exe, "-m", "pip", "install", "-q", "-r", requirements_file],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"    ✓ {label} installed")
                return True
            else:
                print(f"    ✗ {label} installation failed:")
                print(f"    {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print(f"    ✗ {label} installation timed out")
            return False
        except Exception as e:
            print(f"    ✗ {label} installation error: {e}")
            return False
    
    def _verify_installation(self, package: str) -> bool:
        """Verify a package is installed and importable."""
        try:
            __import__(package)
            return True
        except ImportError:
            return False
    
    def install_all(self) -> bool:
        """Install all dependencies."""
        print("\nInstalling dependencies...")
        
        requirements_files = self._find_requirements_files()
        
        if not requirements_files:
            print("  Warning: No requirements.txt files found")
            return False
        
        failed = []
        for label, req_file in requirements_files:
            if not self._install_requirements(label, req_file):
                failed.append(label)
        
        if failed:
            print(f"\n✗ Failed to install: {', '.join(failed)}")
            return False
        
        print("\n✓ All dependencies installed successfully")
        return True
    
    def verify_critical_packages(self) -> bool:
        """Verify critical packages are installed."""
        print("\nVerifying critical packages...")
        
        critical_packages = [
            ("fastmcp", "FastMCP"),
            ("pydantic", "Pydantic"),
            ("serial", "PySerial (for device-test tool)"),  # Note: package 'pyserial' imports as 'serial'
        ]
        
        all_ok = True
        for package, name in critical_packages:
            if self._verify_installation(package):
                print(f"  ✓ {name}")
            else:
                print(f"  ✗ {name} - NOT INSTALLED")
                all_ok = False
        
        return all_ok


def main():
    """Main entry point."""
    installer = DependencyInstaller()
    
    # Install all dependencies
    if not installer.install_all():
        return 1
    
    # Verify critical packages
    if not installer.verify_critical_packages():
        print("\n⚠ Some packages are missing. Trying to install again...")
        if not installer.install_all():
            return 1
    
    print("\n✓ Dependency installation complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
