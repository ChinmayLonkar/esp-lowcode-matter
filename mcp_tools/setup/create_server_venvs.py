#!/usr/bin/env python3
"""
Create isolated virtual environments for each MCP server.
Each server gets its own Python environment with dependencies installed.
"""

import os
import sys
import subprocess
import venv
from pathlib import Path
from typing import List, Tuple

class ServerVenvManager:
    """Manages virtual environments for MCP servers."""
    
    def __init__(self, mcp_tools_dir: str):
        self.mcp_tools_dir = mcp_tools_dir
        self.examples_dir = os.path.join(mcp_tools_dir, "examples")
    
    def _find_servers(self) -> List[Tuple[str, str]]:
        """Find all MCP servers with server.py."""
        servers = []
        
        if not os.path.isdir(self.examples_dir):
            return servers
        
        for server_name in os.listdir(self.examples_dir):
            server_dir = os.path.join(self.examples_dir, server_name)
            
            if not os.path.isdir(server_dir):
                continue
            
            # Skip template directory
            if server_name == "template":
                continue
            
            server_py = os.path.join(server_dir, "server.py")
            if os.path.isfile(server_py):
                servers.append((server_name, server_dir))
        
        return servers
    
    def _create_venv(self, venv_path: str) -> bool:
        """Create a virtual environment."""
        try:
            print(f"    Creating virtual environment...")
            venv.create(venv_path, with_pip=True, clear=True)
            return True
        except Exception as e:
            print(f"    ✗ Failed to create venv: {e}")
            return False
    
    def _install_requirements(self, venv_path: str, requirements_file: str) -> bool:
        """Install requirements in the virtual environment."""
        if not os.path.isfile(requirements_file):
            print(f"    ⚠ No requirements.txt found, skipping")
            return True
        
        # Determine pip path based on OS
        if sys.platform == "win32":
            pip_path = os.path.join(venv_path, "Scripts", "pip")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")
        
        try:
            print(f"    Installing requirements...")
            result = subprocess.run(
                [pip_path, "install", "-q", "-r", requirements_file],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"    ✓ Requirements installed")
                return True
            else:
                print(f"    ✗ Installation failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            print(f"    ✗ Installation timed out")
            return False
        except Exception as e:
            print(f"    ✗ Installation error: {e}")
            return False
    
    def _install_core_dependencies(self, venv_path: str) -> bool:
        """Install core MCP framework dependencies."""
        # Determine pip path based on OS
        if sys.platform == "win32":
            pip_path = os.path.join(venv_path, "Scripts", "pip")
        else:
            pip_path = os.path.join(venv_path, "bin", "pip")
        
        # Core dependencies for all servers
        core_packages = [
            "fastmcp>=0.1.0",
            "pydantic>=2.0.0",
        ]
        
        try:
            print(f"    Installing core MCP framework...")
            result = subprocess.run(
                [pip_path, "install", "-q"] + core_packages,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                print(f"    ✓ Core framework installed")
                return True
            else:
                print(f"    ✗ Core installation failed: {result.stderr}")
                return False
        except Exception as e:
            print(f"    ✗ Core installation error: {e}")
            return False
    
    def setup_server_venv(self, server_name: str, server_dir: str) -> bool:
        """Set up virtual environment for a single server."""
        print(f"\n  Setting up {server_name}...")
        
        venv_path = os.path.join(server_dir, "venv")
        requirements_file = os.path.join(server_dir, "requirements.txt")
        
        # Create venv
        if not self._create_venv(venv_path):
            return False
        
        # Install core dependencies
        if not self._install_core_dependencies(venv_path):
            return False
        
        # Install server-specific requirements
        if not self._install_requirements(venv_path, requirements_file):
            return False
        
        print(f"  ✓ {server_name} environment ready")
        return True
    
    def setup_all(self) -> bool:
        """Set up virtual environments for all servers."""
        print("\nCreating isolated environments for each server...")
        
        servers = self._find_servers()
        
        if not servers:
            print("  No servers found")
            return False
        
        failed = []
        for server_name, server_dir in servers:
            if not self.setup_server_venv(server_name, server_dir):
                failed.append(server_name)
        
        if failed:
            print(f"\n✗ Failed to set up environments: {', '.join(failed)}")
            return False
        
        print(f"\n✓ All {len(servers)} server environments created")
        return True


def main():
    """Main entry point."""
    # Get mcp_tools directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mcp_tools_dir = os.path.dirname(script_dir)
    
    manager = ServerVenvManager(mcp_tools_dir)
    success = manager.setup_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

