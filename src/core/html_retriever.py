"""
HTML Content Retrieval Module

This module handles downloading HTML content from Wayback Machine URLs
with respectful rate limiting and robust error handling.
"""

import requests
import time
from typing import Optional, Dict, Any, Callable
import logging
from urllib.parse import urlparse


class HTMLRetriever:
    """
    Handles downloading HTML content from Wayback Machine URLs with rate limiting.
    
    Implements the respectful scraping practices specified in the project requirements:
    - 1-2 second delays between requests
    - Proper error handling and retries
    - User-agent identification
    """
    
    def __init__(self, request_delay: float = 1.5, max_retries: int = 3, rate_limiter=None):
        """
        Initialize the HTML retriever.
        
        Args:
            request_delay: Delay in seconds between requests (1-2 seconds recommended)
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.logger = logging.getLogger(__name__)
        
        # Create a session with proper headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Archaic/2.0 (Archival Web Scraper; Educational/Archival Use)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def retrieve_page(self, 
                     wayback_url: str, 
                     original_url: str,
                     progress_callback: Optional[Callable[[str], None]] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve HTML content from a Wayback Machine URL.
        
        Args:
            wayback_url: The full Wayback Machine URL to download
            original_url: The original URL (for logging and metadata)
            progress_callback: Optional callback function to report progress
            
        Returns:
            Dictionary containing:
            - 'html': The raw HTML content
            - 'url': The original URL
            - 'wayback_url': The Wayback Machine URL used
            - 'size': Size of the content in bytes
            - 'encoding': Character encoding detected
            
            Returns None if the download fails after all retries
        """
        if progress_callback:
            progress_callback(f"Downloading: {original_url}")
        
        self.logger.info(f"Retrieving HTML for: {original_url}")
        self.logger.debug(f"Wayback URL: {wayback_url}")
        
        # Validate URL
        if not self._is_valid_wayback_url(wayback_url):
            self.logger.error(f"Invalid Wayback Machine URL: {wayback_url}")
            return None
        
        # Attempt download with retries
        for attempt in range(self.max_retries + 1):
            try:
                # Respectful delay before request
                if attempt > 0:
                    delay = self.request_delay * (2 ** attempt)  # Exponential backoff
                    self.logger.info(f"Retry {attempt} after {delay:.1f}s delay")
                    time.sleep(delay)
                else:
                    time.sleep(self.request_delay)
                
                # Respect global rate limiter if present
                if self.rate_limiter:
                    self.rate_limiter.acquire()
                # Make the request
                response = self.session.get(wayback_url, timeout=30)
                response.raise_for_status()
                
                # Validate content type
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type:
                    self.logger.warning(f"Non-HTML content type for {original_url}: {content_type}")
                    # Continue anyway as some archives may have incorrect headers
                
                # Get the HTML content
                html_content = response.text
                
                # Validate content
                if not html_content or len(html_content.strip()) < 100:
                    self.logger.warning(f"Retrieved content seems too short for {original_url}")
                    if attempt < self.max_retries:
                        continue  # Retry
                
                # Success - return the content
                result = {
                    'html': html_content,
                    'url': original_url,
                    'wayback_url': wayback_url,
                    'size': len(html_content.encode('utf-8')),
                    'encoding': response.encoding or 'utf-8'
                }
                
                self.logger.info(f"Successfully retrieved {result['size']} bytes for {original_url}")
                return result
                
            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout retrieving {original_url} (attempt {attempt + 1})")
                if attempt >= self.max_retries:
                    self.logger.error(f"Failed to retrieve {original_url} after {self.max_retries + 1} attempts: Timeout")
                    return None
                    
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else 'unknown'
                self.logger.warning(f"HTTP error {status_code} for {original_url} (attempt {attempt + 1})")
                
                # Don't retry on certain status codes
                if status_code in [404, 403, 410]:
                    self.logger.error(f"Permanent error {status_code} for {original_url}, not retrying")
                    return None
                # Backoff more aggressively on 429/5xx
                if isinstance(status_code, int) and (status_code == 429 or 500 <= status_code < 600):
                    time.sleep(self.request_delay * (2 ** (attempt + 1)))
                if attempt >= self.max_retries:
                    self.logger.error(f"Failed to retrieve {original_url} after {self.max_retries + 1} attempts: HTTP {status_code}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error for {original_url} (attempt {attempt + 1}): {e}")
                if attempt >= self.max_retries:
                    self.logger.error(f"Failed to retrieve {original_url} after {self.max_retries + 1} attempts: {e}")
                    return None
        
        return None
    
    def _is_valid_wayback_url(self, url: str) -> bool:
        """
        Validate that the URL is a proper Wayback Machine URL.
        
        Args:
            url: URL to validate
            
        Returns:
            True if the URL appears to be a valid Wayback Machine URL
        """
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ['http', 'https'] and
                'web.archive.org' in parsed.netloc and
                '/web/' in parsed.path
            )
        except Exception:
            return False
    
    def retrieve_multiple(self, 
                         url_list: list, 
                         progress_callback: Optional[Callable[[int, int, str], None]] = None) -> list:
        """
        Retrieve HTML content for multiple URLs.
        
        Args:
            url_list: List of dictionaries with 'wayback_url' and 'url' keys
            progress_callback: Optional callback function with signature (current, total, status)
            
        Returns:
            List of successful retrieval results
        """
        results = []
        total = len(url_list)
        
        self.logger.info(f"Starting batch retrieval of {total} URLs")
        
        for i, url_info in enumerate(url_list, 1):
            wayback_url = url_info.get('wayback_url')
            original_url = url_info.get('url', wayback_url)
            
            if progress_callback:
                progress_callback(i, total, f"Processing {original_url}")
            
            result = self.retrieve_page(wayback_url, original_url)
            if result:
                results.append(result)
            
            # Additional progress update after each retrieval
            if progress_callback:
                status = "✓ Success" if result else "✗ Failed"
                progress_callback(i, total, f"{status}: {original_url}")
        
        success_count = len(results)
        failure_count = total - success_count
        
        self.logger.info(f"Batch retrieval complete: {success_count} succeeded, {failure_count} failed")
        
        return results
    
    def test_connection(self) -> bool:
        """
        Test connection to the Wayback Machine.
        
        Returns:
            True if connection is successful, False otherwise
        """
        test_url = "https://web.archive.org/web/20230101000000/https://example.com"
        
        try:
            response = self.session.head(test_url, timeout=10)
            return response.status_code in [200, 404]  # 404 is also OK, means connection works
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current session.
        
        Returns:
            Dictionary with session statistics
        """
        return {
            'request_delay': self.request_delay,
            'max_retries': self.max_retries,
            'user_agent': self.session.headers.get('User-Agent')
        }
        # Optional global rate limiter
        self.rate_limiter = rate_limiter
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()
        self.logger.info("HTML retriever session closed")
