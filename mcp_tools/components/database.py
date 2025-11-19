#!/usr/bin/env python3
"""
Database module for MCP tools.
Provides a reusable database interface with SQLite support.
"""

import os
import sqlite3
import json
import threading
import logging
from typing import Dict, List, Any, Optional, Union, Tuple

logger = logging.getLogger(__name__)

class Database:
    """Base database class with SQLite implementation.

    This class provides a simple interface for working with SQLite databases.
    It includes support for:
    - Connection management
    - Basic CRUD operations
    - Transaction support
    - Schema initialization
    - JSON serialization/deserialization
    """

    def __init__(self, database_path: str, initialize_schema: bool = True):
        """Initialize the database.

        Args:
            database_path: Path to the SQLite database file
            initialize_schema: Whether to initialize the schema (create tables) on startup
        """
        self.database_path = database_path
        self._connection = None
        self._lock = threading.RLock()

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)

        # Connect to the database
        self.connect()

        # Initialize schema if requested
        if initialize_schema:
            self.initialize_schema()

    def connect(self) -> None:
        """Connect to the database."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,  # Allow access from multiple threads
                isolation_level=None  # Enable autocommit mode
            )
            # Enable foreign keys
            self._connection.execute("PRAGMA foreign_keys = ON")
            # Use Row factory for better column access
            self._connection.row_factory = sqlite3.Row

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def initialize_schema(self) -> None:
        """Initialize the database schema.

        This method should be overridden by subclasses to create the necessary tables.
        """
        pass

    def execute(self, query: str, parameters: tuple = ()) -> sqlite3.Cursor:
        """Execute a SQL query.

        Args:
            query: SQL query to execute
            parameters: Parameters for the query

        Returns:
            SQLite cursor object
        """
        with self._lock:
            try:
                self.connect()
                cursor = self._connection.execute(query, parameters)
                return cursor
            except sqlite3.Error as e:
                logger.error(f"Database error executing '{query}': {e}")
                raise

    def executemany(self, query: str, parameters_list: List[tuple]) -> sqlite3.Cursor:
        """Execute a SQL query with multiple parameter sets.

        Args:
            query: SQL query to execute
            parameters_list: List of parameter tuples

        Returns:
            SQLite cursor object
        """
        with self._lock:
            try:
                self.connect()
                cursor = self._connection.executemany(query, parameters_list)
                return cursor
            except sqlite3.Error as e:
                logger.error(f"Database error executing '{query}': {e}")
                raise

    def transaction(self):
        """Start a transaction.

        Returns:
            Transaction context manager
        """
        return Transaction(self)

    def fetch_one(self, query: str, parameters: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row from the database.

        Args:
            query: SQL query to execute
            parameters: Parameters for the query

        Returns:
            Dictionary with column names as keys, or None if no row found
        """
        cursor = self.execute(query, parameters)
        row = cursor.fetchone()
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def fetch_all(self, query: str, parameters: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows from the database.

        Args:
            query: SQL query to execute
            parameters: Parameters for the query

        Returns:
            List of dictionaries with column names as keys
        """
        cursor = self.execute(query, parameters)
        rows = cursor.fetchall()
        return [{key: row[key] for key in row.keys()} for row in rows]

    def insert(self, table: str, data: Dict[str, Any]) -> int:
        """Insert a row into the database.

        Args:
            table: Table name
            data: Dictionary of column names and values

        Returns:
            ID of the inserted row
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data.keys()])
        values = tuple(self._serialize_value(v) for v in data.values())

        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        cursor = self.execute(query, values)
        return cursor.lastrowid

    def update(self, table: str, data: Dict[str, Any], where: str, where_params: tuple) -> int:
        """Update rows in the database.

        Args:
            table: Table name
            data: Dictionary of column names and values to update
            where: WHERE clause without the "WHERE" keyword
            where_params: Parameters for the WHERE clause

        Returns:
            Number of rows affected
        """
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        values = tuple(self._serialize_value(v) for v in data.values())

        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        cursor = self.execute(query, values + where_params)
        return cursor.rowcount

    def delete(self, table: str, where: str, where_params: tuple) -> int:
        """Delete rows from the database.

        Args:
            table: Table name
            where: WHERE clause without the "WHERE" keyword
            where_params: Parameters for the WHERE clause

        Returns:
            Number of rows affected
        """
        query = f"DELETE FROM {table} WHERE {where}"
        cursor = self.execute(query, where_params)
        return cursor.rowcount

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for storage in the database.

        Complex objects like dictionaries and lists are serialized to JSON.

        Args:
            value: Value to serialize

        Returns:
            Serialized value
        """
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    def _deserialize_value(self, value: Any, column_type: str) -> Any:
        """Deserialize a value from the database.

        Args:
            value: Value to deserialize
            column_type: Column type

        Returns:
            Deserialized value
        """
        if value is None:
            return None

        if column_type.lower() == 'json' and isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        return value


class Transaction:
    """Database transaction context manager."""

    def __init__(self, database: Database):
        """Initialize the transaction.

        Args:
            database: Database instance
        """
        self.database = database

    def __enter__(self):
        """Start the transaction."""
        with self.database._lock:
            self.database.connect()
            self.database.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End the transaction.

        If an exception occurred, roll back the transaction.
        Otherwise, commit the transaction.
        """
        with self.database._lock:
            if exc_type is not None:
                # An exception occurred, roll back
                self.database.execute("ROLLBACK")
            else:
                # No exception, commit
                self.database.execute("COMMIT")
        return False  # Don't suppress exceptions


class ToolDatabase(Database):
    """Database for storing tool data.

    This is a sample implementation that can be extended for specific tools.
    It provides tables for:
    - Tool history: Records of tool calls
    - Tool data: Arbitrary data stored by tools
    """

    def initialize_schema(self) -> None:
        """Initialize the database schema with tool-related tables."""
        # Tool history table
        self.execute("""
            CREATE TABLE IF NOT EXISTS tool_history (
                id INTEGER PRIMARY KEY,
                tool_name TEXT NOT NULL,
                parameters TEXT,  -- JSON encoded parameters
                result TEXT,      -- JSON encoded result
                status TEXT NOT NULL,
                error_message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tool data table for arbitrary data storage
        self.execute("""
            CREATE TABLE IF NOT EXISTS tool_data (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                value TEXT,       -- JSON encoded value
                tool_name TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(key, tool_name)
            )
        """)

    def record_tool_call(self, tool_name: str, parameters: Dict[str, Any],
                        result: Any = None, status: str = "success",
                        error_message: Optional[str] = None) -> int:
        """Record a tool call in the history.

        Args:
            tool_name: Name of the tool
            parameters: Parameters passed to the tool
            result: Result returned by the tool
            status: Status of the tool call (success, error)
            error_message: Error message if status is error

        Returns:
            ID of the history record
        """
        return self.insert("tool_history", {
            "tool_name": tool_name,
            "parameters": parameters,
            "result": result,
            "status": status,
            "error_message": error_message
        })

    def get_tool_history(self, tool_name: Optional[str] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
        """Get the history of tool calls.

        Args:
            tool_name: Filter by tool name
            limit: Maximum number of records to return

        Returns:
            List of tool call records
        """
        if tool_name:
            return self.fetch_all(
                "SELECT * FROM tool_history WHERE tool_name = ? ORDER BY timestamp DESC LIMIT ?",
                (tool_name, limit)
            )
        else:
            return self.fetch_all(
                "SELECT * FROM tool_history ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            )

    def store_data(self, key: str, value: Any, tool_name: str) -> int:
        """Store arbitrary data for a tool.

        Args:
            key: Data key
            value: Data value
            tool_name: Name of the tool

        Returns:
            ID of the data record
        """
        # Use INSERT OR REPLACE to handle the uniqueness constraint
        self.execute(
            "INSERT OR REPLACE INTO tool_data (key, value, tool_name) VALUES (?, ?, ?)",
            (key, json.dumps(value), tool_name)
        )
        return self.fetch_one(
            "SELECT id FROM tool_data WHERE key = ? AND tool_name = ?",
            (key, tool_name)
        )["id"]

    def get_data(self, key: str, tool_name: str) -> Any:
        """Get stored data for a tool.

        Args:
            key: Data key
            tool_name: Name of the tool

        Returns:
            Stored data value
        """
        row = self.fetch_one(
            "SELECT value FROM tool_data WHERE key = ? AND tool_name = ?",
            (key, tool_name)
        )
        if row is None:
            return None

        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def delete_data(self, key: str, tool_name: str) -> bool:
        """Delete stored data for a tool.

        Args:
            key: Data key
            tool_name: Name of the tool

        Returns:
            True if data was deleted, False otherwise
        """
        rows_affected = self.delete(
            "tool_data",
            "key = ? AND tool_name = ?",
            (key, tool_name)
        )
        return rows_affected > 0
