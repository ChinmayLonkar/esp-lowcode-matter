#!/usr/bin/env python3
"""
Update detected environment with manually provided ESP-IDF path.
"""

import os
import sys
import json
import re

def update_idf_path(idf_path: str, config_file: str) -> bool:
    """Update the detected environment JSON with IDF path and version."""
    try:
        # Load existing config
        with open(config_file, "r") as f:
            config = json.load(f)
        
        # Update IDF path
        config["esp_idf"] = idf_path
        
        # Try to read version from version.cmake
        version_cmake = os.path.join(idf_path, "tools", "cmake", "version.cmake")
        if os.path.isfile(version_cmake):
            with open(version_cmake, "r") as f:
                content = f.read()
                major = re.search(r'set\s*\(\s*IDF_VERSION_MAJOR\s+(\d+)', content)
                minor = re.search(r'set\s*\(\s*IDF_VERSION_MINOR\s+(\d+)', content)
                patch = re.search(r'set\s*\(\s*IDF_VERSION_PATCH\s+(\d+)', content)
                
                if major and minor and patch:
                    version = f"{major.group(1)}.{minor.group(1)}.{patch.group(1)}"
                    config["esp_idf_version"] = version
        
        # Save updated config
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"✓ ESP-IDF path updated: {idf_path}")
        if "esp_idf_version" in config:
            print(f"  Version: {config['esp_idf_version']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error updating configuration: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: update_idf_path.py <idf_path> <config_file>", file=sys.stderr)
        sys.exit(1)
    
    idf_path = sys.argv[1]
    config_file = sys.argv[2]
    
    success = update_idf_path(idf_path, config_file)
    sys.exit(0 if success else 1)

