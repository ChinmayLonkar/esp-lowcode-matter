#!/usr/bin/env python3
"""
ESP-IDF Builder MCP server.
This tool provides functionality for building ESP32 projects and detecting ESP32 chips.
"""

import os
import sys
import json
import logging
import asyncio
import traceback
from typing import Dict, List, Any, Optional, TypedDict, Literal

# Add parent directories to path to find local mcp_tools
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Now import from local mcp_tools
from mcp_tools.components.path_setup import setup_path
setup_path()

# Import FastMCP modules
from fastmcp import FastMCP

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat
from mcp_tools.components.network import ApiClient, NetworkError

# Configure logging with environment variable support and optional file logging
log_level = os.environ.get("MCP_LOG_LEVEL", os.environ.get("LOGGING_LEVEL", "INFO")).upper()
numeric_level = getattr(logging, log_level, logging.INFO)
mcp_log_file = os.environ.get("MCP_LOG_FILE")

# Set up handlers
handlers = []

# Always add console handler (controlled by LOGGING_LEVEL for terminal suppression)
console_level = os.environ.get("LOGGING_LEVEL", "INFO").upper()
console_numeric_level = getattr(logging, console_level, logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(console_numeric_level)
handlers.append(console_handler)

# Add file handler if MCP_LOG_FILE is specified
if mcp_log_file:
    file_handler = logging.FileHandler(mcp_log_file)
    file_handler.setLevel(numeric_level)  # Use MCP_LOG_LEVEL for file
    handlers.append(file_handler)

logging.basicConfig(
    level=min(numeric_level, console_numeric_level),  # Use the most permissive level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger(__name__)

# Suppress verbose logging if console level is WARNING or higher
if console_numeric_level >= logging.WARNING:
    logging.getLogger('mcp.server.lowlevel.server').setLevel(logging.ERROR)
    logging.getLogger('fastmcp').setLevel(logging.ERROR)
elif mcp_log_file:
    # If file logging is enabled, configure FastMCP loggers to use our handlers
    mcp_logger = logging.getLogger('mcp.server.lowlevel.server')
    fastmcp_logger = logging.getLogger('fastmcp')
    mcp_logger.handlers = handlers
    fastmcp_logger.handlers = handlers
    mcp_logger.setLevel(numeric_level)
    fastmcp_logger.setLevel(numeric_level)
    mcp_logger.propagate = False
    fastmcp_logger.propagate = False

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Initialize output manager
output = get_output_manager(format="text", color=True)

# Create FastMCP instance
mcp = FastMCP(name="idf-builder")

# Keep build logs
last_build_output = ""
last_build_summary = ""

# Keep track of last detected chip and project targets to avoid redundant operations
last_detected_chip_info = {}
project_targets = {}  # Maps project_path -> target

async def run_command(cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> tuple[str, int]:
    """Run a command and return stdout/stderr and exit code."""
    logger.info(f"Running command: {' '.join(cmd)}")
    if cwd:
        logger.info(f"Working directory: {cwd}")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=env
    )
    stdout, _ = await process.communicate()
    output_str = stdout.decode('utf-8')
    logger.info(f"Command completed with return code: {process.returncode}")

    # Log the first few lines of output
    output_preview = '\n'.join(output_str.split('\n')[:5])
    if len(output_str.split('\n')) > 5:
        output_preview += "\n... (output truncated)"
    # logger.info(f"Output preview:\n{output_preview}")

    return output_str, process.returncode

async def check_idf_env() -> Dict[str, str]:
    """Check if ESP-IDF environment is properly set up and return environment variables.
    
    The IDF_PATH should already be set when the MCP server starts (from setup.sh).
    This function just validates it exists and returns the current environment.
    
    Raises:
        ValueError: If IDF_PATH is not set
    """
    idf_path = os.environ.get("IDF_PATH")
    if not idf_path:
        raise ValueError(
            "ESP-IDF environment is not set up. IDF_PATH environment variable is not set. "
            "Please ensure you have run the MCP tools setup script (setup.sh) correctly, "
            "which should configure the ESP-IDF environment for the MCP server."
        )

    logger.info(f"IDF_PATH is set to: {idf_path}")
    
    # Return the current environment (IDF should already be exported)
    return dict(os.environ)

async def _detect_chip() -> Dict[str, Any]:
    """Internal function to detect connected ESP32 chip using esptool.py."""
    cmd = ["esptool.py", "chip_id"]

    try:
        # First try using esptool directly (if it's in PATH)
        logger.info("Attempting to run esptool.py directly...")
        output_str, return_code = await run_command(cmd)

        if return_code != 0:
            # Try to find esptool in common locations or using IDF_PATH
            logger.info("Direct call failed, trying to find esptool.py in common locations...")
            idf_path = os.environ.get("IDF_PATH")
            if idf_path:
                logger.info(f"Found IDF_PATH: {idf_path}")
                esptool_path = os.path.join(idf_path, "components", "esptool_py", "esptool", "esptool.py")
                if os.path.exists(esptool_path):
                    logger.info(f"Found esptool.py at: {esptool_path}")
                    cmd = ["python", esptool_path, "chip_id"]
                    output_str, return_code = await run_command(cmd)

        if return_code != 0:
            logger.info("Failed to detect chip")
            return {
                "success": False,
                "message": "No ESP32 device detected or esptool.py not found. Please connect a device."
            }

        # Parse the chip information
        logger.info("Successfully detected chip, parsing information...")
        chip_info = {
            "success": True,
            "raw_output": output_str
        }

        # Extract key information from output
        for line in output_str.splitlines():
            if "Chip is" in line:
                chip_type = line.split("Chip is")[1].strip()
                chip_info["chip_type"] = chip_type
                logger.info(f"Detected chip type: {chip_type}")

                # Add recommended baud rate for serial communication
                if "c2" in chip_type.lower():
                    chip_info["recommended_baud_rate"] = 74800
                    logger.info(f"ESP32-C2 detected - recommended baud rate: 74800")
                else:
                    chip_info["recommended_baud_rate"] = 115200
                    logger.info(f"Standard ESP32 detected - recommended baud rate: 115200")

            elif "Features:" in line:
                chip_info["features"] = line.split("Features:")[1].strip()
            elif "MAC:" in line:
                chip_info["mac"] = line.split("MAC:")[1].strip()

        return chip_info

    except Exception as e:
        logger.error(f"Error in _detect_chip: {e}")
        return {
            "success": False,
            "message": f"Error detecting chip: {str(e)}"
        }


@mcp.tool(name="detect_chip")
async def detect_chip() -> Dict[str, Any]:
    """Auto-detect connected ESP32 chip using esptool.py."""
    logger.info("Tool called: detect_chip")

    try:
        # Call the internal detection function
        result = await _detect_chip()

        # Record tool call result
        if result["success"]:
            db.record_tool_call(
                tool_name="detect_chip",
                parameters={},
                result=result,
                status="success"
            )
            # Output the result
            output.success(f"Detected chip: {result.get('chip_type', 'Unknown')}")
        else:
            db.record_tool_call(
                tool_name="detect_chip",
                parameters={},
                status="error",
                error_message=result["message"]
            )

        return result

    except Exception as e:
        logger.error(f"Error in detect_chip tool: {e}")
        traceback.print_exc()

        # Record error
        db.record_tool_call(
            tool_name="detect_chip",
            parameters={},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "message": f"Error detecting chip: {str(e)}"
        }

def map_chip_to_target(chip_type: str) -> str:
    """Map detected chip type to ESP-IDF target.

    Args:
        chip_type: Chip type string from esptool detection

    Returns:
        ESP-IDF target string
    """
    chip_type_lower = chip_type.lower()

    # Map chip types to ESP-IDF targets
    if "esp32-s3" in chip_type_lower or "esp32s3" in chip_type_lower:
        return "esp32s3"
    elif "esp32-s2" in chip_type_lower or "esp32s2" in chip_type_lower:
        return "esp32s2"
    elif "esp32-c3" in chip_type_lower or "esp32c3" in chip_type_lower:
        return "esp32c3"
    elif "esp32-c2" in chip_type_lower or "esp32c2" in chip_type_lower:
        return "esp32c2"
    elif "esp32-c6" in chip_type_lower or "esp32c6" in chip_type_lower:
        return "esp32c6"
    elif "esp32-h2" in chip_type_lower or "esp32h2" in chip_type_lower:
        return "esp32h2"
    elif "esp32" in chip_type_lower:
        return "esp32"
    else:
        # Default to esp32 for unknown chips
        logger.warning(f"Unknown chip type: {chip_type}, defaulting to esp32")
        return "esp32"

@mcp.tool(name="set_target")
async def set_target(project_path: str, target: Optional[str] = None, auto_detect: bool = True) -> Dict[str, Any]:
    """Set the ESP-IDF target for a project.

    Args:
        project_path: Path to the ESP32 project containing CMakeLists.txt
        target: Specific target to set (e.g., esp32, esp32s3, esp32c3). If None, will auto-detect.
        auto_detect: If True and target is None, automatically detect connected chip and set target
    """
    global last_detected_chip_info, project_targets
    logger.info(f"Tool called: set_target with path: {project_path}, target: {target}, auto_detect: {auto_detect}")

    try:
        project_path = os.path.abspath(os.path.expanduser(project_path))
        logger.info(f"Resolved project path: {project_path}")

        if not os.path.exists(os.path.join(project_path, "CMakeLists.txt")):
            logger.warning(f"No CMakeLists.txt found at {project_path}")
            db.record_tool_call(
                tool_name="set_target",
                parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
                status="error",
                error_message=f"No CMakeLists.txt found at {project_path}"
            )
            return {
                "success": False,
                "message": f"No CMakeLists.txt found at {project_path}"
            }

        detected_target = None
        final_target = target
        chip_detection = None

        # Auto-detect chip if no target specified and auto_detect is enabled
        if not target and auto_detect:
            logger.info("Auto-detecting chip to determine target...")
            output.info("Detecting connected ESP32 chip...")

            # Detect the chip
            chip_detection = await _detect_chip()

            if chip_detection.get("success") and chip_detection.get("chip_type"):
                chip_type = chip_detection["chip_type"]
                detected_target = map_chip_to_target(chip_type)
                final_target = detected_target

                logger.info(f"Detected chip: {chip_type}, mapped to target: {detected_target}")
                output.info(f"Detected chip: {chip_type}, will set target to: {detected_target}")
            else:
                logger.error("Failed to detect chip and no target specified")
                output.error("Failed to detect chip and no target specified")

                db.record_tool_call(
                    tool_name="set_target",
                    parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
                    status="error",
                    error_message="Failed to detect chip and no target specified"
                )

                return {
                    "success": False,
                    "message": "Failed to detect chip and no target specified. Please specify a target manually."
                }

        if not final_target:
            logger.error("No target specified and auto-detection disabled")
            db.record_tool_call(
                tool_name="set_target",
                parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
                status="error",
                error_message="No target specified and auto-detection disabled"
            )
            return {
                "success": False,
                "message": "No target specified and auto-detection disabled"
            }

        # Set the target
        logger.info(f"Setting target to: {final_target}")
        output.info(f"Setting target to: {final_target}")

        # Setup ESP-IDF environment
        try:
            env = await check_idf_env()
            logger.info("ESP-IDF environment setup successful")
        except Exception as e:
            logger.error(f"Failed to setup ESP-IDF environment: {e}")
            return {
                "success": False,
                "message": f"Failed to setup ESP-IDF environment: {str(e)}"
            }

        set_target_cmd = ["idf.py", "set-target", final_target]
        target_output, target_return_code = await run_command(set_target_cmd, cwd=project_path, env=env)

        if target_return_code == 0:
            logger.info(f"Successfully set target to {final_target}")
            output.success(f"Target set to {final_target}")

            # Update our tracking variables
            project_targets[project_path] = final_target
            if chip_detection:
                last_detected_chip_info = chip_detection.copy()

            result = {
                "success": True,
                "target": final_target,
                "detected_target": detected_target,
                "auto_detected": detected_target is not None,
                "output": "Done",
                "message": f"Target successfully set to {final_target}"
            }

            db.record_tool_call(
                tool_name="set_target",
                parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
                result=result,
                status="success"
            )

            return result
        else:
            logger.error(f"Failed to set target to {final_target}: {target_output}")
            output.error(f"Failed to set target to {final_target}")

            db.record_tool_call(
                tool_name="set_target",
                parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
                status="error",
                error_message=f"Failed to set target to {final_target}: {target_output}"
            )

            return {
                "success": False,
                "target": final_target,
                "output": target_output,
                "message": f"Failed to set target to {final_target}",
                "error": target_output
            }

    except Exception as e:
        logger.error(f"Error in set_target: {e}")
        traceback.print_exc()

        # Record error
        db.record_tool_call(
            tool_name="set_target",
            parameters={"project_path": project_path, "target": target, "auto_detect": auto_detect},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "message": f"Error setting target: {str(e)}"
        }

@mcp.tool(name="build_project")
async def build_project(project_path: str, auto_set_target: bool = True) -> Dict[str, Any]:
    """Build ESP32 project at the specified path.

    Args:
        project_path: Path to the ESP32 project containing CMakeLists.txt
        auto_set_target: If True, automatically detect chip and set target before building
    """
    global last_build_output, last_build_summary, last_detected_chip_info, project_targets
    logger.info(f"Tool called: build_project with path: {project_path}, auto_set_target: {auto_set_target}")

    try:
        project_path = os.path.abspath(os.path.expanduser(project_path))
        logger.info(f"Resolved project path: {project_path}")

        if not os.path.exists(os.path.join(project_path, "CMakeLists.txt")):
            logger.warning(f"No CMakeLists.txt found at {project_path}")
            db.record_tool_call(
                tool_name="build_project",
                parameters={"project_path": project_path, "auto_set_target": auto_set_target},
                status="error",
                error_message=f"No CMakeLists.txt found at {project_path}"
            )
            return {
                "success": False,
                "message": f"No CMakeLists.txt found at {project_path}"
            }

        target_set = False
        detected_target = None
        target_skipped = False

        # Auto-detect chip and set target if requested
        if auto_set_target:
            logger.info("Auto-detecting chip and checking if target needs to be set...")
            output.info("Detecting connected ESP32 chip...")

            # Detect the chip
            chip_detection = await _detect_chip()

            if chip_detection.get("success") and chip_detection.get("chip_type"):
                chip_type = chip_detection["chip_type"]
                detected_target = map_chip_to_target(chip_type)

                logger.info(f"Detected chip: {chip_type}, mapped to target: {detected_target}")

                # Check current project target
                current_target = await get_current_target(project_path)
                logger.info(f"Current project target: {current_target}")

                # Check if we need to set the target
                need_to_set_target = True

                # If current target matches detected target, skip setting target
                if current_target == detected_target:
                    logger.info(f"Target already set to {detected_target}, skipping target setting")
                    output.info(f"Target already set to {detected_target}, skipping target setting")
                    need_to_set_target = False
                    target_skipped = True
                else:
                    logger.info(f"Current target ({current_target}) differs from detected target ({detected_target}), will set target")
                    output.info(f"Setting target from {current_target} to {detected_target}")

                if need_to_set_target:
                    # Setup ESP-IDF environment for target setting
                    try:
                        env = await check_idf_env()
                        logger.info("ESP-IDF environment setup successful for target setting")
                    except Exception as e:
                        logger.error(f"Failed to setup ESP-IDF environment for target setting: {e}")
                        output.warning(f"Failed to setup ESP-IDF environment, continuing with existing target")
                        target_set = False
                        need_to_set_target = False
                    
                    if need_to_set_target:
                        # Set the target
                        set_target_cmd = ["idf.py", "set-target", detected_target]
                        target_output, target_return_code = await run_command(set_target_cmd, cwd=project_path, env=env)
                    else:
                        target_return_code = 1  # Mark as failed if we couldn't set target due to env setup failure

                    if target_return_code == 0:
                        target_set = True
                        logger.info(f"Successfully set target to {detected_target}")
                        output.success(f"Target set to {detected_target}")

                        # Update our tracking
                        project_targets[project_path] = detected_target
                    else:
                        logger.warning(f"Failed to set target to {detected_target}: {target_output}")
                        output.warning(f"Failed to set target to {detected_target}, continuing with existing target")

                # Update last detected chip info
                last_detected_chip_info = chip_detection.copy()

            else:
                logger.warning("Failed to detect chip, continuing with existing target")
                output.warning("Failed to detect chip, continuing with existing target")

        # Setup ESP-IDF environment for building
        try:
            env = await check_idf_env()
            logger.info("ESP-IDF environment setup successful for building")
        except Exception as e:
            logger.error(f"Failed to setup ESP-IDF environment for building: {e}")
            db.record_tool_call(
                tool_name="build_project",
                parameters={"project_path": project_path, "auto_set_target": auto_set_target},
                status="error",
                error_message=f"Failed to setup ESP-IDF environment: {str(e)}"
            )
            return {
                "success": False,
                "message": f"Failed to setup ESP-IDF environment: {str(e)}"
            }

        # Run the build command
        logger.info("Starting build process...")
        output.info("Building project...")
        cmd = ["idf.py", "build"]
        output_str, return_code = await run_command(cmd, cwd=project_path, env=env)

        # Store the full output for later reference
        last_build_output = output_str
        logger.info(f"Build completed with return code: {return_code}")

        # Generate a summary
        logger.info("Generating build summary...")
        lines = output_str.splitlines()
        summary_lines = []

        # Add target information to summary
        if target_set and detected_target:
            summary_lines.append(f"TARGET SET: {detected_target} (auto-detected)")
        elif target_skipped and detected_target:
            summary_lines.append(f"TARGET UNCHANGED: {detected_target} (already set)")

        # Extract important information like errors, warnings and the final result
        error_count = 0
        warning_count = 0
        error_files = set()

        # Track CMake error/warning parsing state
        in_cmake_error = False
        in_cmake_warning = False
        current_cmake_error = []
        current_cmake_warning = []
        cmake_error_indent = 0
        cmake_warning_indent = 0

        for i, line in enumerate(lines):
            # Check for regular gcc/g++ errors
            if "error:" in line.lower():
                summary_lines.append(line)
                error_count += 1

                # Extract file path which is before the first colon
                parts = line.split(':', 1)
                if len(parts) > 1:
                    file_path = parts[0].strip()
                    error_files.add(file_path)

            # Check for regular warnings
            elif "warning:" in line.lower():
                warning_count += 1
                if warning_count <= 5:  # Limit to first 5 warnings
                    summary_lines.append(line)

            # Check for CMake errors
            elif "CMake Error" in line:
                in_cmake_error = True
                cmake_error_indent = len(line) - len(line.lstrip())
                current_cmake_error = [line]
                error_count += 1
                # Try to extract a file path if it exists in the CMake error line
                if "at " in line and ".cmake" in line.split("at ")[1]:
                    file_path = line.split("at ")[1].split(":")[0].strip()
                    error_files.add(file_path)

            # Check for CMake warnings
            elif "CMake Warning" in line:
                in_cmake_warning = True
                cmake_warning_indent = len(line) - len(line.lstrip())
                current_cmake_warning = [line]
                warning_count += 1

            # Continue collecting CMake error content
            elif in_cmake_error:
                # Check if this line is indented further than the error start line
                if line.strip() and (len(line) - len(line.lstrip()) > cmake_error_indent):
                    current_cmake_error.append(line)
                    # Try to extract file paths from the error details
                    if ": " in line and os.path.exists(line.split(": ")[0].strip()):
                        error_files.add(line.split(": ")[0].strip())
                else:
                    # End of indented CMake error block
                    if current_cmake_error:
                        summary_lines.extend(current_cmake_error)
                        current_cmake_error = []
                    in_cmake_error = False
                    # Process the current line again
                    i -= 1

            # Continue collecting CMake warning content
            elif in_cmake_warning:
                # Check if this line is indented further than the warning start line
                if line.strip() and (len(line) - len(line.lstrip()) > cmake_warning_indent):
                    current_cmake_warning.append(line)
                else:
                    # End of indented CMake warning block
                    if current_cmake_warning and warning_count <= 5:
                        summary_lines.extend(current_cmake_warning)
                    current_cmake_warning = []
                    in_cmake_warning = False
                    # Process the current line again
                    i -= 1

        # Add any remaining CMake errors/warnings
        if current_cmake_error:
            summary_lines.extend(current_cmake_error)

        if current_cmake_warning and warning_count <= 5:
            summary_lines.extend(current_cmake_warning)

        # Add build result
        if return_code == 0:
            # Find build completion message
            completion_msg = "Project build complete."
            for i in range(len(lines) - 1, 0, -1):
                if "Project build complete" in lines[i]:
                    completion_msg = lines[i]
                    # Also add the next line which contains the binary path
                    if i + 1 < len(lines):
                        completion_msg += f"\n{lines[i+1]}"
                    break
            summary_lines.append(f"BUILD SUCCESSFUL: {completion_msg}")
        else:
            summary_lines.append(f"BUILD FAILED with {error_count} errors, {warning_count} warnings")

        summary = "\n".join(summary_lines)
        last_build_summary = summary

        # Record the result
        result = {
            "success": return_code == 0,
            "error_count": error_count,
            "warning_count": warning_count,
            "summary": summary,
            "error_files": list(error_files),
            "target_set": target_set,
            "target_skipped": target_skipped,
            "detected_target": detected_target
        }

        db.record_tool_call(
            tool_name="build_project",
            parameters={"project_path": project_path, "auto_set_target": auto_set_target},
            result=result,
            status="success" if return_code == 0 else "error",
            error_message=None if return_code == 0 else f"Build failed with {error_count} errors"
        )

        # Output using the output manager
        if return_code == 0:
            output.success("Build completed successfully")
            if target_set:
                output.info(f"Target was automatically set to {detected_target}")
            elif target_skipped:
                output.info(f"Target setting skipped (already set to {detected_target})")
        else:
            output.error(f"Build failed with {error_count} errors")

        return result

    except Exception as e:
        logger.error(f"Error in build_project: {e}")
        traceback.print_exc()

        # Record error
        db.record_tool_call(
            tool_name="build_project",
            parameters={"project_path": project_path, "auto_set_target": auto_set_target},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "message": f"Error building project: {str(e)}"
        }

@mcp.tool(name="fullclean")
async def fullclean(project_path: str) -> Dict[str, Any]:
    """Run idf.py fullclean to remove all build artifacts.

    Args:
        project_path: Path to the ESP32 project containing CMakeLists.txt
    """
    logger.info(f"Tool called: fullclean with path: {project_path}")

    try:
        project_path = os.path.abspath(os.path.expanduser(project_path))
        logger.info(f"Resolved project path: {project_path}")

        if not os.path.exists(os.path.join(project_path, "CMakeLists.txt")):
            logger.warning(f"No CMakeLists.txt found at {project_path}")
            db.record_tool_call(
                tool_name="fullclean",
                parameters={"project_path": project_path},
                status="error",
                error_message=f"No CMakeLists.txt found at {project_path}"
            )
            return {
                "success": False,
                "message": f"No CMakeLists.txt found at {project_path}"
            }

        # Setup ESP-IDF environment
        try:
            env = await check_idf_env()
            logger.info("ESP-IDF environment setup successful")
        except Exception as e:
            logger.error(f"Failed to setup ESP-IDF environment: {e}")
            db.record_tool_call(
                tool_name="fullclean",
                parameters={"project_path": project_path},
                status="error",
                error_message=f"Failed to setup ESP-IDF environment: {str(e)}"
            )
            return {
                "success": False,
                "message": f"Failed to setup ESP-IDF environment: {str(e)}"
            }

        # Run fullclean command
        logger.info("Running fullclean...")
        output.info("Running fullclean to remove all build artifacts...")
        cmd = ["idf.py", "fullclean"]
        output_str, return_code = await run_command(cmd, cwd=project_path, env=env)

        if return_code == 0:
            logger.info("Fullclean completed successfully")
            output.success("Fullclean completed successfully")

            result = {
                "success": True,
                "message": "All build artifacts removed successfully",
                "output": output_str
            }

            db.record_tool_call(
                tool_name="fullclean",
                parameters={"project_path": project_path},
                result=result,
                status="success"
            )

            return result
        else:
            logger.error(f"Fullclean failed: {output_str}")
            output.error("Fullclean failed")

            db.record_tool_call(
                tool_name="fullclean",
                parameters={"project_path": project_path},
                status="error",
                error_message=f"Fullclean failed: {output_str}"
            )

            return {
                "success": False,
                "message": "Fullclean failed",
                "error": output_str
            }

    except Exception as e:
        logger.error(f"Error in fullclean: {e}")
        traceback.print_exc()

        db.record_tool_call(
            tool_name="fullclean",
            parameters={"project_path": project_path},
            status="error",
            error_message=str(e)
        )

        return {
            "success": False,
            "message": f"Error running fullclean: {str(e)}"
        }

@mcp.tool(name="get_full_build_log")
def get_full_build_log() -> str:
    """Get the full build log from the last build."""
    global last_build_output
    logger.info("Tool called: get_full_build_log")

    db.record_tool_call(
        tool_name="get_full_build_log",
        parameters={},
        status="success"
    )

    if not last_build_output:
        output.warning("No build log available. Please run a build first.")
        return "No build log available. Please run a build first."

    output.info("Returning full build log")
    return last_build_output

@mcp.tool(name="get_build_summary")
def get_build_summary() -> str:
    """Get a summary of the last build."""
    global last_build_summary
    logger.info("Tool called: get_build_summary")

    db.record_tool_call(
        tool_name="get_build_summary",
        parameters={},
        status="success"
    )

    if not last_build_summary:
        output.warning("No build summary available. Please run a build first.")
        return "No build summary available. Please run a build first."

    output.info("Returning build summary")
    return last_build_summary

@mcp.tool(name="clear_tracking")
def clear_tracking() -> Dict[str, Any]:
    """Clear chip and target tracking information to force fresh detection on next build."""
    logger.info("Tool called: clear_tracking")

    clear_chip_tracking()

    result = {
        "success": True,
        "message": "Chip and target tracking information cleared. Next build will perform fresh chip detection."
    }

    db.record_tool_call(
        tool_name="clear_tracking",
        parameters={},
        result=result,
        status="success"
    )

    output.success("Tracking information cleared")
    return result

# ============================================================================
# MCP PROMPTS - Structured Workflows
# ============================================================================

@mcp.prompt()
def build_firmware(project_path: str, clean_build: bool = False) -> str:
    """Complete ESP-IDF firmware build workflow with auto-detection.
    
    Guides through: detect chip → set target → build → verify
    
    Args:
        project_path: Path to ESP-IDF project directory
        clean_build: If true, run fullclean before building
    """
    return f"""Execute the complete ESP-IDF firmware build workflow:

PROJECT PATH: {project_path}
CLEAN BUILD: {'Yes (will run fullclean first)' if clean_build else 'No (incremental build)'}

WORKFLOW:

1. **Verify Project Structure**
   - Check that {project_path} contains CMakeLists.txt
   - Verify it's a valid ESP-IDF project

2. **Detect Connected Device**
   - Use detect_chip() to identify connected ESP32 chip
   - Determine appropriate target (esp32, esp32s3, esp32c3, etc.)
   - Note the chip type for reference

3. {'**Clean Build Artifacts**' if clean_build else '**Skip Clean (Incremental Build)**'}
   {f'- Run fullclean("{project_path}") to remove all build artifacts' if clean_build else '- Proceeding with incremental build'}
   {f'- Ensures fresh compilation of all files' if clean_build else '- Only modified files will be recompiled'}

4. **Build Project**
   - Run build_project("{project_path}", auto_set_target=True)
   - This will automatically set the correct target if needed
   - Monitor build progress and capture errors/warnings

5. **Review Results**
   - If build succeeds: Report success and binary location
   - If build fails: 
     * Use get_build_summary() to see errors
     * Identify error files and line numbers
     * Provide recommendations for fixes
     * Do NOT proceed to flashing

6. **Next Steps**
   - If successful: Project is ready for flashing
   - If failed: Fix identified errors and rebuild

IMPORTANT NOTES:
- Auto-detection will set the correct target based on connected chip
- Build errors must be fixed before proceeding to testing
- Use get_full_build_log() if detailed build output is needed
"""

@mcp.prompt()
def clean_rebuild(project_path: str) -> str:
    """Clean all build artifacts and rebuild from scratch.
    
    Args:
        project_path: Path to ESP-IDF project directory
    """
    return f"""Execute clean rebuild workflow:

PROJECT PATH: {project_path}

WORKFLOW:

1. **Full Clean**
   - Run fullclean("{project_path}")
   - Removes: build/, sdkconfig (preserves sdkconfig.old)
   - This ensures a completely fresh build

2. **Rebuild from Scratch**
   - Run build_project("{project_path}", auto_set_target=True)
   - All files will be recompiled
   - Target will be auto-detected and set

3. **Verify Success**
   - Check build completed without errors
   - Review any warnings
   - Confirm binary was generated

USE CASES:
- Build system acting strangely
- Changed menuconfig settings significantly
- Want to verify clean build works
- Switching between different targets
"""

@mcp.prompt()
def diagnose_build_failure(project_path: str) -> str:
    """Analyze build failures and provide fix recommendations.
    
    Args:
        project_path: Path to ESP-IDF project that failed to build
    """
    return f"""Diagnose build failure for project:

PROJECT PATH: {project_path}

DIAGNOSTIC WORKFLOW:

1. **Get Build Summary**
   - Run get_build_summary() to see the last build results
   - Identify error count, warning count, and affected files

2. **Analyze Errors**
   - Categorize errors:
     * CMake configuration errors (missing components, wrong paths)
     * Compilation errors (syntax, undefined references)
     * Linker errors (missing symbols, memory overflow)
   - Note error patterns (multiple similar errors suggest root cause)

3. **Check Common Issues**
   - IDF_PATH environment variable set correctly?
   - Target matches connected chip? (use get_tracking_status())
   - Required components available?
   - sdkconfig consistent with target?

4. **Provide Recommendations**
   - For each error, suggest specific fixes
   - If config issue: recommend set_target() or fullclean()
   - If code issue: identify specific files and lines to fix
   - If dependency issue: list missing components

5. **Suggest Next Steps**
   - Prioritize fixes (fix CMake errors first, then compilation, then linker)
   - Recommend incremental fixes (fix one issue, rebuild, repeat)

DO NOT:
- Make multiple changes at once
- Proceed to testing with build failures
- Guess at fixes without analyzing the actual errors
"""

@mcp.tool(name="get_tracking_status")
def get_tracking_status() -> Dict[str, Any]:
    """Get the current chip and target tracking status."""
    global last_detected_chip_info, project_targets
    logger.info("Tool called: get_tracking_status")

    result = {
        "success": True,
        "last_detected_chip": last_detected_chip_info.copy() if last_detected_chip_info else None,
        "project_targets": project_targets.copy() if project_targets else {},
        "has_tracking_data": bool(last_detected_chip_info or project_targets)
    }

    db.record_tool_call(
        tool_name="get_tracking_status",
        parameters={},
        result=result,
        status="success"
    )

    if result["has_tracking_data"]:
        output.info("Tracking data available")
    else:
        output.info("No tracking data available")

    return result

@mcp.tool(name="get_idf_version")
async def get_idf_version() -> Dict[str, Any]:
    """Get the ESP-IDF version currently configured."""
    logger.info("Tool called: get_idf_version")
    
    try:
        env = await check_idf_env()
        cmd = ["idf.py", "--version"]
        version_output, return_code = await run_command(cmd, env=env)
        
        if return_code == 0:
            result = {
                "success": True,
                "version": version_output.strip()
            }
            db.record_tool_call(
                tool_name="get_idf_version",
                parameters={},
                result=result,
                status="success"
            )
            output.success(f"IDF version: {version_output.strip()}")
            return result
        else:
            result = {
                "success": False,
                "error": version_output
            }
            db.record_tool_call(
                tool_name="get_idf_version",
                parameters={},
                status="error",
                error_message=version_output
            )
            output.error("Failed to get IDF version")
            return result
            
    except Exception as e:
        logger.error(f"Error getting IDF version: {e}")
        result = {
            "success": False,
            "error": str(e)
        }
        db.record_tool_call(
            tool_name="get_idf_version",
            parameters={},
            status="error",
            error_message=str(e)
        )
        output.error(f"Error: {str(e)}")
        return result

async def get_current_target(project_path: str) -> Optional[str]:
    """Get the current target set for a project by reading sdkconfig.

    Args:
        project_path: Path to the ESP32 project

    Returns:
        Current target string or None if not set
    """
    try:
        sdkconfig_path = os.path.join(project_path, "sdkconfig")
        if not os.path.exists(sdkconfig_path):
            return None

        with open(sdkconfig_path, 'r') as f:
            for line in f:
                if line.startswith("CONFIG_IDF_TARGET="):
                    target = line.split("=")[1].strip().strip('"')
                    logger.info(f"Found current target in sdkconfig: {target}")
                    return target
        return None
    except Exception as e:
        logger.warning(f"Failed to read current target from sdkconfig: {e}")
        return None

def clear_chip_tracking():
    """Clear the chip and target tracking information."""
    global last_detected_chip_info, project_targets
    last_detected_chip_info.clear()
    project_targets.clear()
    logger.info("Cleared chip and target tracking information")

def is_same_chip_type(chip_info1: Dict[str, Any], chip_info2: Dict[str, Any]) -> bool:
    """Compare two chip detection results to see if they represent the same chip type.

    Args:
        chip_info1: First chip detection result
        chip_info2: Second chip detection result

    Returns:
        True if both represent the same chip type
    """
    if not chip_info1 or not chip_info2:
        return False

    # Compare chip types (this is the most important comparison)
    chip_type1 = chip_info1.get("chip_type", "").lower()
    chip_type2 = chip_info2.get("chip_type", "").lower()

    if chip_type1 != chip_type2:
        return False

    # For additional verification, we could compare features if available
    # but chip_type should be sufficient for our use case
    return True

async def main():
    """Main entry point."""
    # Print available tools
    tools = await mcp.get_tools()
    tools_data = [{"name": t.name, "description": t.description} for t in tools.values()]
    output.print("Registered Tools:", color="green")
    output.output(tools_data)

    # Start the server using stdio transport
    output.info("Starting MCP server using stdio transport")
    await mcp.run_stdio_async()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
