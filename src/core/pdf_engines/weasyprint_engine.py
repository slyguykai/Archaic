"""
WeasyPrint PDF Engine

Primary PDF engine for Archaic using WeasyPrint to render cleaned HTML to PDF.

Resources are constrained to local filesystem by default via a custom
url_fetcher that denies http(s) requests to ensure offline rendering.
"""

import logging
import os
from typing import Optional, Dict, Any

try:
    from weasyprint import HTML
except Exception:  # pragma: no cover - handled at runtime
    HTML = None


class WeasyPrintEngine:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def _local_only_fetcher(self, allowed_base: Optional[str] = None):
        """
        Return a url_fetcher for WeasyPrint that only allows local file paths.
        Optionally restrict under an allowed_base directory.
        """

        def fetch(url):
            # Deny any remote fetches
            if url.startswith('http://') or url.startswith('https://'):
                raise RuntimeError(f"Remote fetch blocked: {url}")
            if url.startswith('file://'):
                path = url[7:]
            else:
                # Treat bare paths as local
                path = url
            # Normalize and enforce base if provided
            abs_path = os.path.abspath(path)
            if allowed_base:
                base = os.path.abspath(allowed_base)
                if not abs_path.startswith(base):
                    raise RuntimeError(f"Access outside allowed base blocked: {url}")
            try:
                with open(abs_path, 'rb') as f:
                    data = f.read()
                return {
                    'string': data,
                    'mime_type': None,  # Let WeasyPrint infer
                    'encoding': 'binary'
                }
            except Exception as e:
                raise RuntimeError(f"Failed to read local resource: {url} ({e})")

        return fetch

    def available(self) -> bool:
        """Return True if WeasyPrint is importable."""
        return HTML is not None

    def generate(self, html_content: str, output_path: str, base_url: Optional[str] = None) -> bool:
        """
        Generate a PDF using WeasyPrint.

        Args:
            html_content: Cleaned HTML string
            output_path: Target PDF path
            base_url: Base directory for resolving relative resources
        """
        if HTML is None:
            self.logger.error("WeasyPrint is not installed. Please install 'weasyprint'.")
            return False

        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            # Constrain fetcher to local only (and within base_url when provided)
            url_fetcher = self._local_only_fetcher(allowed_base=base_url)
            html = HTML(string=html_content, base_url=base_url, url_fetcher=url_fetcher)
            html.write_pdf(output_path)

            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            self.logger.error(f"WeasyPrint generation failed: {e}")
            return False

