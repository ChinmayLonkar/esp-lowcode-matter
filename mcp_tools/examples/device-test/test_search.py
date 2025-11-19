#!/usr/bin/env python3
"""
Test script to verify wait_for_pattern functionality
"""

import sys
import os
import time

# Add parent directories to path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, "../../.."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Import directly from server module
from server import SerialMonitor

def test_wait_for_pattern():
    """Test the wait_for_pattern method directly"""
    print('Testing wait_for_pattern method...')

    # Create a mock serial monitor
    monitor = SerialMonitor('/dev/null', 115200)

    # Add some test data manually
    monitor.received_data = [
        {'timestamp': time.time(), 'data': 'ESP32 starting up...'},
        {'timestamp': time.time(), 'data': 'WiFi connecting...'},
        {'timestamp': time.time(), 'data': 'System ready for operation'},
        {'timestamp': time.time(), 'data': 'Temperature sensor initialized'},
        {'timestamp': time.time(), 'data': 'ERROR: Connection failed'},
        {'timestamp': time.time(), 'data': 'I (123) MAIN: Hello World!'},
    ]

    print('Test data added:')
    for i, entry in enumerate(monitor.received_data):
        print(f'  {i+1}: {entry["data"]}')

    print()

    # Test various patterns
    test_patterns = [
        'ESP32',
        'ready',
        'WiFi',
        'temperature',
        'SYSTEM',  # Test case insensitive
        'error',   # Test case insensitive
        'hello',   # Test case insensitive
        'main',    # Test case insensitive
        'nonexistent'
    ]

    for pattern in test_patterns:
        print(f'Testing pattern: "{pattern}"')
        result = monitor.wait_for_pattern(pattern, timeout=0.1)  # Short timeout for testing
        if result:
            print(f'  ✓ Found: {result}')
        else:
            print(f'  ✗ Not found')
        print()

if __name__ == "__main__":
    test_wait_for_pattern()
