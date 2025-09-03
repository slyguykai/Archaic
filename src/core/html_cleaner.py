"""
HTML Content Cleaning Module

This module handles cleaning HTML content retrieved from the Wayback Machine
by removing the injected archive interface elements while preserving the
original page content and styling.
"""

from bs4 import BeautifulSoup, Comment
import re
import logging
from typing import Optional, List, Set
import urllib.parse as urlparse


class HTMLCleaner:
    """
    Cleans HTML content by removing Wayback Machine interface elements.
    
    The Wayback Machine injects various UI elements when serving archived pages:
    - Archive header/toolbar
    - JavaScript for archive functionality  
    - Modified URLs pointing to archived resources
    - Archive-specific CSS and scripts
    
    This cleaner removes these elements while preserving the original content.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Wayback Machine specific elements to remove
        self.wayback_selectors = [
            # Main archive toolbar/header
            '#wm-ipp-base',
            '#wm-ipp',
            '.wb-overlay',
            '#donato',
            
            # Archive notification banners
            '.wb-autocomplete-suggestions',
            '#wm-capresources',
            '#wm-expand',
            
            # Various wayback UI elements
            '[id^="wm-"]',
            '[class^="wb-"]',
            '[class*="wayback"]',
            '[id*="wayback"]'
        ]
        
        # Script patterns that indicate Wayback Machine injection
        self.wayback_script_patterns = [
            r'web\.archive\.org',
            r'wayback',
            r'wbhack',
            r'_wb_wombat',
            r'archive_analytics',
            r'__wb_'
        ]
        
        # URL patterns to clean/remove
        self.wayback_url_patterns = [
            r'https?://web\.archive\.org/web/\d+[a-z_]*/',
            r'https?://wayback\.archive-it\.org/\d+/\d+/'
        ]
    
    def clean_html(self, html_content: str, original_url: str) -> Optional[str]:
        """
        Clean HTML content by removing Wayback Machine interface elements.
        
        Args:
            html_content: Raw HTML content from Wayback Machine
            original_url: The original URL of the page (for URL restoration)
            
        Returns:
            Cleaned HTML content, or None if cleaning fails
        """
        try:
            self.logger.info(f"Cleaning HTML content for: {original_url}")
            
            # Parse the HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Remove Wayback Machine UI elements
            self._remove_wayback_elements(soup)
            
            # Clean up scripts
            self._clean_scripts(soup)
            
            # Clean up stylesheets
            self._clean_stylesheets(soup)
            
            # Restore original URLs where possible
            self._restore_urls(soup, original_url)
            
            # Remove archive-injected comments
            self._remove_wayback_comments(soup)
            
            # Clean up any remaining wayback artifacts
            self._final_cleanup(soup)
            
            # Get the cleaned HTML
            cleaned_html = str(soup)
            
            # Final text-based cleaning
            cleaned_html = self._post_process_html(cleaned_html)
            
            self.logger.info(f"Successfully cleaned HTML for: {original_url}")
            self.logger.debug(f"Original size: {len(html_content)}, Cleaned size: {len(cleaned_html)}")
            
            return cleaned_html
            
        except Exception as e:
            self.logger.error(f"Failed to clean HTML for {original_url}: {e}")
            return None
    
    def _remove_wayback_elements(self, soup: BeautifulSoup) -> None:
        """Remove Wayback Machine UI elements using CSS selectors."""
        removed_count = 0
        
        for selector in self.wayback_selectors:
            elements = soup.select(selector)
            for element in elements:
                element.decompose()
                removed_count += 1
        
        # Also remove elements with wayback-related attributes
        for element in soup.find_all(attrs={'class': re.compile(r'wayback|wb-|wm-', re.I)}):
            element.decompose()
            removed_count += 1
            
        for element in soup.find_all(attrs={'id': re.compile(r'wayback|wb-|wm-', re.I)}):
            element.decompose()
            removed_count += 1
        
        if removed_count > 0:
            self.logger.debug(f"Removed {removed_count} Wayback UI elements")
    
    def _clean_scripts(self, soup: BeautifulSoup) -> None:
        """Remove Wayback Machine injected scripts."""
        scripts_to_remove = []
        
        for script in soup.find_all('script'):
            script_content = script.get_text() if script.string else ''
            script_src = script.get('src', '')
            
            # Check if this is a Wayback-injected script
            is_wayback_script = False
            
            for pattern in self.wayback_script_patterns:
                if re.search(pattern, script_content, re.I) or re.search(pattern, script_src, re.I):
                    is_wayback_script = True
                    break
            
            if is_wayback_script:
                scripts_to_remove.append(script)
        
        for script in scripts_to_remove:
            script.decompose()
        
        if scripts_to_remove:
            self.logger.debug(f"Removed {len(scripts_to_remove)} Wayback scripts")
    
    def _clean_stylesheets(self, soup: BeautifulSoup) -> None:
        """Remove Wayback Machine injected stylesheets."""
        styles_to_remove = []
        
        # Remove link elements pointing to Wayback resources
        for link in soup.find_all('link', rel='stylesheet'):
            href = link.get('href', '')
            if any(re.search(pattern, href, re.I) for pattern in self.wayback_url_patterns):
                styles_to_remove.append(link)
        
        # Remove style elements with Wayback content
        for style in soup.find_all('style'):
            style_content = style.get_text() if style.string else ''
            if any(re.search(pattern, style_content, re.I) for pattern in self.wayback_script_patterns):
                styles_to_remove.append(style)
        
        for style in styles_to_remove:
            style.decompose()
        
        if styles_to_remove:
            self.logger.debug(f"Removed {len(styles_to_remove)} Wayback stylesheets")
    
    def _restore_urls(self, soup: BeautifulSoup, original_url: str) -> None:
        """Attempt to restore original URLs from Wayback Machine URLs."""
        restored_count = 0
        
        # Get the base domain from original URL
        parsed_original = urlparse.urlparse(original_url)
        base_domain = f"{parsed_original.scheme}://{parsed_original.netloc}"
        
        # Restore URLs in common attributes
        url_attributes = ['href', 'src', 'action', 'data-src']
        
        for attr in url_attributes:
            for element in soup.find_all(attrs={attr: True}):
                original_attr = element[attr]
                cleaned_url = self._clean_archived_url(original_attr, base_domain)
                
                if cleaned_url != original_attr:
                    element[attr] = cleaned_url
                    restored_count += 1
        
        if restored_count > 0:
            self.logger.debug(f"Restored {restored_count} URLs")
    
    def _clean_archived_url(self, url: str, base_domain: str) -> str:
        """
        Clean a single URL by removing Wayback Machine prefixes.
        
        Args:
            url: The URL to clean
            base_domain: Base domain of the original site
            
        Returns:
            Cleaned URL
        """
        if not url or not isinstance(url, str):
            return url
        
        # Remove Wayback Machine URL prefixes
        for pattern in self.wayback_url_patterns:
            url = re.sub(pattern, '', url)
        
        # Handle relative URLs
        if url.startswith('/') and not url.startswith('//'):
            url = base_domain + url
        elif url.startswith('../') or not url.startswith(('http://', 'https://', '//', 'mailto:', 'javascript:', '#')):
            # Handle relative paths - attempt to make them absolute
            if not url.startswith('#') and not url.startswith('javascript:'):
                url = base_domain + '/' + url.lstrip('./')
        
        return url
    
    def _remove_wayback_comments(self, soup: BeautifulSoup) -> None:
        """Remove HTML comments injected by Wayback Machine."""
        comments_removed = 0
        
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment_text = str(comment).lower()
            if any(keyword in comment_text for keyword in ['wayback', 'archive.org', 'web.archive', 'begin wayback']):
                comment.extract()
                comments_removed += 1
        
        if comments_removed > 0:
            self.logger.debug(f"Removed {comments_removed} Wayback comments")
    
    def _final_cleanup(self, soup: BeautifulSoup) -> None:
        """Perform final cleanup of any remaining Wayback artifacts."""
        # Remove any remaining elements with wayback data attributes
        for element in soup.find_all():
            if element.attrs:
                attrs_to_remove = []
                for attr in element.attrs.keys():
                    if attr.lower().startswith(('data-wb', 'data-wayback')):
                        attrs_to_remove.append(attr)
                
                for attr in attrs_to_remove:
                    del element.attrs[attr]
        
        # Clean up any remaining wayback classes
        for element in soup.find_all(class_=True):
            classes = element.get('class', [])
            clean_classes = [cls for cls in classes if not re.match(r'wb-|wm-|wayback', cls, re.I)]
            if clean_classes != classes:
                element['class'] = clean_classes if clean_classes else None
                if not clean_classes:
                    del element['class']
    
    def _post_process_html(self, html: str) -> str:
        """
        Perform final text-based cleaning on the HTML string.
        
        Args:
            html: HTML content as string
            
        Returns:
            Post-processed HTML content
        """
        # Remove any remaining Wayback Machine URLs in the HTML text
        for pattern in self.wayback_url_patterns:
            html = re.sub(pattern, '', html)
        
        # Remove empty script and style tags that might be left behind
        html = re.sub(r'<script[^>]*>\s*</script>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<style[^>]*>\s*</style>', '', html, flags=re.IGNORECASE)
        
        # Clean up excessive whitespace
        html = re.sub(r'\n\s*\n\s*\n', '\n\n', html)
        
        return html
    
    def validate_cleaned_content(self, original_html: str, cleaned_html: str) -> dict:
        """
        Validate that the cleaning process preserved important content.
        
        Args:
            original_html: Original HTML before cleaning
            cleaned_html: HTML after cleaning
            
        Returns:
            Dictionary with validation results
        """
        try:
            original_soup = BeautifulSoup(original_html, 'lxml')
            cleaned_soup = BeautifulSoup(cleaned_html, 'lxml')
            
            # Count important elements
            original_counts = self._count_elements(original_soup)
            cleaned_counts = self._count_elements(cleaned_soup)
            
            # Calculate preservation ratios
            preservation_ratios = {}
            for element_type in original_counts:
                if original_counts[element_type] > 0:
                    ratio = cleaned_counts.get(element_type, 0) / original_counts[element_type]
                    preservation_ratios[element_type] = ratio
                else:
                    preservation_ratios[element_type] = 1.0
            
            return {
                'original_size': len(original_html),
                'cleaned_size': len(cleaned_html),
                'size_reduction': 1 - (len(cleaned_html) / len(original_html)),
                'element_counts': {
                    'original': original_counts,
                    'cleaned': cleaned_counts
                },
                'preservation_ratios': preservation_ratios
            }
            
        except Exception as e:
            self.logger.error(f"Validation failed: {e}")
            return {}
    
    def _count_elements(self, soup: BeautifulSoup) -> dict:
        """Count important HTML elements in the soup."""
        return {
            'paragraphs': len(soup.find_all('p')),
            'headings': len(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])),
            'images': len(soup.find_all('img')),
            'links': len(soup.find_all('a')),
            'divs': len(soup.find_all('div')),
            'scripts': len(soup.find_all('script')),
            'styles': len(soup.find_all('style'))
        }