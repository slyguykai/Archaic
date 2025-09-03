"""
CDX API Client for Internet Archive Wayback Machine

This module handles communication with the Internet Archive's CDX Server API
to discover all captured URLs matching a specific path pattern.
"""

import requests
import time
from typing import List, Dict, Optional, Set
from urllib.parse import urlparse, urljoin
import logging


class CDXClient:
    """
    Client for interacting with the Internet Archive CDX Server API.
    
    The CDX API allows us to search through the Internet Archive's index
    to find all captured pages matching a specific URL pattern.
    """
    
    CDX_BASE_URL = "http://web.archive.org/cdx/search/cdx"
    
    def __init__(self, request_delay: float = 1.0):
        """
        Initialize the CDX client.
        
        Args:
            request_delay: Delay in seconds between API requests to be respectful
        """
        self.request_delay = request_delay
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Archaic/2.0 (Archival Web Scraper; contact: user@example.com)'
        })
    
    def discover_urls(self, base_url: str) -> List[Dict[str, str]]:
        """
        Discover all unique URLs captured by the Wayback Machine for a given base path.
        
        Args:
            base_url: The base URL pattern to search for (e.g., "example.com/articles/")
        
        Returns:
            List of dictionaries containing URL metadata:
            - 'url': The original URL
            - 'timestamp': The capture timestamp
            - 'wayback_url': The full Wayback Machine URL for accessing the page
            - 'status_code': HTTP status code of the capture
            - 'mime_type': MIME type of the captured content
        
        Raises:
            requests.RequestException: If the CDX API request fails
            ValueError: If the base_url is invalid
        """
        self.logger.info(f"Discovering URLs for pattern: {base_url}")
        
        # Validate and prepare the URL pattern
        url_pattern = self._prepare_url_pattern(base_url)
        
        # Build CDX API parameters
        params = {
            'url': url_pattern,
            'output': 'json',
            'fl': 'timestamp,original,statuscode,mimetype',
            'filter': 'statuscode:200',  # Only successful captures
            'collapse': 'original',       # Remove duplicates by original URL
            'limit': 10000               # Reasonable limit to prevent overwhelming
        }
        
        try:
            # Make the API request with rate limiting
            response = self._make_request(params)
            
            # Parse the response
            urls = self._parse_cdx_response(response.json())
            
            self.logger.info(f"Discovered {len(urls)} unique URLs")
            return urls
            
        except requests.RequestException as e:
            self.logger.error(f"CDX API request failed: {e}")
            raise
        except ValueError as e:
            self.logger.error(f"Invalid response from CDX API: {e}")
            raise
    
    def _prepare_url_pattern(self, base_url: str) -> str:
        """
        Prepare the URL pattern for CDX API search.
        
        Args:
            base_url: User-provided base URL
            
        Returns:
            Properly formatted URL pattern for CDX search
            
        Raises:
            ValueError: If the URL is invalid
        """
        if not base_url:
            raise ValueError("Base URL cannot be empty")
        
        # Add protocol if missing
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        
        # Parse the URL to validate it
        parsed = urlparse(base_url)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL: {base_url}")
        
        # Create wildcard pattern for CDX search
        # If path doesn't end with *, add /*
        if not base_url.endswith('*'):
            if base_url.endswith('/'):
                pattern = base_url + '*'
            else:
                pattern = base_url + '/*'
        else:
            pattern = base_url
        
        self.logger.debug(f"URL pattern prepared: {pattern}")
        return pattern
    
    def _make_request(self, params: Dict) -> requests.Response:
        """
        Make a rate-limited request to the CDX API.
        
        Args:
            params: Query parameters for the CDX API
            
        Returns:
            Response object from the API
            
        Raises:
            requests.RequestException: If the request fails
        """
        # Respectful delay before request
        if self.request_delay > 0:
            time.sleep(self.request_delay)
        
        self.logger.debug(f"Making CDX API request with params: {params}")
        
        response = self.session.get(self.CDX_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        
        return response
    
    def _parse_cdx_response(self, data: List) -> List[Dict[str, str]]:
        """
        Parse the JSON response from the CDX API.
        
        Args:
            data: Raw JSON data from CDX API
            
        Returns:
            List of parsed URL records
            
        Raises:
            ValueError: If the response format is unexpected
        """
        if not data or len(data) == 0:
            return []
        
        # First row contains column headers
        if len(data) < 2:
            return []
        
        headers = data[0]
        rows = data[1:]
        
        # Expected headers: ['timestamp', 'original', 'statuscode', 'mimetype']
        if len(headers) < 4:
            raise ValueError("Unexpected CDX response format: insufficient columns")
        
        urls = []
        seen_urls: Set[str] = set()
        
        for row in rows:
            if len(row) < 4:
                continue  # Skip malformed rows
            
            timestamp, original_url, status_code, mime_type = row[:4]
            
            # Skip if we've already seen this URL (additional deduplication)
            if original_url in seen_urls:
                continue
            seen_urls.add(original_url)
            
            # Only include HTML content
            if not mime_type.startswith('text/html'):
                continue
            
            # Construct the Wayback Machine URL
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
            
            urls.append({
                'url': original_url,
                'timestamp': timestamp,
                'wayback_url': wayback_url,
                'status_code': status_code,
                'mime_type': mime_type
            })
        
        return urls
    
    def get_latest_capture(self, url: str) -> Optional[Dict[str, str]]:
        """
        Get the most recent capture of a specific URL.
        
        Args:
            url: The specific URL to find the latest capture for
            
        Returns:
            Dictionary with capture metadata, or None if not found
        """
        params = {
            'url': url,
            'output': 'json',
            'fl': 'timestamp,original,statuscode,mimetype',
            'filter': 'statuscode:200',
            'limit': 1,
            'sort': 'reverse'  # Most recent first
        }
        
        try:
            response = self._make_request(params)
            data = response.json()
            
            if len(data) < 2:
                return None
            
            row = data[1]  # Skip headers
            if len(row) < 4:
                return None
            
            timestamp, original_url, status_code, mime_type = row[:4]
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
            
            return {
                'url': original_url,
                'timestamp': timestamp,
                'wayback_url': wayback_url,
                'status_code': status_code,
                'mime_type': mime_type
            }
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to get latest capture for {url}: {e}")
            return None
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()