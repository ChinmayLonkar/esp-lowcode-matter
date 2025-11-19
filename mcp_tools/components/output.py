#!/usr/bin/env python3
"""
Output formatting module for MCP tools.
Provides consistent data presentation for different output formats.
"""

import json
import logging
import sys
import os
import csv
import io
from typing import Dict, List, Any, Optional, Union, Callable, TextIO
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)

class OutputFormat(Enum):
    """Supported output formats."""
    TEXT = "text"
    JSON = "json"
    CSV = "csv"
    TABLE = "table"

class Formatter:
    """Base formatter interface."""

    def format(self, data: Any) -> str:
        """Format data as string.

        Args:
            data: Data to format

        Returns:
            Formatted string
        """
        raise NotImplementedError()


class TextFormatter(Formatter):
    """Simple text formatter."""

    def __init__(self, indent: int = 2):
        """Initialize text formatter.

        Args:
            indent: Indentation level for nested structures
        """
        self.indent = indent

    def format(self, data: Any) -> str:
        """Format data as plain text.

        Args:
            data: Data to format

        Returns:
            Formatted string
        """
        if data is None:
            return "None"

        if isinstance(data, (int, float, bool, str)):
            return str(data)

        if isinstance(data, list):
            if not data:
                return "[]"

            lines = []
            for item in data:
                item_str = self.format(item)
                # Indent multiline items
                if "\n" in item_str:
                    item_str = item_str.replace("\n", "\n" + " " * self.indent)
                lines.append(f"{' ' * self.indent}- {item_str}")

            return "\n" + "\n".join(lines)

        if isinstance(data, dict):
            if not data:
                return "{}"

            lines = []
            for key, value in data.items():
                value_str = self.format(value)
                # Indent multiline values
                if "\n" in value_str:
                    value_str = value_str.replace("\n", "\n" + " " * self.indent)
                lines.append(f"{' ' * self.indent}{key}: {value_str}")

            return "\n" + "\n".join(lines)

        # Try string representation for other types
        return str(data)


class JsonFormatter(Formatter):
    """JSON formatter with customizable options."""

    def __init__(self, indent: int = 2, sort_keys: bool = False):
        """Initialize JSON formatter.

        Args:
            indent: Number of spaces for indentation
            sort_keys: Whether to sort keys alphabetically
        """
        self.indent = indent
        self.sort_keys = sort_keys

    def format(self, data: Any) -> str:
        """Format data as JSON.

        Args:
            data: Data to format

        Returns:
            JSON string
        """
        try:
            return json.dumps(
                data,
                indent=self.indent,
                sort_keys=self.sort_keys,
                default=self._json_default
            )
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON serialization error: {e}")
            # Fallback to string representation
            return str(data)

    def _json_default(self, obj: Any) -> Any:
        """Handle non-serializable objects in JSON.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable representation
        """
        if isinstance(obj, datetime):
            return obj.isoformat()

        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            return obj.to_dict()

        if hasattr(obj, "__dict__"):
            return obj.__dict__

        return str(obj)


class CsvFormatter(Formatter):
    """CSV formatter for tabular data."""

    def __init__(self, delimiter: str = ",", quoting: int = csv.QUOTE_MINIMAL):
        """Initialize CSV formatter.

        Args:
            delimiter: Field delimiter
            quoting: Quoting style
        """
        self.delimiter = delimiter
        self.quoting = quoting

    def format(self, data: Any) -> str:
        """Format data as CSV.

        Handles:
        - List of dictionaries (rows with headers)
        - List of lists (rows with optional header row)
        - Dictionary (single row with headers)

        Args:
            data: Data to format

        Returns:
            CSV string
        """
        output = io.StringIO()
        writer = csv.writer(
            output,
            delimiter=self.delimiter,
            quoting=self.quoting,
            lineterminator="\n"
        )

        if isinstance(data, list):
            if not data:
                return ""

            if isinstance(data[0], dict):
                # List of dictionaries
                fieldnames = list(data[0].keys())
                writer.writerow(fieldnames)

                for row in data:
                    writer.writerow([
                        self._format_value(row.get(field, ""))
                        for field in fieldnames
                    ])

            else:
                # List of lists
                for row in data:
                    writer.writerow([self._format_value(v) for v in row])

        elif isinstance(data, dict):
            # Single dictionary
            writer.writerow(data.keys())
            writer.writerow([self._format_value(v) for v in data.values()])

        else:
            # Single value
            writer.writerow([self._format_value(data)])

        return output.getvalue()

    def _format_value(self, value: Any) -> str:
        """Format a value for CSV.

        Handles complex types by converting to JSON.

        Args:
            value: Value to format

        Returns:
            String representation
        """
        if value is None:
            return ""

        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False)
            except (TypeError, ValueError):
                return str(value)

        return str(value)


class TableFormatter(Formatter):
    """Text table formatter for tabular data."""

    def __init__(self, max_width: int = 80, show_header: bool = True, border: bool = True):
        """Initialize table formatter.

        Args:
            max_width: Maximum width of the table
            show_header: Whether to show header row
            border: Whether to show table borders
        """
        self.max_width = max_width
        self.show_header = show_header
        self.border = border

    def format(self, data: Any) -> str:
        """Format data as text table.

        Args:
            data: Data to format

        Returns:
            Text table
        """
        if not data:
            return "Empty data"

        if isinstance(data, list):
            if not data:
                return "Empty list"

            if isinstance(data[0], dict):
                # List of dictionaries
                return self._format_dict_list(data)

            if isinstance(data[0], (list, tuple)):
                # List of lists
                return self._format_list_list(data)

        if isinstance(data, dict):
            # Single dictionary as key-value pairs
            return self._format_key_value(data)

        # Not tabular data, use text formatter
        return TextFormatter().format(data)

    def _format_dict_list(self, data: List[Dict[str, Any]]) -> str:
        """Format a list of dictionaries as a table.

        Args:
            data: List of dictionaries

        Returns:
            Text table
        """
        # Extract all keys from all dictionaries
        all_keys = set()
        for row in data:
            all_keys.update(row.keys())

        headers = sorted(all_keys)
        rows = []

        for row in data:
            rows.append([self._format_cell(row.get(key, "")) for key in headers])

        return self._render_table(headers, rows)

    def _format_list_list(self, data: List[List[Any]]) -> str:
        """Format a list of lists as a table.

        Args:
            data: List of lists

        Returns:
            Text table
        """
        if len(data) == 0:
            return "Empty table"

        # Determine the maximum number of columns
        max_cols = max(len(row) for row in data)

        headers = None
        rows = []

        if self.show_header and len(data) > 1:
            # Use first row as header
            headers = [self._format_cell(cell) for cell in data[0]]
            # Pad header if necessary
            headers.extend([""] * (max_cols - len(headers)))
            # Use remaining rows as data
            for row in data[1:]:
                formatted_row = [self._format_cell(cell) for cell in row]
                # Pad row if necessary
                formatted_row.extend([""] * (max_cols - len(formatted_row)))
                rows.append(formatted_row)
        else:
            # No header
            headers = [f"Column {i+1}" for i in range(max_cols)]
            for row in data:
                formatted_row = [self._format_cell(cell) for cell in row]
                # Pad row if necessary
                formatted_row.extend([""] * (max_cols - len(formatted_row)))
                rows.append(formatted_row)

        return self._render_table(headers, rows)

    def _format_key_value(self, data: Dict[str, Any]) -> str:
        """Format a dictionary as a key-value table.

        Args:
            data: Dictionary

        Returns:
            Text table
        """
        headers = ["Key", "Value"]
        rows = [[key, self._format_cell(value)] for key, value in data.items()]
        return self._render_table(headers, rows)

    def _format_cell(self, value: Any) -> str:
        """Format a cell value.

        Args:
            value: Cell value

        Returns:
            Formatted string
        """
        if value is None:
            return ""

        if isinstance(value, (dict, list)):
            try:
                json_str = json.dumps(value, ensure_ascii=False)
                if len(json_str) > 30:
                    return json_str[:27] + "..."
                return json_str
            except (TypeError, ValueError):
                cell = str(value)
        else:
            cell = str(value)

        # Truncate long values
        if len(cell) > 30:
            return cell[:27] + "..."

        return cell

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render a table with headers and rows.

        Args:
            headers: Column headers
            rows: Table rows

        Returns:
            Rendered table
        """
        if not headers or not rows:
            return "Empty table"

        # Calculate column widths
        num_columns = len(headers)
        col_widths = [len(h) for h in headers]

        for row in rows:
            for i, cell in enumerate(row):
                if i < num_columns:
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Adjust column widths to fit max_width
        available_width = self.max_width - num_columns - 1
        if self.border:
            available_width -= num_columns + 1

        if sum(col_widths) > available_width:
            # Simple strategy: Distribute width proportionally
            excess = sum(col_widths) - available_width
            for i in range(num_columns):
                proportion = col_widths[i] / sum(col_widths)
                reduction = int(excess * proportion)
                col_widths[i] = max(5, col_widths[i] - reduction)

        # Render table
        result = []

        if self.border:
            # Top border
            result.append("+" + "+".join("-" * (w + 2) for w in col_widths) + "+")

            # Header row
            header_cells = []
            for i, header in enumerate(headers):
                cell = header
                if len(cell) > col_widths[i]:
                    cell = cell[:col_widths[i]-3] + "..."
                header_cells.append(f" {cell:{col_widths[i]}} ")
            result.append("|" + "|".join(header_cells) + "|")

            # Header separator
            result.append("+" + "+".join("=" * (w + 2) for w in col_widths) + "+")

            # Data rows
            for row in rows:
                row_cells = []
                for i, cell in enumerate(row):
                    if i < num_columns:
                        cell_str = str(cell)
                        if len(cell_str) > col_widths[i]:
                            cell_str = cell_str[:col_widths[i]-3] + "..."
                        row_cells.append(f" {cell_str:{col_widths[i]}} ")
                result.append("|" + "|".join(row_cells) + "|")

            # Bottom border
            result.append("+" + "+".join("-" * (w + 2) for w in col_widths) + "+")
        else:
            # Header row
            header_cells = []
            for i, header in enumerate(headers):
                cell = header
                if len(cell) > col_widths[i]:
                    cell = cell[:col_widths[i]-3] + "..."
                header_cells.append(f"{cell:{col_widths[i]}}")
            result.append(" ".join(header_cells))

            # Header separator
            result.append(" ".join("-" * w for w in col_widths))

            # Data rows
            for row in rows:
                row_cells = []
                for i, cell in enumerate(row):
                    if i < num_columns:
                        cell_str = str(cell)
                        if len(cell_str) > col_widths[i]:
                            cell_str = cell_str[:col_widths[i]-3] + "..."
                        row_cells.append(f"{cell_str:{col_widths[i]}}")
                result.append(" ".join(row_cells))

        return "\n".join(result)


class OutputManager:
    """Manages output formatting and destination.

    Features:
    - Multiple output formats
    - File or stream output
    - Progress indicators
    - Color support
    """

    def __init__(
        self,
        format: Union[str, OutputFormat] = OutputFormat.TEXT,
        output_file: Optional[Union[str, TextIO]] = None,
        color: bool = True
    ):
        """Initialize output manager.

        Args:
            format: Output format (text, json, csv, table)
            output_file: Output file path or stream
            color: Whether to use ANSI colors
        """
        self.format = OutputFormat(format) if isinstance(format, str) else format
        self.output_file = output_file
        self.color = color and sys.stdout.isatty() and os.name != 'nt'

        # Create formatter
        if self.format == OutputFormat.JSON:
            self.formatter = JsonFormatter()
        elif self.format == OutputFormat.CSV:
            self.formatter = CsvFormatter()
        elif self.format == OutputFormat.TABLE:
            self.formatter = TableFormatter()
        else:
            self.formatter = TextFormatter()

        # Output stream
        self.stream = None
        if isinstance(output_file, str):
            self.stream = open(output_file, 'w', encoding='utf-8')
        elif hasattr(output_file, 'write'):
            self.stream = output_file
        else:
            self.stream = sys.stdout

        # Colors
        self.COLORS = {
            'reset': '\033[0m',
            'bold': '\033[1m',
            'red': '\033[31m',
            'green': '\033[32m',
            'yellow': '\033[33m',
            'blue': '\033[34m',
            'magenta': '\033[35m',
            'cyan': '\033[36m',
            'white': '\033[37m',
            'gray': '\033[90m'
        }

    def __del__(self):
        """Close file if needed."""
        if isinstance(self.output_file, str) and self.stream and self.stream != sys.stdout:
            self.stream.close()

    def colorize(self, text: str, color: str) -> str:
        """Add color to text.

        Args:
            text: Text to colorize
            color: Color name

        Returns:
            Colorized string if colors enabled
        """
        if not self.color or color not in self.COLORS:
            return text

        return f"{self.COLORS[color]}{text}{self.COLORS['reset']}"

    def output(self, data: Any) -> None:
        """Format and output data.

        Args:
            data: Data to output
        """
        formatted = self.formatter.format(data)
        print(formatted, file=self.stream)

    def print(self, *args, color: Optional[str] = None, **kwargs) -> None:
        """Print with optional color.

        Args:
            *args: Values to print
            color: Optional color
            **kwargs: Print options
        """
        if color and self.color:
            parts = [str(arg) for arg in args]
            colored = self.colorize(" ".join(parts), color)
            print(colored, file=self.stream, **kwargs)
        else:
            print(*args, file=self.stream, **kwargs)

    def error(self, message: str) -> None:
        """Print error message.

        Args:
            message: Error message
        """
        self.print(f"ERROR: {message}", color='red')

    def warning(self, message: str) -> None:
        """Print warning message.

        Args:
            message: Warning message
        """
        self.print(f"WARNING: {message}", color='yellow')

    def success(self, message: str) -> None:
        """Print success message.

        Args:
            message: Success message
        """
        self.print(f"SUCCESS: {message}", color='green')

    def info(self, message: str) -> None:
        """Print info message.

        Args:
            message: Info message
        """
        self.print(f"INFO: {message}", color='blue')

    def debug(self, message: str) -> None:
        """Print debug message.

        Args:
            message: Debug message
        """
        self.print(f"DEBUG: {message}", color='gray')

    def progress(self, message: str, count: int, total: int) -> None:
        """Print progress message.

        Args:
            message: Progress message
            count: Current count
            total: Total count
        """
        percent = (count / total) * 100 if total > 0 else 0
        progress_bar = self._create_progress_bar(count, total)
        self.print(f"{message}: {progress_bar} {count}/{total} ({percent:.1f}%)", color='cyan')

    def _create_progress_bar(self, count: int, total: int, width: int = 20) -> str:
        """Create a text progress bar.

        Args:
            count: Current count
            total: Total count
            width: Width of the progress bar

        Returns:
            Text progress bar
        """
        percent = min(1.0, count / total if total > 0 else 0)
        filled_length = int(width * percent)
        bar = '█' * filled_length + '░' * (width - filled_length)
        return f"[{bar}]"


def get_output_manager(
    format: str = "text",
    output_file: Optional[str] = None,
    color: bool = True
) -> OutputManager:
    """Create an output manager with the specified options.

    Args:
        format: Output format (text, json, csv, table)
        output_file: Output file path
        color: Whether to use colors

    Returns:
        Configured OutputManager
    """
    return OutputManager(format=format, output_file=output_file, color=color)
