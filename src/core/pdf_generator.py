"""
PDF Generation Module

This module handles converting cleaned HTML content to PDF format using ReportLab.
ReportLab is used instead of wkhtmltopdf due to installation difficulties on macOS,
as it is a pure Python library that doesn't require external system dependencies.
"""

import logging
import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin
import re
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.colors import black, blue, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from bs4 import BeautifulSoup
import requests


class PDFGenerator:
    """
    Generates PDF files from cleaned HTML content using ReportLab.
    
    This generator attempts to preserve the structure and basic styling
    of the original HTML while creating a readable PDF document.
    """
    
    def __init__(self, page_size=A4, margins=(72, 72, 72, 72)):
        """
        Initialize the PDF generator.
        
        Args:
            page_size: Page size tuple (default: A4)
            margins: Margins tuple (left, right, top, bottom) in points
        """
        self.page_size = page_size
        self.margins = margins
        self.logger = logging.getLogger(__name__)
        
        # Initialize styles
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
        # Session for downloading images
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Archaic/2.0 (PDF Generator)'
        })
    
    def _setup_custom_styles(self):
        """Set up custom paragraph styles for different HTML elements."""
        # Custom title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=TA_CENTER,
            textColor=black
        ))
        
        # Custom heading styles
        self.styles.add(ParagraphStyle(
            name='CustomH2',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=20,
            spaceAfter=12,
            textColor=black
        ))
        
        self.styles.add(ParagraphStyle(
            name='CustomH3',
            parent=self.styles['Heading3'],
            fontSize=12,
            spaceBefore=16,
            spaceAfter=8,
            textColor=black
        ))
        
        # Custom body text
        self.styles.add(ParagraphStyle(
            name='CustomBody',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=12,
            alignment=TA_JUSTIFY,
            textColor=black
        ))
        
        # Custom blockquote
        self.styles.add(ParagraphStyle(
            name='CustomBlockquote',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=36,
            rightIndent=36,
            spaceAfter=12,
            textColor=grey,
            borderColor=grey,
            borderWidth=1,
            borderPadding=12
        ))
    
    def generate_pdf(self, 
                    html_content: str, 
                    output_path: str, 
                    title: str = None,
                    original_url: str = None) -> bool:
        """
        Generate a PDF from cleaned HTML content.
        
        Args:
            html_content: Cleaned HTML content
            output_path: Path where the PDF should be saved
            title: Title for the PDF document
            original_url: Original URL of the page (for metadata)
            
        Returns:
            True if PDF generation succeeded, False otherwise
        """
        try:
            self.logger.info(f"Generating PDF: {os.path.basename(output_path)}")
            
            # Ensure output directory exists
            output_dir = os.path.dirname(os.path.abspath(output_path))
            os.makedirs(output_dir, exist_ok=True)
            
            # Parse HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title if not provided
            if not title:
                title_tag = soup.find('title')
                title = title_tag.get_text().strip() if title_tag else "Archived Page"
            
            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=self.page_size,
                leftMargin=self.margins[0],
                rightMargin=self.margins[1],
                topMargin=self.margins[2],
                bottomMargin=self.margins[3]
            )
            
            # Build content
            story = []
            
            # Add header information
            self._add_header(story, title, original_url)
            
            # Convert HTML to PDF content
            self._convert_html_elements(soup, story, original_url)
            
            # Build the PDF
            try:
                doc.build(story)
            except Exception as pdf_error:
                self.logger.error(f"PDF build error: {pdf_error}")
                import traceback
                self.logger.error(f"PDF build traceback: {traceback.format_exc()}")
                raise
            
            # Verify file was created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                self.logger.info(f"Successfully generated PDF: {output_path}")
                return True
            else:
                self.logger.error(f"PDF file was not created or is empty: {output_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to generate PDF {output_path}: {e}")
            import traceback
            self.logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    
    def _add_header(self, story: list, title: str, original_url: str = None):
        """Add header information to the PDF."""
        # Add title
        story.append(Paragraph(title, self.styles['CustomTitle']))
        story.append(Spacer(1, 12))
        
        # Add original URL if available
        if original_url:
            url_text = f"<b>Original URL:</b> {original_url}"
            story.append(Paragraph(url_text, self.styles['Normal']))
            story.append(Spacer(1, 6))
        
        # Add archive information
        archive_text = "<b>Archived by:</b> Archaic Web Scraper"
        story.append(Paragraph(archive_text, self.styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Add horizontal line
        story.append(HRFlowable(width="100%", thickness=1, color=grey))
        story.append(Spacer(1, 20))
    
    def _convert_html_elements(self, soup: BeautifulSoup, story: list, base_url: str = None):
        """Convert HTML elements to PDF flowables."""
        # Find the main content area (prefer body, fall back to entire document)
        content_root = soup.find('body') or soup
        
        # Process child elements
        for element in content_root.children:
            if hasattr(element, 'name'):  # Skip text nodes
                self._process_element(element, story, base_url)
    
    def _process_element(self, element, story: list, base_url: str = None):
        """Process individual HTML elements."""
        if not hasattr(element, 'name') or not element.name:
            return
        
        # Safely get the tag name
        try:
            tag_name = element.name.lower()
        except AttributeError:
            # Skip if element.name is None or doesn't have lower() method
            return
            
        if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self._add_heading(element, story, tag_name)
        elif tag_name == 'p':
            self._add_paragraph(element, story)
        elif tag_name in ['div', 'section', 'article']:
            self._process_container(element, story, base_url)
        elif tag_name in ['ul', 'ol']:
            self._add_list(element, story)
        elif tag_name == 'blockquote':
            self._add_blockquote(element, story)
        elif tag_name == 'img':
            self._add_image(element, story, base_url)
        elif tag_name == 'hr':
            story.append(HRFlowable(width="100%", thickness=1, color=grey))
            story.append(Spacer(1, 12))
        elif tag_name in ['br']:
            story.append(Spacer(1, 6))
        else:
            # For other elements, process their children
            if hasattr(element, 'children'):
                for child in element.children:
                    if hasattr(child, 'name') and child.name:
                        self._process_element(child, story, base_url)
    
    def _add_heading(self, element, story: list, tag_name: str):
        """Add a heading to the story."""
        text = self._extract_text(element)
        if not text.strip():
            return
        
        if tag_name == 'h1':
            style = self.styles['CustomTitle']
        elif tag_name == 'h2':
            style = self.styles['CustomH2']
        elif tag_name == 'h3':
            style = self.styles['CustomH3']
        else:
            style = self.styles['Heading4']
        
        story.append(Paragraph(self._escape_html(text), style))
        story.append(Spacer(1, 6))
    
    def _add_paragraph(self, element, story: list):
        """Add a paragraph to the story."""
        text = self._extract_text_with_formatting(element)
        if not text.strip():
            return
        
        story.append(Paragraph(text, self.styles['CustomBody']))
        story.append(Spacer(1, 6))
    
    def _add_blockquote(self, element, story: list):
        """Add a blockquote to the story."""
        text = self._extract_text_with_formatting(element)
        if not text.strip():
            return
        
        story.append(Paragraph(text, self.styles['CustomBlockquote']))
        story.append(Spacer(1, 12))
    
    def _add_list(self, element, story: list):
        """Add a list to the story."""
        is_ordered = element.name == 'ol'
        items = element.find_all('li', recursive=False)
        
        for i, item in enumerate(items, 1):
            text = self._extract_text_with_formatting(item)
            if not text.strip():
                continue
            
            if is_ordered:
                bullet = f"{i}. "
            else:
                bullet = "• "
            
            list_text = f"{bullet}{text}"
            list_style = ParagraphStyle(
                name='ListItem',
                parent=self.styles['Normal'],
                fontSize=10,
                leftIndent=24,
                spaceAfter=6
            )
            
            story.append(Paragraph(list_text, list_style))
        
        story.append(Spacer(1, 12))
    
    def _process_container(self, element, story: list, base_url: str = None):
        """Process container elements like div, section, article."""
        for child in element.children:
            if hasattr(child, 'name'):
                self._process_element(child, story, base_url)
    
    def _add_image(self, element, story: list, base_url: str = None):
        """Add an image to the story (placeholder for now)."""
        # For now, just add a text placeholder
        # In a full implementation, you'd download and embed the image
        alt_text = element.get('alt', 'Image')
        src = element.get('src', '')
        
        if src:
            img_text = f"[Image: {alt_text}] (Source: {src})"
        else:
            img_text = f"[Image: {alt_text}]"
        
        img_style = ParagraphStyle(
            name='ImagePlaceholder',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=grey,
            alignment=TA_CENTER,
            spaceAfter=12
        )
        
        story.append(Paragraph(self._escape_html(img_text), img_style))
    
    def _extract_text(self, element) -> str:
        """Extract plain text from an element."""
        return element.get_text(strip=True)
    
    def _extract_text_with_formatting(self, element) -> str:
        """Extract text with basic formatting preserved."""
        # This is a simplified version - a full implementation would handle more formatting
        text = ""
        
        for content in element.children:
            if hasattr(content, 'name') and content.name:
                try:
                    tag = content.name.lower()
                    inner_text = content.get_text(strip=True)
                    
                    if tag in ['b', 'strong']:
                        text += f"<b>{self._escape_html(inner_text)}</b>"
                    elif tag in ['i', 'em']:
                        text += f"<i>{self._escape_html(inner_text)}</i>"
                    elif tag == 'a':
                        href = content.get('href', '')
                        if href:
                            text += f'<link href="{href}">{self._escape_html(inner_text)}</link>'
                        else:
                            text += self._escape_html(inner_text)
                    else:
                        text += self._escape_html(inner_text)
                except AttributeError:
                    # Skip if content.name is None or doesn't support lower()
                    continue
            else:
                # Text node
                text += self._escape_html(str(content))
        
        return text.strip()
    
    def _escape_html(self, text: str) -> str:
        """Escape HTML characters for ReportLab."""
        if not isinstance(text, str):
            text = str(text)
        
        # Basic HTML escaping
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        
        return text
    
    def close(self):
        """Close the HTTP session."""
        self.session.close()
    
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