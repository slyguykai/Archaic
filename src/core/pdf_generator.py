"""
PDF Generation Module (WeasyPrint-backed)

Converts cleaned HTML content to PDF format using WeasyPrint as the primary
engine. ReportLab implementation has been deprecated in favor of higher-fidelity
rendering and simpler dependency story for HTML/CSS support.
"""

import logging
import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

from .pdf_engines.weasyprint_engine import WeasyPrintEngine


class PDFGenerator:
    """Generates PDF files from cleaned HTML content using WeasyPrint."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.engine = WeasyPrintEngine()

    def generate_pdf(self,
                     html_content: str,
                     output_path: str,
                     title: str = None,
                     original_url: str = None,
                     base_url: Optional[str] = None) -> bool:
        """
        Generate a PDF from cleaned HTML using WeasyPrint.

        Args:
            html_content: Cleaned HTML content
            output_path: Target PDF path
            title: Unused placeholder for API compatibility
            original_url: Unused placeholder for API compatibility
            base_url: Base directory for resolving relative resources (assets)
        """
        try:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            if self.engine.available():
                base_dir = base_url or os.path.dirname(os.path.abspath(output_path))
                success = self.engine.generate(html_content=html_content,
                                               output_path=output_path,
                                               base_url=base_dir)
                if success:
                    self.logger.info(f"Successfully generated PDF: {output_path}")
                    return True
                self.logger.error(f"WeasyPrint failed; attempting ReportLab fallback")

            # Fallback: minimal ReportLab rendering if available
            try:
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.pagesizes import A4
            except Exception:
                self.logger.error("WeasyPrint not available and ReportLab fallback missing.")
                return False

            styles = getSampleStyleSheet()
            doc = SimpleDocTemplate(output_path, pagesize=A4)
            story = []
            soup = BeautifulSoup(html_content, 'html.parser')
            t = soup.find('title')
            text_title = (t.get_text().strip() if t else (title or "Archived Page"))
            story.append(Paragraph(text_title, styles['Title']))
            story.append(Spacer(1, 12))
            # Add paragraphs for each <p>
            for p in soup.find_all('p'):
                txt = p.get_text().strip()
                if txt:
                    story.append(Paragraph(txt, styles['Normal']))
                    story.append(Spacer(1, 6))
            doc.build(story)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
        except Exception as e:
            self.logger.error(f"Failed to generate PDF {output_path}: {e}")
            return False

    def close(self):
        """No-op for WeasyPrint engine."""
        return None

    def get_metadata(self, html_content: str) -> Dict[str, Any]:
        """
        Extract metadata from HTML content.
        
        Args:
            html_content: HTML content to analyze
            
        Returns:
            Dictionary with metadata information
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        metadata = {
            'title': '',
            'description': '',
            'keywords': '',
            'word_count': 0,
            'image_count': 0,
            'link_count': 0
        }
        
        # Extract title
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.get_text().strip()
        
        # Extract meta description
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag:
            metadata['description'] = desc_tag.get('content', '').strip()
        
        # Extract meta keywords
        keywords_tag = soup.find('meta', attrs={'name': 'keywords'})
        if keywords_tag:
            metadata['keywords'] = keywords_tag.get('content', '').strip()
        
        # Count elements
        body = soup.find('body') or soup
        text = body.get_text()
        metadata['word_count'] = len(text.split())
        metadata['image_count'] = len(soup.find_all('img'))
        metadata['link_count'] = len(soup.find_all('a'))
        
        return metadata
