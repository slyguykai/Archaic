"""
Asset collection, download, and rewrite utilities.

This module discovers external assets in cleaned HTML, downloads them from the
Wayback Machine for the same capture timestamp, and rewrites the HTML to point
to local files. It supports a "single-file HTML" mode that embeds assets as
data URIs for portability (optional).
"""

from __future__ import annotations

import os
import re
import base64
import mimetypes
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


WAYBACK_ASSET_PREFIX = "https://web.archive.org/web/{timestamp}if_/"


@dataclass
class Asset:
    url: str              # Original absolute URL (post-cleaning)
    type: str             # 'image' | 'stylesheet' | 'other'
    attr: str             # Attribute containing the URL ('src' or 'href' or 'style')
    local_path: Optional[str] = None
    content: Optional[bytes] = None


class AssetCollector:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def collect(self, html: str, page_url: str) -> List[Asset]:
        soup = BeautifulSoup(html, 'lxml')
        assets: List[Asset] = []

        # Images
        for img in soup.find_all('img'):
            src = img.get('src')
            if src and not src.startswith('data:'):
                abs_url = urljoin(page_url, src)
                assets.append(Asset(url=abs_url, type='image', attr='src'))
            # srcset candidates
            srcset = img.get('srcset')
            if srcset:
                for candidate in self._parse_srcset(srcset):
                    if candidate and not candidate.startswith('data:'):
                        abs_cand = urljoin(page_url, candidate)
                        assets.append(Asset(url=abs_cand, type='image', attr='srcset'))

        # Stylesheets
        for link in soup.find_all('link', rel=lambda v: v and 'stylesheet' in v):
            href = link.get('href')
            if href and not href.startswith('data:'):
                abs_url = urljoin(page_url, href)
                assets.append(Asset(url=abs_url, type='stylesheet', attr='href'))

        # Picture/source srcset
        for source in soup.find_all('source'):
            srcset = source.get('srcset')
            if srcset:
                for candidate in self._parse_srcset(srcset):
                    if candidate and not candidate.startswith('data:'):
                        abs_cand = urljoin(page_url, candidate)
                        assets.append(Asset(url=abs_cand, type='image', attr='srcset'))

        # Inline style attributes url(...)
        for el in soup.find_all(style=True):
            style = el.get('style', '')
            for css_url in self._extract_css_urls(style):
                if css_url and not css_url.startswith('data:'):
                    abs_url = urljoin(page_url, css_url)
                    assets.append(Asset(url=abs_url, type='image', attr='style'))

        # <style> blocks url(...)
        for style_tag in soup.find_all('style'):
            css_text = style_tag.get_text() or ''
            for css_url in self._extract_css_urls(css_text):
                if css_url and not css_url.startswith('data:'):
                    abs_url = urljoin(page_url, css_url)
                    assets.append(Asset(url=abs_url, type='image', attr='style'))

        # De-duplicate by URL
        dedup: Dict[str, Asset] = {}
        for a in assets:
            dedup[a.url] = a
        return list(dedup.values())

    def _extract_css_urls(self, css_text: str) -> List[str]:
        urls = []
        for match in re.finditer(r"url\(([^)]+)\)", css_text, flags=re.I):
            raw = match.group(1).strip().strip('"\'')
            # Skip data URIs
            if raw.lower().startswith('data:'):
                continue
            urls.append(raw)
        # Also capture @import rules with or without url()
        for match in re.finditer(r"@import\s+(?:url\()?['\"]?([^'\")\s]+)", css_text, flags=re.I):
            raw = match.group(1).strip()
            if raw and not raw.lower().startswith('data:'):
                urls.append(raw)
        return urls

    def _parse_srcset(self, srcset: str) -> List[str]:
        # srcset entries are comma-separated; each entry has URL + descriptor
        candidates = []
        for part in srcset.split(','):
            item = part.strip()
            if not item:
                continue
            url_only = item.split()[0]
            candidates.append(url_only)
        return candidates


class AssetDownloader:
    def __init__(self, request_delay: float = 1.5, max_retries: int = 2, rate_limiter=None):
        self.logger = logging.getLogger(__name__)
        self.request_delay = request_delay
        self.max_retries = max_retries
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Archaic/2.0 (AssetDownloader)'
        })

    def _wayback_url(self, asset_url: str, timestamp: str) -> str:
        return WAYBACK_ASSET_PREFIX.format(timestamp=timestamp) + asset_url

    def download(self, assets: List[Asset], dest_dir: str, timestamp: str) -> Dict[str, str]:
        """
        Download assets via Wayback for the given capture timestamp.
        Returns a mapping of original URL -> local file path.
        """
        os.makedirs(dest_dir, exist_ok=True)
        mapping: Dict[str, str] = {}
        for a in assets:
            wayback = self._wayback_url(a.url, timestamp)
            local_rel = self._local_name(a.url)
            local_path = os.path.join(dest_dir, local_rel)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                if self.rate_limiter:
                    self.rate_limiter.acquire()
                resp = self.session.get(wayback, timeout=30)
                resp.raise_for_status()
                with open(local_path, 'wb') as f:
                    f.write(resp.content)
                mapping[a.url] = local_path
            except Exception as e:
                self.logger.warning(f"Failed to download asset: {a.url} ({e})")
        return mapping

    def _local_name(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path
        if not path or path.endswith('/'):
            path = os.path.join(path, 'index')
        return path.lstrip('/')


class AssetRewriter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def rewrite_html(self, html: str, page_url: str, mapping: Dict[str, str], html_dir: str, assets_relroot: str) -> str:
        """
        Rewrite HTML references to point to local paths relative to html_dir.
        assets_relroot: e.g., 'assets/slug'
        """
        soup = BeautifulSoup(html, 'lxml')

        def rel_from_abs(local_abs: str) -> str:
            rel = os.path.relpath(local_abs, html_dir)
            # Normalize to posix separators for HTML
            return rel.replace(os.sep, '/')

        # Images
        for img in soup.find_all('img'):
            src = img.get('src')
            if src and src in mapping:
                img['src'] = rel_from_abs(mapping[src])

        # Stylesheets
        for link in soup.find_all('link', rel=lambda v: v and 'stylesheet' in v):
            href = link.get('href')
            if href and href in mapping:
                link['href'] = rel_from_abs(mapping[href])

        # Inline style attributes
        for el in soup.find_all(style=True):
            style = el.get('style', '')
            new_style = self._rewrite_css_urls(style, mapping, html_dir)
            if new_style != style:
                el['style'] = new_style

        # <style> blocks
        for style_tag in soup.find_all('style'):
            css_text = style_tag.get_text() or ''
            new_css = self._rewrite_css_urls(css_text, mapping, html_dir)
            if new_css != css_text:
                style_tag.string = new_css

        # Rewrite srcset attributes
        for tag in soup.find_all(['img', 'source']):
            srcset = tag.get('srcset')
            if not srcset:
                continue
            parts = []
            for part in srcset.split(','):
                item = part.strip()
                if not item:
                    continue
                tokens = item.split()
                url_only = tokens[0]
                descriptor = ' '.join(tokens[1:]) if len(tokens) > 1 else ''
                if url_only in mapping:
                    rel = rel_from_abs(mapping[url_only])
                    parts.append((rel + (f" {descriptor}" if descriptor else '')).strip())
                else:
                    parts.append(item)
            tag['srcset'] = ', '.join(parts)

        return str(soup)

    def _rewrite_css_urls(self, css_text: str, mapping: Dict[str, str], html_dir: str) -> str:
        def repl(m):
            raw = m.group(1).strip().strip('"\'')
            if raw in mapping:
                rel = os.path.relpath(mapping[raw], html_dir).replace(os.sep, '/')
                return f"url({rel})"
            return m.group(0)

        return re.sub(r"url\(([^)]+)\)", repl, css_text, flags=re.I)

    def embed_single_file(self, html: str, mapping: Dict[str, str], html_dir: str, size_limit: int = 1_500_000) -> str:
        """
        Convert HTML into a single-file by embedding images and stylesheets
        as data URIs (for stylesheets, inline as <style> with content).
        """
        soup = BeautifulSoup(html, 'lxml')

        # Embed images
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            abs_path = mapping.get(src)
            if not abs_path:
                # Resolve relative to HTML directory
                abs_path = os.path.abspath(os.path.join(html_dir, src))
            if os.path.exists(abs_path) and os.path.getsize(abs_path) <= size_limit:
                mime, _ = mimetypes.guess_type(abs_path)
                mime = mime or 'application/octet-stream'
                with open(abs_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                img['src'] = f"data:{mime};base64,{b64}"

        # Inline stylesheets
        for link in list(soup.find_all('link', rel=lambda v: v and 'stylesheet' in v)):
            href = link.get('href')
            if not href:
                continue
            abs_path = mapping.get(href)
            if not abs_path:
                abs_path = os.path.abspath(os.path.join(html_dir, href))
            if not os.path.exists(abs_path):
                continue
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                    css = f.read()
                style_tag = soup.new_tag('style')
                style_tag.string = css
                link.replace_with(style_tag)
            except Exception:
                continue

        return str(soup)

    # Deep CSS pass: download CSS dependencies and rewrite CSS files
    def extract_css_dependencies(self, css_content: str) -> List[str]:
        return [u for u in self._extract_css_urls(css_content) if not u.lower().startswith('data:')]

    def rewrite_css_file(self, css_path: str, mapping: Dict[str, str], html_dir: str) -> None:
        try:
            with open(css_path, 'r', encoding='utf-8', errors='ignore') as f:
                css = f.read()
            new_css = self._rewrite_css_urls(css, mapping, html_dir)
            if new_css != css:
                with open(css_path, 'w', encoding='utf-8') as f:
                    f.write(new_css)
        except Exception as e:
            self.logger.warning(f"Failed to rewrite CSS file {css_path}: {e}")
