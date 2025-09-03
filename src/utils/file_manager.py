"""
File Management Utilities

This module provides utilities for managing output files with logical,
corresponding filenames as specified in the project requirements.
"""

import os
import re
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from urllib.parse import urlparse
import logging
from datetime import datetime


class FileManager:
    """
    Manages file organization and naming for archived content.
    
    Ensures generated HTML and PDF files are saved in organized output
    directories with logical, corresponding filenames for easy reference.
    """
    
    def __init__(self, base_output_dir: str = "output"):
        """
        Initialize the file manager.
        
        Args:
            base_output_dir: Base directory for all output files
        """
        self.base_output_dir = Path(base_output_dir)
        self.html_dir = self.base_output_dir / "html"
        self.pdf_dir = self.base_output_dir / "pdf"
        self.logger = logging.getLogger(__name__)
        
        # Create output directories
        self._create_directories()
    
    def _create_directories(self):
        """Create necessary output directories."""
        self.base_output_dir.mkdir(exist_ok=True)
        self.html_dir.mkdir(exist_ok=True)
        self.pdf_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"Output directories created at: {self.base_output_dir.absolute()}")
    
    def generate_filename(self, url: str, timestamp: str = None) -> str:
        """
        Generate a logical filename from a URL.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp from archive
            
        Returns:
            Clean filename suitable for file system
        """
        # Parse the URL
        parsed = urlparse(url)
        
        # Start with the domain
        domain = parsed.netloc.replace('www.', '')
        
        # Clean the path
        path = parsed.path.strip('/')
        if not path:
            path = "index"
        
        # Replace problematic characters
        filename_base = f"{domain}_{path}"
        filename_base = re.sub(r'[^\w\-_.]', '_', filename_base)
        filename_base = re.sub(r'_+', '_', filename_base)  # Collapse multiple underscores
        filename_base = filename_base.strip('_')
        
        # Add timestamp if available
        if timestamp:
            # Convert timestamp to readable format
            try:
                if len(timestamp) >= 14:
                    year = timestamp[:4]
                    month = timestamp[4:6]
                    day = timestamp[6:8]
                    hour = timestamp[8:10]
                    minute = timestamp[10:12]
                    second = timestamp[12:14]
                    readable_timestamp = f"{year}{month}{day}_{hour}{minute}{second}"
                    filename_base += f"_{readable_timestamp}"
            except (ValueError, IndexError):
                # If timestamp parsing fails, use it as-is
                filename_base += f"_{timestamp}"
        
        # Ensure filename isn't too long (max 200 chars for safety)
        if len(filename_base) > 200:
            filename_base = filename_base[:200]
        
        return filename_base
    
    def get_file_paths(self, url: str, timestamp: str = None) -> Tuple[str, str]:
        """
        Get the full file paths for HTML and PDF output.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp from archive
            
        Returns:
            Tuple of (html_path, pdf_path)
        """
        filename_base = self.generate_filename(url, timestamp)
        
        html_path = self.html_dir / f"{filename_base}.html"
        pdf_path = self.pdf_dir / f"{filename_base}.pdf"
        
        return str(html_path), str(pdf_path)
    
    def save_html(self, html_content: str, url: str, timestamp: str = None) -> Optional[str]:
        """
        Save HTML content to file.
        
        Args:
            html_content: Cleaned HTML content
            url: Original URL
            timestamp: Optional timestamp from archive
            
        Returns:
            Path to saved file, or None if save failed
        """
        try:
            html_path, _ = self.get_file_paths(url, timestamp)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(html_path), exist_ok=True)
            
            # Save the HTML content
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            file_size = os.path.getsize(html_path)
            self.logger.info(f"Saved HTML ({file_size} bytes): {os.path.basename(html_path)}")
            
            return html_path
            
        except Exception as e:
            self.logger.error(f"Failed to save HTML for {url}: {e}")
            return None
    
    def file_exists(self, url: str, timestamp: str = None, file_type: str = 'both') -> Dict[str, bool]:
        """
        Check if files already exist for a given URL.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp from archive
            file_type: Type to check ('html', 'pdf', or 'both')
            
        Returns:
            Dictionary with existence status for each file type
        """
        html_path, pdf_path = self.get_file_paths(url, timestamp)
        
        result = {}
        
        if file_type in ['html', 'both']:
            result['html'] = os.path.exists(html_path)
        
        if file_type in ['pdf', 'both']:
            result['pdf'] = os.path.exists(pdf_path)
        
        return result
    
    def get_output_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the output directory.
        
        Returns:
            Dictionary with file counts and sizes
        """
        stats = {
            'html_files': 0,
            'pdf_files': 0,
            'total_html_size': 0,
            'total_pdf_size': 0,
            'html_dir': str(self.html_dir),
            'pdf_dir': str(self.pdf_dir)
        }
        
        try:
            # Count HTML files
            if self.html_dir.exists():
                html_files = list(self.html_dir.glob('*.html'))
                stats['html_files'] = len(html_files)
                stats['total_html_size'] = sum(f.stat().st_size for f in html_files)
            
            # Count PDF files
            if self.pdf_dir.exists():
                pdf_files = list(self.pdf_dir.glob('*.pdf'))
                stats['pdf_files'] = len(pdf_files)
                stats['total_pdf_size'] = sum(f.stat().st_size for f in pdf_files)
                
        except Exception as e:
            self.logger.error(f"Error calculating output stats: {e}")
        
        return stats
    
    def create_session_directory(self, session_id: str) -> Tuple[str, str]:
        """
        Create session-specific directories for a scraping session.
        
        Args:
            session_id: Unique identifier for the session
            
        Returns:
            Tuple of (html_session_dir, pdf_session_dir)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_name = f"session_{session_id}_{timestamp}"
        
        html_session_dir = self.html_dir / session_name
        pdf_session_dir = self.pdf_dir / session_name
        
        html_session_dir.mkdir(exist_ok=True)
        pdf_session_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"Created session directories: {session_name}")
        
        return str(html_session_dir), str(pdf_session_dir)
    
    def generate_index_file(self, urls_processed: list, output_path: str = None) -> str:
        """
        Generate an index HTML file listing all processed URLs.
        
        Args:
            urls_processed: List of dictionaries with URL information
            output_path: Path for the index file (optional)
            
        Returns:
            Path to the generated index file
        """
        if output_path is None:
            output_path = self.base_output_dir / "index.html"
        
        try:
            html_content = self._build_index_html(urls_processed)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            self.logger.info(f"Generated index file: {output_path}")
            return str(output_path)
            
        except Exception as e:
            self.logger.error(f"Failed to generate index file: {e}")
            return ""
    
    def _build_index_html(self, urls_processed: list) -> str:
        """Build the HTML content for the index file."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Archaic - Archived Pages Index</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1 { color: #333; text-align: center; }
        .stats { background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .url-entry { border: 1px solid #ddd; margin: 10px 0; padding: 15px; border-radius: 5px; }
        .url-title { font-weight: bold; color: #2c5aa0; }
        .url-link { color: #666; font-size: 0.9em; margin: 5px 0; }
        .file-links { margin-top: 10px; }
        .file-links a { margin-right: 15px; text-decoration: none; color: #2c5aa0; }
        .file-links a:hover { text-decoration: underline; }
        .timestamp { color: #888; font-size: 0.8em; }
    </style>
</head>
<body>
    <h1>🗄️ Archaic - Archived Pages</h1>
    <div class="stats">
        <h2>Archive Statistics</h2>
        <p><strong>Total Pages:</strong> {total_pages}</p>
        <p><strong>Generated:</strong> {generation_time}</p>
    </div>
    <div class="url-list">
        <h2>Archived Pages</h2>
        {url_entries}
    </div>
</body>
</html>"""
        
        # Build URL entries
        url_entries = ""
        for i, url_info in enumerate(urls_processed, 1):
            original_url = url_info.get('url', 'Unknown URL')
            timestamp = url_info.get('timestamp', '')
            html_path = url_info.get('html_path', '')
            pdf_path = url_info.get('pdf_path', '')
            
            # Generate relative paths for links
            html_link = os.path.relpath(html_path, self.base_output_dir) if html_path else ""
            pdf_link = os.path.relpath(pdf_path, self.base_output_dir) if pdf_path else ""
            
            timestamp_display = ""
            if timestamp:
                try:
                    if len(timestamp) >= 14:
                        year = timestamp[:4]
                        month = timestamp[4:6]
                        day = timestamp[6:8]
                        hour = timestamp[8:10]
                        minute = timestamp[10:12]
                        timestamp_display = f"Archived: {year}-{month}-{day} {hour}:{minute}"
                except:
                    timestamp_display = f"Archived: {timestamp}"
            
            url_entries += f"""
        <div class="url-entry">
            <div class="url-title">{i}. {self._escape_html(original_url)}</div>
            <div class="timestamp">{timestamp_display}</div>
            <div class="file-links">
                {f'<a href="{html_link}">📄 View HTML</a>' if html_link else ''}
                {f'<a href="{pdf_link}">📋 View PDF</a>' if pdf_link else ''}
            </div>
        </div>"""
        
        return html.format(
            total_pages=len(urls_processed),
            generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            url_entries=url_entries
        )
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML characters."""
        if not isinstance(text, str):
            text = str(text)
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))
    
    def cleanup_empty_directories(self):
        """Remove empty directories in the output structure."""
        try:
            for directory in [self.html_dir, self.pdf_dir]:
                for subdir in directory.glob('**/'):
                    if subdir.is_dir() and not any(subdir.iterdir()):
                        subdir.rmdir()
                        self.logger.debug(f"Removed empty directory: {subdir}")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")