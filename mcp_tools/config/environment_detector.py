#!/usr/bin/env python3
"""
Environment Detector for MCP Tools Setup
Automatically discovers and validates ESP-IDF, Python, and tool installations.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple

class EnvironmentDetector:
    """Detects and validates development environment for MCP tools."""
    
    def __init__(self):
        self.detected = {
            "os": sys.platform,
            "python": self._detect_python(),
            "esp_idf": None,
            "esp_idf_version": None,
            "esptool": None,
            "cmake": None,
            "git": None,
        }
    
    def _detect_python(self) -> str:
        """Get Python executable path."""
        return sys.executable
    
    def _run_command(self, cmd: list) -> Tuple[bool, str]:
        """Run command and return success status and output."""
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)
    
    def _find_in_path(self, executable: str) -> Optional[str]:
        """Find executable in PATH."""
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            exe_path = os.path.join(path_dir, executable)
            if os.path.isfile(exe_path) and os.access(exe_path, os.X_OK):
                return exe_path
        return None

    def detect_esp_idf(self) -> Optional[str]:
        """Detect ESP-IDF installation by checking IDF_PATH, idf_env.json, or PATH."""

        # 1. Check environment variable
        if "IDF_PATH" in os.environ:
            idf_path = os.environ["IDF_PATH"]
            if os.path.isdir(idf_path):
                self.detected["esp_idf"] = idf_path
                self._detect_esp_idf_version(idf_path)
                return idf_path
            else:
                print(f"Warning: IDF_PATH is set but path does not exist: {idf_path}")

        # 2. Check ~/.espressif/idf_env.json
        idf_env_json = os.path.expanduser("~/.espressif/idf-env.json")
        if os.path.isfile(idf_env_json):
            try:
                with open(idf_env_json, "r") as f:
                    idf_env = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {idf_env_json} is not a valid JSON file.")
                idf_env = {}

            idf_entries = idf_env.get("idfInstalled", {})
            if not idf_entries:
                print("No ESP-IDF installations found in idf_env.json.")
            else:
                valid_versions = {}

                for install_path, info in idf_entries.items():
                    declared_version = info.get("version")
                    idf_path = info.get("path", install_path)

                    if not idf_path or not os.path.isdir(idf_path):
                        print(f"Skipping invalid ESP-IDF path: {idf_path}")
                        continue

                    # Detect actual installed version from path using your existing function
                    self._detect_esp_idf_version(idf_path)
                    detected_version = self.detected.get("esp_idf_version", None)

                    # Prefer detected version if available
                    final_version = detected_version or declared_version or "unknown"

                    # Prevent duplicates for same folder
                    if idf_path not in valid_versions.values():
                        valid_versions[final_version] = idf_path

                if not valid_versions:
                    print("No valid ESP-IDF installations found (all paths invalid).")
                else:
                    print("\nAvailable ESP-IDF installations:")
                    for i, (ver, path) in enumerate(valid_versions.items(), 1):
                        declared_note = ""
                        # If declared version and detected version mismatch
                        json_ver = next((info.get("version") for p, info in idf_entries.items() if info.get("path") == path), None)
                        if json_ver and json_ver != ver:
                            declared_note = f" (declared {json_ver})"
                        print(f"{i}. v{ver}{declared_note}  →  {path}")

                    # Ask user to select
                    choice = input(f"Select ESP-IDF version [1-{len(valid_versions)}] (default: latest): ").strip()

                    try:
                        if choice:
                            selected_version = list(valid_versions.keys())[int(choice) - 1]
                        else:
                            selected_version = sorted(
                                valid_versions.keys(),
                                key=lambda v: [int(x) for x in v.split('.') if x.isdigit()]
                            )[-1]
                    except (ValueError, IndexError):
                        print("Invalid selection, defaulting to latest available version.")
                        selected_version = sorted(
                            valid_versions.keys(),
                            key=lambda v: [int(x) for x in v.split('.') if x.isdigit()]
                        )[-1]

                    idf_path = valid_versions[selected_version]
                    self.detected["esp_idf"] = idf_path
                    self.detected["esp_idf_version"] = selected_version
                    print(f"\nSelected ESP-IDF v{selected_version} at {idf_path}")
                    return idf_path
        else:
            print("ESP-IDF environment file not found at ~/.espressif/idf_env.json.")
            print("Please install ESP-IDF or set the IDF_PATH environment variable.")

        # 3. Try finding idf.py in PATH
        idf_py_path = self._find_in_path("idf.py")
        if idf_py_path:
            idf_root = os.path.dirname(os.path.dirname(idf_py_path))
            if os.path.isfile(os.path.join(idf_root, "tools", "idf.py")):
                self.detected["esp_idf"] = idf_root
                self._detect_esp_idf_version(idf_root)
                return idf_root

        print("ESP-IDF not detected. Please install ESP-IDF or configure IDF_PATH.")
        return None

    def _detect_esp_idf_version(self, idf_path: str) -> None:
        """Detect ESP-IDF version."""
        # Try version.cmake first (correct location in ESP-IDF)
        version_cmake = os.path.join(idf_path, "tools", "cmake", "version.cmake")
        if os.path.isfile(version_cmake):
            try:
                with open(version_cmake, "r") as f:
                    content = f.read()
                    # Extract version numbers using regex
                    import re
                    major = re.search(r'set\s*\(\s*IDF_VERSION_MAJOR\s+(\d+)', content)
                    minor = re.search(r'set\s*\(\s*IDF_VERSION_MINOR\s+(\d+)', content)
                    patch = re.search(r'set\s*\(\s*IDF_VERSION_PATCH\s+(\d+)', content)
                    
                    if major and minor and patch:
                        version = f"{major.group(1)}.{minor.group(1)}.{patch.group(1)}"
                        self.detected["esp_idf_version"] = version
                        return
            except Exception:
                pass
        
        # Fallback: try version.txt (alternative location)
        version_file = os.path.join(idf_path, "tools", "version.txt")
        if os.path.isfile(version_file):
            try:
                with open(version_file, "r") as f:
                    self.detected["esp_idf_version"] = f.read().strip()
            except Exception:
                pass
    
    def detect_esptool(self) -> Optional[str]:
        """Detect esptool.py installation."""
        # Try to find esptool.py in PATH
        esptool = self._find_in_path("esptool.py")
        if esptool:
            self.detected["esptool"] = esptool
            return esptool
        
        # Try to import esptool as Python package
        try:
            import esptool
            self.detected["esptool"] = "python -m esptool"
            return "python -m esptool"
        except ImportError:
            pass
        
        return None
    
    def detect_cmake(self) -> Optional[str]:
        """Detect CMake installation."""
        cmake = self._find_in_path("cmake")
        if cmake:
            success, version = self._run_command(["cmake", "--version"])
            if success:
                self.detected["cmake"] = cmake
                return cmake
        
        return None
    
    def detect_git(self) -> Optional[str]:
        """Detect Git installation."""
        git = self._find_in_path("git")
        if git:
            success, version = self._run_command(["git", "--version"])
            if success:
                self.detected["git"] = git
                return git
        
        return None
    
    def detect_all(self) -> Dict:
        """Detect all tools and return environment."""
        print("\nDetecting environment...")
        if self.detected['os'] == 'MACOS':
            os_name = 'MacOS'
        else:
            os_name = 'Linux'
        print(f"  OS: {os_name}")
        print(f"  Python: {self.detected['python']}")
        
        if self.detect_esp_idf():
            print(f"  ESP-IDF: {self.detected['esp_idf']}")
            if self.detected['esp_idf_version']:
                print(f"    Version: {self.detected['esp_idf_version']}")
        else:
            print("  ESP-IDF: NOT FOUND (optional, required for idf-builder tool)")
        
        if self.detect_esptool():
            print(f"  esptool: {self.detected['esptool']}")
        else:
            print("  esptool: NOT FOUND (will install via pip)")
        
        if self.detect_cmake():
            print(f"  CMake: {self.detected['cmake']}")
        else:
            print("  CMake: NOT FOUND (optional, recommended)")
        
        if self.detect_git():
            print(f"  Git: {self.detected['git']}")
        else:
            print("  Git: NOT FOUND (optional, recommended)")
        
        return self.detected
    
    def save_detection(self, output_path: str) -> None:
        """Save detected environment to JSON file."""
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(self.detected, f, indent=2)
        
        print(f"\n✓ Environment detection saved to {output_path}")


def main():
    """Main entry point."""
    detector = EnvironmentDetector()
    detector.detect_all()
    
    # Save detection results
    config_dir = os.path.dirname(os.path.abspath(__file__))
    detection_file = os.path.join(config_dir, "detected_environment.json")
    detector.save_detection(detection_file)
    
    # Check for critical dependencies
    missing = []
    if not detector.detected["esp_idf"]:
        print("\n⚠ WARNING: ESP-IDF not detected")
        print("  The idf-builder tool requires ESP-IDF to be installed")
        print("  Install from: https://github.com/espressif/esp-idf")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
