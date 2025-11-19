"""
HTML to text conversion utility for MCP tools.
Provides a simple way to convert HTML content to plain text.
"""

import re
from html import unescape
from typing import Optional


class HtmlToText:
    """Converts HTML content to plain text."""

    def __init__(self):
        """Initialize the HTML to text converter."""
        pass

    def convert(self, html_content: str) -> str:
        """Convert HTML content to plain text.

        Args:
            html_content: The HTML content to convert

        Returns:
            Plain text version of the HTML content
        """
        if not html_content:
            return ""

        # Remove script and style tags and their content
        html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

        # Remove comments
        html_content = re.sub(r'<!--.*?-->', '', html_content, flags=re.DOTALL)

        # Add line breaks for block elements
        block_elements = [
            'div', 'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'li', 'ul', 'ol', 'blockquote', 'pre', 'hr', 'table',
            'tr', 'td', 'th', 'tbody', 'thead', 'tfoot'
        ]

        for element in block_elements:
            # Add newlines before and after block elements
            html_content = re.sub(f'<{element}[^>]*>', f'\n<{element}>', html_content, flags=re.IGNORECASE)
            html_content = re.sub(f'</{element}>', f'</{element}>\n', html_content, flags=re.IGNORECASE)

        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', '', html_content)

        # Decode HTML entities
        text = unescape(text)

        # Clean up whitespace
        # Replace multiple whitespaces with single space
        text = re.sub(r'\s+', ' ', text)

        # Replace multiple newlines with double newlines
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text
