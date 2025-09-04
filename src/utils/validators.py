"""
URL Validation Utilities

This module provides URL validation and normalization functions
for the Archaic web scraper.
"""

import re
from urllib.parse import urlparse, urlunparse
from typing import Tuple, Optional
import logging


class URLValidator:
    """
    Validates and normalizes URLs for the archival process.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Patterns for common URL formats
        self.domain_pattern = re.compile(
            r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        )
    
    def validate_and_normalize(self, url: str) -> Tuple[bool, str, str]:
        """
        Validate and normalize a URL for archival.
        
        Args:
            url: The URL to validate and normalize
            
        Returns:
            Tuple of (is_valid, normalized_url, error_message)
        """
        if not url or not isinstance(url, str):
            return False, "", "URL cannot be empty"
        
        url = url.strip()
        
        try:
            # Parse the URL first to check if it already has a scheme
            parsed_check = urlparse(url)
            
            # If it already has a scheme, validate it directly
            if parsed_check.scheme:
                # Validate scheme
                if parsed_check.scheme not in ['http', 'https']:
                    return False, "", "URL must use HTTP or HTTPS protocol"
                parsed = parsed_check
            else:
                # Add protocol if missing
                url = 'https://' + url
                parsed = urlparse(url)
            
            # Validate domain
            if not parsed.netloc:
                return False, "", "URL must have a valid domain"
            
            # Extract domain for validation
            domain = parsed.netloc.lower()
            
            # Remove port if present for domain validation
            if ':' in domain:
                domain = domain.split(':')[0]
            
            # Validate domain format
            if not self.domain_pattern.match(domain):
                return False, "", "Invalid domain format"
            
            # Normalize the URL
            normalized_url = self._normalize_url(parsed)
            
            return True, normalized_url, ""
            
        except Exception as e:
            return False, "", f"URL validation error: {str(e)}"
    
    def _normalize_url(self, parsed_url) -> str:
        """
        Normalize a parsed URL.
        
        Args:
            parsed_url: ParseResult object from urlparse
            
        Returns:
            Normalized URL string
        """
        # Normalize components
        scheme = parsed_url.scheme.lower()
        netloc = parsed_url.netloc.lower()
        path = parsed_url.path
        
        # Ensure path ends with / for directory-like URLs
        if not path:
            path = '/'
        elif not path.endswith('/') and '.' not in path.split('/')[-1]:
            # If the last part doesn't contain a dot (likely not a file), add trailing slash
            path += '/'
        
        # Remove fragment (not needed for archival)
        fragment = ''
        
        # Keep query parameters as they might be important
        query = parsed_url.query
        params = parsed_url.params
        
        # Reconstruct the URL
        normalized = urlunparse((scheme, netloc, path, params, query, fragment))
        
        return normalized
    
    def extract_domain(self, url: str) -> Optional[str]:
        """
        Extract the domain from a URL.
        
        Args:
            url: The URL to extract domain from
            
        Returns:
            Domain string, or None if extraction fails
        """
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except Exception:
            return None
    
    def is_same_domain(self, url1: str, url2: str) -> bool:
        """
        Check if two URLs are from the same domain.
        
        Args:
            url1: First URL
            url2: Second URL
            
        Returns:
            True if same domain, False otherwise
        """
        domain1 = self.extract_domain(url1)
        domain2 = self.extract_domain(url2)
        
        return domain1 is not None and domain1 == domain2
    
    def create_wildcard_pattern(self, base_url: str) -> Optional[str]:
        """
        Create a wildcard pattern for CDX API from a base URL.
        
        Args:
            base_url: Base URL to create pattern from
            
        Returns:
            Wildcard pattern string, or None if creation fails
        """
        is_valid, normalized_url, error = self.validate_and_normalize(base_url)
        
        if not is_valid:
            self.logger.error(f"Cannot create pattern from invalid URL: {error}")
            return None
        
        # For CDX API, we want to match all URLs under the path
        if not normalized_url.endswith('*'):
            if normalized_url.endswith('/'):
                pattern = normalized_url + '*'
            else:
                pattern = normalized_url + '/*'
        else:
            pattern = normalized_url
        
        return pattern
    
    def get_url_components(self, url: str) -> dict:
        """
        Get detailed components of a URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            Dictionary with URL components
        """
        try:
            parsed = urlparse(url)
            
            return {
                'scheme': parsed.scheme,
                'domain': parsed.netloc,
                'path': parsed.path,
                'query': parsed.query,
                'fragment': parsed.fragment,
                'port': parsed.port,
                'username': parsed.username,
                'password': parsed.password
            }
        except Exception as e:
            self.logger.error(f"Error parsing URL {url}: {e}")
            return {}


_singleton_validator: Optional[URLValidator] = None


def get_validator() -> URLValidator:
    """Return a singleton URLValidator instance."""
    global _singleton_validator
    if _singleton_validator is None:
        _singleton_validator = URLValidator()
    return _singleton_validator


def validate_url(url: str) -> Tuple[bool, str, str]:
    """
    Convenience wrapper used by tests/GUI.
    Returns (is_valid, normalized_url, error_message).
    """
    return get_validator().validate_and_normalize(url)


def normalize_host(url: str) -> Tuple[bool, str, str]:
    """
    Normalize scheme/host for deduplication:
    - Lowercase scheme/host, strip leading 'www.'
    - Remove default ports 80/443
    """
    try:
        ok, normalized, err = validate_url(url)
        if not ok:
            return ok, "", err
        parsed = urlparse(normalized)
        host = parsed.netloc.lower()
        # Remove default ports
        if host.endswith(":80"):
            host = host[:-3]
        if host.endswith(":443"):
            host = host[:-4]
        # Strip leading www.
        if host.startswith("www."):
            host = host[4:]
        # Rebuild URL
        rebuilt = urlunparse((parsed.scheme.lower(), host, parsed.path, parsed.params, parsed.query, ""))
        return True, rebuilt, ""
    except Exception as e:
        return False, "", str(e)


def create_wildcard_patterns(base_url: str) -> Tuple[bool, list, str]:
    """
    Build CDX wildcard patterns covering HTTP/HTTPS and host+www variants.
    Returns (ok, patterns, error).
    Examples:
      http*://example.com/articles/* and http*://www.example.com/articles/*
    """
    ok, normalized, err = validate_url(base_url)
    if not ok:
        return False, [], err

    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    if host.endswith(":80"):
        host = host[:-3]
    if host.endswith(":443"):
        host = host[:-4]
    bare_host = host[4:] if host.startswith("www.") else host

    # Ensure trailing slash for directory-like paths
    path = parsed.path
    if not path:
        path = "/"
    elif not path.endswith('/') and '.' not in path.split('/')[-1]:
        path += '/'

    # Build patterns with http* scheme umbrella
    patterns = [
        f"http*://{bare_host}{path}*",
        f"http*://www.{bare_host}{path}*",
    ]
    # De-duplicate if base was already www
    patterns = list(dict.fromkeys(patterns))
    return True, patterns, ""

# Global validator instance
_validator_instance: Optional[URLValidator] = None


def get_validator() -> URLValidator:
    """
    Get the global URL validator instance.
    
    Returns:
        URLValidator instance
    """
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = URLValidator()
    return _validator_instance


def validate_url(url: str) -> Tuple[bool, str, str]:
    """
    Validate and normalize a URL.
    
    Args:
        url: URL to validate
        
    Returns:
        Tuple of (is_valid, normalized_url, error_message)
    """
    return get_validator().validate_and_normalize(url)
