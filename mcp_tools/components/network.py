#!/usr/bin/env python3
"""
Networking module for MCP tools.
Provides a reusable HTTP client and API utilities.
"""

import aiohttp
import asyncio
import json
import logging
import time
import ssl
from typing import Dict, List, Any, Optional, Union, Tuple, Callable
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

class NetworkError(Exception):
    """Base exception for network-related errors."""
    pass

class HttpError(NetworkError):
    """HTTP error with status code."""

    def __init__(self, status_code: int, message: str, response_data: Any = None):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(f"HTTP error {status_code}: {message}")

class RateLimitError(HttpError):
    """Rate limit exceeded error."""

    def __init__(self, status_code: int, message: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(status_code, message)

class ApiClient:
    """Reusable HTTP client for API calls.

    Features:
    - Connection pooling
    - Automatic retries
    - Rate limiting
    - Request/response logging
    - JSON handling
    - Authentication
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        auth: Optional[aiohttp.BasicAuth] = None,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 2,
        verify_ssl: bool = True,
        user_agent: str = "MCP-Tool/1.0"
    ):
        """Initialize the API client.

        Args:
            base_url: Base URL for API requests
            headers: Default headers to send with every request
            auth: Basic authentication credentials
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            verify_ssl: Whether to verify SSL certificates
            user_agent: User agent string
        """
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self.auth = auth
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.verify_ssl = verify_ssl
        self.session = None

        # Set default headers
        if 'User-Agent' not in self.headers:
            self.headers['User-Agent'] = user_agent
        if 'Accept' not in self.headers:
            self.headers['Accept'] = 'application/json'

        # Rate limiting state
        self._rate_limit_remaining = None
        self._rate_limit_reset = None

    async def __aenter__(self):
        """Create a session when entering the context manager."""
        await self.create_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close the session when exiting the context manager."""
        await self.close_session()

    async def create_session(self):
        """Create a new HTTP session."""
        if self.session is None or self.session.closed:
            ssl_context = None
            if not self.verify_ssl:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            # Create TCP connector with connection pooling
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=100,  # Max simultaneous connections
                ttl_dns_cache=300  # Cache DNS results for 5 minutes
            )

            self.session = aiohttp.ClientSession(
                connector=connector,
                headers=self.headers,
                auth=self.auth,
                raise_for_status=False,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )

    async def close_session(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    def build_url(self, path: str) -> str:
        """Build a full URL from a path.

        Args:
            path: API endpoint path

        Returns:
            Full URL
        """
        # Handle absolute URLs
        if path.startswith(('http://', 'https://')):
            return path

        # Handle relative paths
        path = path.lstrip('/')
        return f"{self.base_url}/{path}"

    async def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        json_data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        auth: Optional[aiohttp.BasicAuth] = None,
        timeout: Optional[int] = None,
        retry_on_status: Optional[List[int]] = None,
        handle_rate_limit: bool = True,
        parse_json: bool = True
    ) -> Tuple[Any, Dict[str, str]]:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API endpoint path
            params: Query parameters
            data: Request body (for form data)
            json_data: Request body (for JSON data)
            headers: Additional headers for this request
            auth: Authentication credentials for this request
            timeout: Request timeout in seconds
            retry_on_status: List of status codes to retry on
            handle_rate_limit: Whether to handle rate limiting
            parse_json: Whether to parse the response as JSON

        Returns:
            Tuple of (response_data, response_headers)

        Raises:
            HttpError: If the request fails
            RateLimitError: If rate limit is exceeded
            NetworkError: If a network error occurs
        """
        if self.session is None or self.session.closed:
            await self.create_session()

        url = self.build_url(path)
        retry_on_status = retry_on_status or [429, 500, 502, 503, 504]
        request_timeout = aiohttp.ClientTimeout(total=timeout or self.timeout)

        # Combine default headers with request-specific headers
        merged_headers = {**self.headers}
        if headers:
            merged_headers.update(headers)

        # Handle rate limiting
        if handle_rate_limit and self._rate_limit_remaining == 0 and self._rate_limit_reset:
            delay = max(0, self._rate_limit_reset - time.time())
            if delay > 0:
                logger.info(f"Rate limit exceeded. Waiting for {delay:.2f} seconds")
                await asyncio.sleep(delay)

        # Perform the request with retries
        retries = 0
        while True:
            try:
                start_time = time.time()

                # Log the request
                logger.debug(f"Request: {method} {url}")
                if params:
                    logger.debug(f"Params: {params}")
                if json_data:
                    logger.debug(f"JSON data: {json_data}")

                # Make the request
                async with self.session.request(
                    method,
                    url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=merged_headers,
                    auth=auth or self.auth,
                    timeout=request_timeout
                ) as response:
                    # Extract rate limit headers
                    if handle_rate_limit:
                        self._rate_limit_remaining = int(response.headers.get('X-RateLimit-Remaining', '1000'))
                        reset_value = response.headers.get('X-RateLimit-Reset')
                        if reset_value:
                            try:
                                self._rate_limit_reset = int(reset_value)
                            except ValueError:
                                pass

                    # Handle response
                    status_code = response.status
                    elapsed = time.time() - start_time
                    logger.debug(f"Response: {status_code} ({elapsed:.2f}s)")

                    # Check if we need to retry
                    if status_code in retry_on_status and retries < self.max_retries:
                        retries += 1
                        wait_time = self.retry_delay * (2 ** (retries - 1))  # Exponential backoff

                        # Check for retry-after header
                        retry_after = response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                wait_time = int(retry_after)
                            except ValueError:
                                pass

                        logger.info(f"Retrying in {wait_time} seconds (attempt {retries}/{self.max_retries})")
                        await asyncio.sleep(wait_time)
                        continue

                    # Handle rate limiting
                    if status_code == 429:
                        retry_after = None
                        try:
                            retry_after = int(response.headers.get('Retry-After', 0))
                        except ValueError:
                            pass

                        content = await response.text()
                        raise RateLimitError(status_code, content, retry_after)

                    # Handle errors
                    if status_code >= 400:
                        content = await response.text()
                        error_data = None
                        if parse_json:
                            try:
                                error_data = json.loads(content)
                            except json.JSONDecodeError:
                                pass
                        raise HttpError(status_code, content, error_data)

                    # Parse successful response
                    if parse_json and 'application/json' in response.headers.get('Content-Type', ''):
                        response_data = await response.json()
                    else:
                        response_data = await response.text()

                    return response_data, dict(response.headers)

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                # Handle network errors
                if retries < self.max_retries:
                    retries += 1
                    wait_time = self.retry_delay * (2 ** (retries - 1))
                    logger.warning(f"Network error: {e}. Retrying in {wait_time} seconds (attempt {retries}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Network error after {self.max_retries} retries: {e}")
                    raise NetworkError(f"Network error: {e}") from e

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """Make a GET request.

        Args:
            path: API endpoint path
            params: Query parameters
            **kwargs: Additional arguments for request()

        Returns:
            Response data
        """
        data, _ = await self.request('GET', path, params=params, **kwargs)
        return data

    async def post(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        json_data: Any = None,
        **kwargs
    ) -> Any:
        """Make a POST request.

        Args:
            path: API endpoint path
            params: Query parameters
            data: Form data
            json_data: JSON data
            **kwargs: Additional arguments for request()

        Returns:
            Response data
        """
        data, _ = await self.request('POST', path, params=params, data=data, json_data=json_data, **kwargs)
        return data

    async def put(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        json_data: Any = None,
        **kwargs
    ) -> Any:
        """Make a PUT request.

        Args:
            path: API endpoint path
            params: Query parameters
            data: Form data
            json_data: JSON data
            **kwargs: Additional arguments for request()

        Returns:
            Response data
        """
        data, _ = await self.request('PUT', path, params=params, data=data, json_data=json_data, **kwargs)
        return data

    async def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """Make a DELETE request.

        Args:
            path: API endpoint path
            params: Query parameters
            **kwargs: Additional arguments for request()

        Returns:
            Response data
        """
        data, _ = await self.request('DELETE', path, params=params, **kwargs)
        return data

    async def paginate(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data_key: str = "data",
        page_param: str = "page",
        limit_param: Optional[str] = "limit",
        page_size: int = 50,
        max_pages: Optional[int] = None,
        **kwargs
    ) -> List[Any]:
        """Paginate through a collection endpoint.

        Args:
            path: API endpoint path
            params: Base query parameters
            data_key: Key in the response that contains the data array
            page_param: Name of the page parameter
            limit_param: Name of the limit/size parameter
            page_size: Number of items per page
            max_pages: Maximum number of pages to fetch
            **kwargs: Additional arguments for request()

        Returns:
            List of all items across all pages
        """
        all_items = []
        page = 1
        params = params or {}

        if limit_param:
            params[limit_param] = page_size

        while True:
            params[page_param] = page
            response_data, _ = await self.request('GET', path, params=params, **kwargs)

            # Extract data items
            page_items = response_data.get(data_key, [])
            all_items.extend(page_items)

            # Check if we're done
            if not page_items or len(page_items) < page_size:
                break

            # Check if we've reached the maximum number of pages
            if max_pages and page >= max_pages:
                break

            page += 1

        return all_items


class OAuthClient(ApiClient):
    """API client with OAuth2 authentication support."""

    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        token_url: str,
        scopes: Optional[List[str]] = None,
        **kwargs
    ):
        """Initialize the OAuth client.

        Args:
            base_url: Base URL for API requests
            client_id: OAuth client ID
            client_secret: OAuth client secret
            token_url: URL to request access tokens
            scopes: OAuth scopes to request
            **kwargs: Additional arguments for ApiClient.__init__()
        """
        super().__init__(base_url, **kwargs)
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.scopes = scopes or []

        self.access_token = None
        self.refresh_token = None
        self.token_expiry = 0

    async def ensure_token(self):
        """Ensure we have a valid access token.

        Get a new token if we don't have one, or refresh it if it's expired.
        """
        if not self.access_token or time.time() >= self.token_expiry:
            if self.refresh_token:
                await self.refresh_access_token()
            else:
                await self.get_access_token()

    async def get_access_token(self):
        """Get a new access token using client credentials flow."""
        if self.session is None or self.session.closed:
            await self.create_session()

        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        if self.scopes:
            data['scope'] = ' '.join(self.scopes)

        async with self.session.post(self.token_url, data=data) as response:
            if response.status >= 400:
                text = await response.text()
                raise HttpError(response.status, f"Failed to get access token: {text}")

            token_data = await response.json()
            self.access_token = token_data.get('access_token')
            self.refresh_token = token_data.get('refresh_token')

            expires_in = token_data.get('expires_in', 3600)
            self.token_expiry = time.time() + expires_in - 60  # Refresh 60 seconds before expiry

            # Update authorization header
            self.headers['Authorization'] = f"Bearer {self.access_token}"

    async def refresh_access_token(self):
        """Refresh the access token using the refresh token."""
        if not self.refresh_token:
            await self.get_access_token()
            return

        if self.session is None or self.session.closed:
            await self.create_session()

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        async with self.session.post(self.token_url, data=data) as response:
            if response.status >= 400:
                # If refresh fails, try getting a new token
                await self.get_access_token()
                return

            token_data = await response.json()
            self.access_token = token_data.get('access_token')

            # Update refresh token if provided
            if 'refresh_token' in token_data:
                self.refresh_token = token_data.get('refresh_token')

            expires_in = token_data.get('expires_in', 3600)
            self.token_expiry = time.time() + expires_in - 60

            # Update authorization header
            self.headers['Authorization'] = f"Bearer {self.access_token}"

    async def request(self, method: str, path: str, **kwargs):
        """Make an authenticated request.

        Ensures we have a valid access token before making the request.
        """
        await self.ensure_token()
        return await super().request(method, path, **kwargs)
