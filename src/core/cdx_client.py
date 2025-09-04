"""
CDX API Client for Internet Archive Wayback Machine

This module handles communication with the Internet Archive's CDX Server API
to discover all captured URLs matching a specific path pattern.
"""

import requests
import time
from typing import List, Dict, Optional, Set, Tuple
from urllib.parse import urlparse, urljoin
import logging
from src.utils.validators import create_wildcard_patterns, normalize_host

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
        
        # Build patterns to cover http/https and host+www variants
        ok, patterns, err = create_wildcard_patterns(base_url)
        if not ok:
            raise ValueError(f"Invalid base URL: {err}")

        # Build CDX API base parameters
        base_params = {
            'output': 'json',
            'fl': 'timestamp,original,statuscode,mimetype',
            'filter': ['statuscode:200', 'mimetype:text/html'],
            'collapse': 'original',
            'sort': 'reverse',
            'limit': 10000
        }
        
        try:
            merged: Dict[str, Dict[str, str]] = {}
            for pattern in patterns:
                params = dict(base_params)
                params['url'] = pattern
                params['showResumeKey'] = 'true'

                # Page through results using resumeKey if present
                resume_key: Optional[str] = None
                page_count = 0
                while True:
                    if resume_key:
                        params['resumeKey'] = resume_key
                    else:
                        params.pop('resumeKey', None)
                    response = self._make_request(params)
                    records, resume_key = self._parse_cdx_json_with_resume(response)
                    page_count += 1
                    # Merge by normalized original (scheme+host normalized)
                    for rec in records:
                        norm_ok, norm_url, _ = normalize_host(rec['url'])
                        key = norm_url if norm_ok else rec['url']
                        if key not in merged or rec['timestamp'] > merged[key]['timestamp']:
                            merged[key] = rec
                    if not resume_key:
                        break
                    # Safety: avoid pathological loops
                    if page_count > 1000:
                        self.logger.warning("CDX paging aborted after 1000 pages (safety limit)")
                        break
            urls = list(merged.values())
            self.logger.info(f"Discovered {len(urls)} unique URLs across patterns")
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

        # Create wildcard pattern for CDX search (http* to include both schemes)
        path = parsed.path or '/'
        if not path.endswith('*'):
            if path.endswith('/'):
                path = path + '*'
            else:
                path = path + '/*'
        # Normalize host (strip default ports)
        host = parsed.netloc
        if host.endswith(':80'):
            host = host[:-3]
        if host.endswith(':443'):
            host = host[:-4]
        pattern = f"http*://{host}{path}"
        
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

    def _parse_cdx_json_with_resume(self, response: requests.Response) -> Tuple[List[Dict[str, str]], Optional[str]]:
        """
        Parse a CDX JSON page and detect resumeKey when showResumeKey=true.

        Returns (records, resume_key)
        """
        resume_key: Optional[str] = None
        try:
            data = response.json()
        except Exception:
            # Fallback: try to find resumeKey in text
            txt = response.text
            # crude search for resumeKey pattern
            if 'resumeKey' in txt:
                # attempt to extract after colon
                try:
                    resume_key = txt.split('resumeKey')[-1].split(':', 1)[-1].strip().strip('"\'{}[] ,\n\r')
                except Exception:
                    resume_key = None
            return [], resume_key

        # Normal records
        records = []
        if not data or len(data) < 2:
            return records, None
        headers = data[0]
        for row in data[1:]:
            # Detect resumeKey row variants
            if isinstance(row, dict) and 'resumeKey' in row:
                resume_key = row.get('resumeKey')
                continue
            if isinstance(row, str):
                # Some servers return a plain string row for resumeKey
                # Heuristic: if not the same length as headers and contains no spaces
                if len(row) > 0 and len(row.split()) == 1 and len(headers) != 1:
                    resume_key = row
                    continue
            if not isinstance(row, list) or len(row) < 4:
                continue
            timestamp, original_url, status_code, mime_type = row[:4]
            if not str(mime_type).startswith('text/html'):
                continue
            wayback_url = f"https://web.archive.org/web/{timestamp}/{original_url}"
            records.append({
                'url': original_url,
                'timestamp': timestamp,
                'wayback_url': wayback_url,
                'status_code': status_code,
                'mime_type': mime_type
            })
        return records, resume_key
    
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
