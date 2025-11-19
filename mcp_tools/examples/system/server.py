#!/usr/bin/env python3
"""
Template for an MCP server.
This is a starting point for creating a custom tool that follows the MCP protocol.
"""

import os
import sys
import json
import logging
import tempfile
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
from fastmcp.server.server import stdio_server as stdio_transport

# Import additional base components
from mcp_tools.components.database import ToolDatabase
from mcp_tools.components.output import get_output_manager, OutputFormat
from mcp_tools.components.network import ApiClient, NetworkError

from html_to_text import HtmlToText
from pdf_to_text import PdfToText

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

# Initialize database with a path relative to the tool directory
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
db = ToolDatabase(DB_PATH)

# Initialize output manager
output = get_output_manager(format="text", color=True)

# Initialize HtmlToText
html_to_text = HtmlToText()
pdf_to_text = PdfToText()

# Create FastMCP instance
mcp = FastMCP(name="system")

@mcp.tool(name="apply_patch")
def apply_patch(patch_content: str, working_directory: str = ".") -> Dict[str, Any]:
    """Apply a patch to files in the specified directory.

    Args:
        patch_content: The patch content to apply (must start with *** Begin Patch)
        working_directory: Directory to apply the patch in (default: current directory)

    Returns:
        Dictionary with success status and details
    
    Example patch formats:
    
    1. Add a new file:
        *** Begin Patch
        *** Add File: src/config.py
        +DEBUG = False
        +PORT = 8080
        +TIMEOUT = 30
        *** End Patch
    
    2. Update an existing file:
        *** Begin Patch
        *** Update File: src/config.py
        @@ -10,3 +10,4 @@
         DEBUG = False
         PORT = 8080
        +TIMEOUT = 30
        *** End Patch
    
    3. Delete a file:
        *** Begin Patch
        *** Delete File: src/old_config.py
        *** End Patch
    
    Notes:
        - All patches must start with '*** Begin Patch' and end with '*** End Patch'
        - Use relative paths from working_directory (not absolute paths)
        - For adding files: prefix each line with '+'
        - For updating files: use @@ markers and context lines with ' ', '+', or '-'
        - Context lines (unchanged) start with a space ' '
        - Added lines start with '+'
        - Removed lines start with '-'
    """
    import os
    import sys

    # Add the apply_patch module to path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    apply_patch_path = os.path.join(current_dir, "apply_patch.py")

    try:
        # Log tool usage
        db.record_tool_call(
            tool_name="apply_patch",
            parameters={"patch_content": f"{len(patch_content)} chars", "working_directory": working_directory},
            status="started"
        )

        # Import apply_patch module
        import importlib.util
        spec = importlib.util.spec_from_file_location("apply_patch", apply_patch_path)
        if not spec or not spec.loader:
            error_msg = f"Could not load apply_patch.py from {apply_patch_path}"
            db.record_tool_call(
                tool_name="apply_patch",
                parameters={"error": error_msg},
                status="error"
            )
            return {"success": False, "error": error_msg}

        apply_patch_module = importlib.util.module_from_spec(spec)
        sys.modules["apply_patch"] = apply_patch_module
        spec.loader.exec_module(apply_patch_module)

        # Change to working directory
        original_cwd = os.getcwd()
        if working_directory != ".":
            os.chdir(working_directory)

        try:
            # Apply the patch using the module's functions
            result = apply_patch_module.process_patch(
                patch_content,
                apply_patch_module.open_file,
                apply_patch_module.write_file,
                apply_patch_module.remove_file
            )

            db.record_tool_call(
                tool_name="apply_patch",
                parameters={"result": result},
                status="success"
            )

            output.success(f"Patch applied successfully: {result}")

            return {
                "success": True,
                "result": result,
                "working_directory": working_directory
            }

        finally:
            # Restore original working directory
            os.chdir(original_cwd)

    except Exception as e:
        error_msg = f"Patch application failed: {str(e)}"
        db.record_tool_call(
            tool_name="apply_patch",
            parameters={"error": error_msg},
            status="error"
        )
        output.error(error_msg)

        return {
            "success": False,
            "error": error_msg,
            "working_directory": working_directory
        }

@mcp.tool(name="list_files")
def list_files(directory: str = ".") -> Dict[str, Any]:
    """List the files in a directory recursively.
    Ignore hidden files and common build artifacts.
    Also returns the number of lines and size in bytes of each file.
    """
    if not os.path.exists(directory):
        return {"success": False, "error": f"Directory {directory} does not exist"}

    file_list = []
    try:
        for root, dirs, filenames in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'managed_components']]

            for filename in filenames:
                if filename.startswith('.') or filename.endswith(('.o', '.bin', '.elf', '.map', '.pyc')) or filename in ['sdkconfig', 'sdkconfig.old']:
                    continue

                file_path = os.path.join(root, filename)
                try:
                    # Get file size
                    file_size = os.path.getsize(file_path)

                    # Try to count lines for text files
                    line_count = 0
                    try:
                        if file_path.endswith(".pdf"):
                            line_count = len(pdf_to_text.convert(file_path).split("\n"))
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                line_count = sum(1 for _ in f)
                    except (OSError, PermissionError):
                        # For binary files or permission issues, set lines to 0
                        line_count = 0

                    file_list.append({
                        "name": filename,
                        "path": file_path,
                        "lines": line_count,
                        "size": file_size
                    })
                except (OSError, PermissionError) as e:
                    # Skip files we can't access
                    logger.debug(f"Skipping file {file_path}: {e}")
                    continue

    except Exception as e:
        return {"success": False, "error": f"Error listing directory: {str(e)}"}

    return {"success": True, "files": file_list}

@mcp.tool(name="read_file")
def read_file(filename: str, from_line: int = 0, to_line: int = 0, from_page: int = 0, to_page: int = 0) -> Dict[str, Any]:
    """Read the contents of a file.

    Args:
        filename: The name of the file to read
        from_line: The line number to start reading from for non-PDF files (default: 0, reads all)
        to_line: The line number to stop reading at for non-PDF files (default: 0, reads all)
        from_page: The page number to start reading from for PDF files (default: 0, reads all)
        to_page: The page number to stop reading at for PDF files (default: 0, reads all)
    """
    if not os.path.exists(filename):
        return {"success": False, "error": f"File {filename} does not exist"}

    contents = None
    
    if filename.endswith(".pdf"):
        # Direct users to use extract_pdf instead
        return {"success": False, "error": "PDF files are not supported by read_file. Please use the extract_pdf tool instead to extract and process PDF content."}
    else:
        # Handle non-PDF files with line-based reading
        if from_page > 0 or to_page > 0:
            return {"success": False, "error": "from_page and to_page are only supported for PDF files"}
        
        try:
            with open(filename, "r", encoding='utf-8', errors='ignore') as f:
                if from_line > 0 and to_line > 0:
                    # Validate line numbers
                    if from_line > to_line:
                        return {"success": False, "error": f"from_line ({from_line}) cannot be greater than to_line ({to_line})"}
                    
                    # Read specific line range
                    all_lines = f.readlines()
                    total_lines = len(all_lines)
                    
                    # Adjust bounds
                    if from_line > total_lines:
                        return {"success": False, "error": f"from_line ({from_line}) exceeds file length ({total_lines} lines)"}
                    
                    to_line = min(to_line, total_lines)
                    selected_lines = all_lines[from_line-1:to_line]
                    contents = ''.join(selected_lines)
                elif from_line > 0 or to_line > 0:
                    return {"success": False, "error": "For non-PDF files, both from_line and to_line must be specified together (both > 0)"}
                else:
                    # Read entire file
                    contents = f.read()
        except Exception as e:
            return {"success": False, "error": f"Error reading file {filename}: {str(e)}"}

    if not contents:
        return {"success": False, "error": f"Could not read file {filename} or file is empty"}
    
    return {"success": True, "contents": contents}

@mcp.tool(name="search_file")
def search_file(filename: str, pattern: str) -> Dict[str, Any]:
    """Search the contents of a file or directory for a given pattern.
    The line numbers are 1-indexed.
    """
    if not os.path.exists(filename):
        return {"success": False, "error": f"File or directory {filename} does not exist"}

    found_files = []
    if os.path.isdir(filename):
        file_list = list_files(filename)
        for file in file_list["files"]:
            found_files.append(file["path"])
    else:
        found_files.append(filename)

    found_lines = []
    for file in found_files:
        contents = None
        try:
            if file.endswith(".pdf"):
                contents = pdf_to_text.convert(file)
            else:
                with open(file, "r", encoding='utf-8', errors='ignore') as f:
                    contents = f.read()
        except (OSError, PermissionError, UnicodeDecodeError):
            # Skip files that can't be read (binary, permission issues, etc.)
            continue

        if not contents:
            continue

        lines = contents.split("\n")
        for i, line in enumerate(lines):
            if pattern in line:
                found_lines.append({"file": file, "line": i+1, "line_content": line})

    if len(found_lines) == 0:
        return {"success": False, "error": f"Pattern {pattern} not found in any file in {filename}"}
    return {"success": True, "found_lines": found_lines}

@mcp.tool(name="web_page_reader")
def web_page_reader(url: str) -> Dict[str, Any]:
    """Read the contents of a web page.
    """
    import requests
    import urllib.parse
    url = urllib.parse.unquote(url)
    if url.startswith("file://"):
        return {"success": False, "error": f"Use the read_file tool to read local files"}
    if not url.startswith("http"):
        return {"success": False, "error": f"Invalid URL: {url}"}
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Failed to fetch web page: {str(e)}"}

    text = html_to_text.convert(response.text)
    return {"success": True, "contents": text}

@mcp.tool(name="extract_pdf")
def extract_pdf(pdf_path: str, output_path: str = None) -> Dict[str, Any]:
    """Extract comprehensive data from a PDF file including markdown text, images, and metadata.
    
    This tool extracts:
    - Markdown formatted text with preserved structure
    - All images with contextual metadata
    - PDF document information
    
    All outputs are stored in the specified output folder.
    
    Args:
        pdf_path: Path to the PDF file to extract
        output_path: Directory where extracted content will be stored (default: system temp directory)
        
    Returns:
        Dictionary with extraction results and file paths
    """
    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF file not found: {pdf_path}"}
    
    if not pdf_path.lower().endswith('.pdf'):
        return {"success": False, "error": f"File must be a PDF: {pdf_path}"}
    
    try:
        # Initialize PDF converter
        pdf_converter = PdfToText()
        
        # Use system temp directory if no output path specified
        if output_path is None:
            import tempfile
            output_path = os.path.join(tempfile.gettempdir(), "pdf_extracts")
        
        # Create docs folder in specified location
        docs_folder = os.path.expanduser(output_path)
        os.makedirs(docs_folder, exist_ok=True)
        
        # Create subfolder for this PDF
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        pdf_docs_folder = os.path.join(docs_folder, pdf_name)
        os.makedirs(pdf_docs_folder, exist_ok=True)
        
        # Create subfolders
        images_folder = os.path.join(pdf_docs_folder, "images")
        os.makedirs(images_folder, exist_ok=True)
        
        # Extract markdown text
        logger.info(f"Extracting markdown text from {pdf_path}")
        markdown_text = pdf_converter.convert_to_markdown(pdf_path)
        
        if markdown_text.startswith("[Error"):
            return {"success": False, "error": f"Failed to extract text: {markdown_text}"}
        
        # Save markdown file
        markdown_file = os.path.join(pdf_docs_folder, f"{pdf_name}.md")
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write(markdown_text)
        
        # Extract images with metadata
        logger.info(f"Extracting images from {pdf_path}")
        images_info = pdf_converter.extract_images(pdf_path, images_folder)
        
        if images_info and "error" in images_info[0]:
            return {"success": False, "error": f"Failed to extract images: {images_info[0]['error']}"}
        
        # Save images metadata
        metadata_file = os.path.join(pdf_docs_folder, "images_metadata.json")
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(images_info, f, indent=2, ensure_ascii=False)
        
        # Get PDF document info
        logger.info(f"Extracting PDF info from {pdf_path}")
        pdf_info = pdf_converter.get_pdf_info(pdf_path)
        
        # Save PDF info
        info_file = os.path.join(pdf_docs_folder, "pdf_info.json")
        with open(info_file, 'w', encoding='utf-8') as f:
            json.dump(pdf_info, f, indent=2, ensure_ascii=False)
        
        # Create concise image summaries for LLM consumption
        image_summaries = []
        if images_info:
            for img in images_info:
                metadata = img.get('metadata', {})
                
                # Only include meaningful metadata
                summary = {
                    "file": img['filename'],
                    "page": img['page']
                }
                
                # Add description if meaningful
                description = metadata.get('description', '')
                if description and not description.startswith('Technical diagram or illustration'):
                    summary["description"] = description
                
                # Add caption if found
                caption = metadata.get('caption')
                if caption and caption.get('description'):
                    summary["caption"] = f"{caption.get('type', 'Figure')} {caption.get('number', '')}: {caption.get('description', '')}"
                
                # Add surrounding text context if meaningful
                surrounding = metadata.get('surrounding_text', {})
                if surrounding.get('before') or surrounding.get('after'):
                    # Extract key technical terms from surrounding text
                    context_text = (surrounding.get('before', '') + ' ' + surrounding.get('after', '')).lower()
                    key_terms = []
                    common_terms = ['pin', 'circuit', 'diagram', 'table', 'graph', 'chart', 'block', 'schematic', 'timing', 'register', 'memory', 'application', 'package']
                    for term in common_terms:
                        if term in context_text:
                            key_terms.append(term)
                    if key_terms:
                        summary["context_terms"] = key_terms[:3]  # Limit to top 3 terms
                
                # Only include if we have meaningful content
                if len(summary) > 2:  # More than just file and page
                    image_summaries.append(summary)
        
        # Compact extraction summary
        extraction_summary = {
            "pdf": {
                "title": pdf_info.get('title', '').split(' - ')[0] if pdf_info.get('title') else os.path.splitext(os.path.basename(pdf_path))[0],
                "pages": pdf_info.get('page_count', 0)
            },
            "extracted": {
                "markdown_file": os.path.basename(markdown_file),
                "images_count": len(images_info) if images_info else 0,
                "images_with_context": len(image_summaries)
            },
            "output_path": pdf_docs_folder
        }
        
        # Save full detailed data for reference
        full_stats = {
            "pdf_file": pdf_path,
            "extraction_timestamp": os.path.getctime(pdf_docs_folder),
            "markdown": {"file": markdown_file, "size_chars": len(markdown_text), "size_lines": len(markdown_text.split('\n'))},
            "images": {"folder": images_folder, "metadata_file": metadata_file, "total_count": len(images_info) if images_info else 0},
            "pdf_info": {"file": info_file, "pages": pdf_info.get('page_count', 0), "title": pdf_info.get('title', 'Unknown')},
            "output_folder": pdf_docs_folder
        }
        
        summary_file = os.path.join(pdf_docs_folder, "extraction_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(full_stats, f, indent=2, ensure_ascii=False)
        
        logger.info(f"PDF extraction completed successfully. Output folder: {pdf_docs_folder}")
        
        return {
            "success": True,
            "paths": {
                "markdown": markdown_file,
                "images_folder": images_folder,
                "metadata": metadata_file
            }
        }
        
    except Exception as e:
        logger.error(f"Error extracting PDF {pdf_path}: {str(e)}")
        return {"success": False, "error": f"Extraction failed: {str(e)}"}

@mcp.tool(name="get_image")
def get_image(image_path: str) -> Dict[str, Any]:
    """Send an image to the LLM for analysis.
    
    This tool reads an image file and returns it with metadata for LLM processing.
    Works with images extracted by extract_pdf or any other image file.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Dictionary with success status and image information
    """
    import base64
    
    # Handle PIL import with auto-installation
    try:
        from PIL import Image
    except ImportError:
        print("Installing required package: Pillow...")
        os.system("pip3 install Pillow")
        try:
            from PIL import Image
        except ImportError:
            return {
                "success": False,
                "error": "Failed to install required package: Pillow (PIL). Please install manually with 'pip install Pillow'"
            }
    
    # Normalize the image path
    full_image_path = os.path.abspath(os.path.expanduser(image_path))
    
    # Check if file exists
    if not os.path.exists(full_image_path):
        return {
            "success": False, 
            "error": f"Image file not found: {full_image_path}"
        }
    
    try:
        
        # Validate it's an image file
        valid_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        file_ext = os.path.splitext(full_image_path)[1].lower()
        if file_ext not in valid_extensions:
            return {
                "success": False, 
                "error": f"File is not a supported image format. Supported formats: {', '.join(valid_extensions)}"
            }
        
        # Try to open and validate the image
        try:
            with Image.open(full_image_path) as img:
                width, height = img.size
                format_type = img.format
                mode = img.mode
        except Exception as e:
            return {
                "success": False, 
                "error": f"Cannot open image file: {str(e)}"
            }
        
        # Read and encode image as base64
        try:
            with open(full_image_path, 'rb') as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            return {
                "success": False, 
                "error": f"Cannot read image file: {str(e)}"
            }
        
        # Get file size
        file_size = os.path.getsize(full_image_path)
        
        # Try to load associated metadata if available (for PDF-extracted images)
        metadata = None
        image_dir = os.path.dirname(full_image_path)
        parent_dir = os.path.dirname(image_dir)
        
        # Look for metadata file in parent directory (typical extract_pdf structure)
        metadata_file = os.path.join(parent_dir, "images_metadata.json")
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    all_metadata = json.load(f)
                
                # Find metadata for this specific image
                image_filename = os.path.basename(full_image_path)
                for img_meta in all_metadata:
                    if img_meta.get('filename') == image_filename:
                        metadata = img_meta.get('metadata', {})
                        break
            except Exception as e:
                logger.warning(f"Could not load metadata: {str(e)}")
        
        # Log tool usage
        db.record_tool_call(
            tool_name="get_image",
            parameters={"image_path": image_path, "file_size": file_size},
            status="success"
        )
        
        logger.info(f"Successfully loaded image: {full_image_path} ({width}x{height}, {file_size} bytes)")
        
        result = {
            "success": True,
            "image": {
                "path": full_image_path,
                "filename": os.path.basename(full_image_path),
                "data": image_data,
                "format": format_type,
                "size": {"width": width, "height": height},
                "file_size": file_size,
                "mode": mode
            }
        }
        
        # Add metadata if available
        if metadata:
            result["image"]["metadata"] = metadata
        
        return result
        
    except Exception as e:
        db.record_tool_call(
            tool_name="get_image",
            parameters={"image_path": image_path, "error": str(e)},
            status="error"
        )
        
        logger.error(f"Error processing image {image_path}: {str(e)}")
        return {
            "success": False, 
            "error": f"Error processing image: {str(e)}"
        }

# ============================================================================
# MCP PROMPTS - Structured Workflows
# ============================================================================

@mcp.prompt()
def extract_and_analyze_datasheet(pdf_path: str, device_type: str = "sensor") -> str:
    """Extract and analyze a device datasheet for firmware development.
    
    Args:
        pdf_path: Path to the datasheet PDF file
        device_type: Type of device (sensor, display, motor_driver, mcu, etc.)
    """
    return f"""Extract and analyze device datasheet for firmware implementation:

DATASHEET: {pdf_path}
DEVICE TYPE: {device_type}

WORKFLOW:

1. **Extract PDF Content**
   - Use extract_pdf("{pdf_path}") to extract markdown and images
   - Note the output folder location
   - This creates: markdown file, images folder, metadata

2. **Read Markdown Content**
   - Read the generated .md file from output folder
   - Focus on key sections:
     * Pin descriptions and configurations
     * Communication protocol (I2C, SPI, UART addresses/timing)
     * Register map and command set
     * Initialization sequence
     * Operating modes and configuration
     * Timing diagrams and specifications

3. **Analyze Images**
   - Check images_metadata.json for available diagrams
   - Use get_image() for critical diagrams:
     * Pin layout / package diagrams
     * Block diagrams
     * Timing diagrams
     * Application circuits
   - Extract pin numbers, connections, required external components

4. **Generate Documentation Files**
   - Create three files in project docs/ folder:
   
   **registers.md:**
   - All register addresses in hex
   - Bit fields and their meanings
   - Read/write permissions
   - Default values
   
   **commands.md:**
   - Communication protocol details (I2C address, SPI mode, etc.)
   - Command sequences for common operations
   - Read/write command formats
   - Response formats
   
   **summary.md:**
   - Device overview and capabilities
   - Complete initialization sequence (step-by-step)
   - Pin configuration requirements
   - Power requirements and timing
   - Example application notes

5. **Identify Key Parameters**
   - Communication address (I2C slave address, SPI CS pin)
   - Clock frequency limits
   - Voltage levels and power requirements
   - Timing constraints (setup, hold times)
   - Required external components (pull-ups, caps, etc.)

6. **Prepare for Implementation**
   - Summarize the initialization sequence
   - List GPIO pins needed
   - Identify required ESP-IDF drivers/APIs
   - Note any special timing or sequencing requirements

IMPORTANT FOR {device_type.upper()}:
- Extract exact register addresses and bit positions
- Note any undocumented but recommended settings
- Identify errata or known issues if mentioned
- Check for application examples or reference code
"""

@mcp.prompt()
def analyze_pdf_document(pdf_path: str, analysis_focus: str = "general") -> str:
    """Extract and analyze any PDF document with specific focus.
    
    Args:
        pdf_path: Path to PDF file
        analysis_focus: Focus area (general, technical, images, tables, code)
    """
    return f"""Analyze PDF document with focus on {analysis_focus}:

PDF FILE: {pdf_path}
ANALYSIS FOCUS: {analysis_focus}

WORKFLOW:

1. **Extract Content**
   - Use extract_pdf("{pdf_path}") 
   - Get markdown text, images, and metadata
   - Note extraction output location

2. **Read Document**
   - Read the generated markdown file
   - Scan for overall structure and key sections
   
3. **Focused Analysis**
   {'- Extract code examples and implementations' if analysis_focus == 'code' else ''}
   {'- Identify and extract all tables' if analysis_focus == 'tables' else ''}
   {'- Analyze all diagrams and figures with get_image()' if analysis_focus == 'images' else ''}
   {'- Extract technical specifications and parameters' if analysis_focus == 'technical' else ''}
   {'- Summarize key information and structure' if analysis_focus == 'general' else ''}

4. **Synthesize Information**
   - Create organized summary of findings
   - Highlight actionable information
   - Note any unclear or ambiguous content

5. **Provide Output**
   - Present extracted information in structured format
   - Include relevant image references
   - Suggest next steps based on content
"""

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
