"""
Archaic Orchestrator: runs the end-to-end pipeline (Phases 1–4).

Slice 1 focuses on serial processing, offline assets, and WeasyPrint PDFs.
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass
from typing import Callable, Optional, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from .cdx_client import CDXClient
from .html_retriever import HTMLRetriever
from .html_cleaner import HTMLCleaner
from .pdf_generator import PDFGenerator
from .assets import AssetCollector, AssetDownloader, AssetRewriter, Asset
from utils.file_manager import FileManager
from utils.validators import normalize_host
from utils.manifest import Manifest, ManifestRecord
from utils.rate_limiter import TokenBucket
from urllib.parse import urljoin


@dataclass
class RunConfig:
    base_url: str
    output_dir: str = "output"
    delay_secs: float = 1.5
    max_retries: int = 3
    offline_assets: bool = True
    single_file_html: bool = False
    concurrency: int = 1
    max_pages: int = 0  # 0 = no cap


class ArchaicController:
    def __init__(self, config: RunConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        # Shared rate limiter (~1 token per delay_secs)
        rate = 1.0 / max(self.config.delay_secs, 0.1)
        self.rate_limiter = TokenBucket(rate_per_sec=rate, burst=1, jitter_ms=300)
        self.cdx = CDXClient(request_delay=config.delay_secs)
        self.retriever = HTMLRetriever(request_delay=config.delay_secs, max_retries=config.max_retries, rate_limiter=self.rate_limiter)
        self.cleaner = HTMLCleaner()
        self.pdf = PDFGenerator()
        self.collector = AssetCollector()
        self.downloader = AssetDownloader(request_delay=config.delay_secs, rate_limiter=self.rate_limiter)
        self.rewriter = AssetRewriter()
        self.files = FileManager(config.output_dir)
        self.manifest = Manifest(config.output_dir)
        self._stop_event = threading.Event()
        self._manifest_lock = threading.Lock()

    def stop(self):
        self._stop_event.set()

    def run(self, progress: Optional[Callable[[object], None]] = None) -> Dict[str, int]:
        """Run Phases 1–4 serially with manifest tracking."""
        stats = {"discovered": 0, "downloaded": 0, "cleaned": 0, "pdf": 0, "failed": 0}

        # Phase 1: Discover
        if progress:
            progress("Discovering URLs via CDX...")
        pages = self.cdx.discover_urls(self.config.base_url)
        stats["discovered"] = len(pages)
        if progress:
            progress({"type": "discovery", "total": len(pages)})
        # Apply cap if specified
        if self.config.max_pages and self.config.max_pages > 0 and len(pages) > self.config.max_pages:
            pages = pages[: self.config.max_pages]
            if progress:
                progress({"type": "discovery_cap", "processing": len(pages)})

        # Resume support
        completed = self.manifest.get_completed_set()
        processed: List[Dict[str, str]] = []

        def process_one(idx: int, page: Dict[str, str]) -> Tuple[int, int, int, int]:
            if self._stop_event.is_set():
                return (0, 0, 0, 0)
            url = page['url']
            ts = page['timestamp']
            wayback_url = page['wayback_url']
            ok, norm_url, _ = normalize_host(url)
            nkey = norm_url if ok else url
            if (nkey, ts) in completed:
                self.logger.info(f"Skipping completed: {url} @ {ts}")
                return (0, 0, 0, 0)
            # Append discovered record
            with self._manifest_lock:
                self.manifest.append(ManifestRecord(url=url, normalized_url=nkey, timestamp=ts, wayback_url=wayback_url,
                                                    status='discovered', started_at=time.time(), finished_at=0.0))

            if progress:
                progress({"type": "url", "index": idx, "stage": "downloading", "url": url})
            html_data = self.retriever.retrieve_page(wayback_url, url)
            if not html_data or not html_data.get('html'):
                with self._manifest_lock:
                    self.manifest.append(ManifestRecord(url=url, normalized_url=nkey, timestamp=ts, wayback_url=wayback_url,
                                                        status='failed', error='download_failed', started_at=time.time(),
                                                        finished_at=time.time()))
                if progress:
                    progress({"type": "url", "index": idx, "stage": "failed", "url": url, "reason": "download"})
                return (0, 0, 0, 1)

            if progress:
                progress({"type": "url", "index": idx, "stage": "cleaning", "url": url})
            cleaned = self.cleaner.clean_html(html_data['html'], url)
            if not cleaned:
                with self._manifest_lock:
                    self.manifest.append(ManifestRecord(url=url, normalized_url=nkey, timestamp=ts, wayback_url=wayback_url,
                                                        status='failed', error='clean_failed', started_at=time.time(),
                                                        finished_at=time.time()))
                if progress:
                    progress({"type": "url", "index": idx, "stage": "failed", "url": url, "reason": "clean"})
                return (0, 0, 0, 1)

            final_html = cleaned
            assets_mapping: Dict[str, str] = {}
            html_path, pdf_path = self.files.get_file_paths(url, ts)
            html_dir = os.path.dirname(os.path.abspath(html_path))
            assets_dir = os.path.join(html_dir, 'assets', os.path.splitext(os.path.basename(html_path))[0])

            if self.config.offline_assets:
                if progress:
                    progress({"type": "url", "index": idx, "stage": "assets", "url": url})
                assets = self.collector.collect(cleaned, url)
                assets_mapping = self.downloader.download(assets, assets_dir, ts)
                # Deep CSS pass: for downloaded CSS, fetch dependencies and rewrite CSS files
                css_urls = [u for u in assets_mapping.keys() if u.lower().endswith('.css')]
                for css_url in css_urls:
                    # Read CSS content and extract dependencies
                    local_css = assets_mapping[css_url]
                    try:
                        with open(local_css, 'r', encoding='utf-8', errors='ignore') as f:
                            css_content = f.read()
                        deps = self.rewriter.extract_css_dependencies(css_content)
                        dep_assets = []
                        for d in deps:
                            dep_abs = urljoin(css_url, d)
                            dep_assets.append(Asset(url=dep_abs, type='image', attr='css'))
                        dep_map = self.downloader.download(dep_assets, assets_dir, ts)
                        assets_mapping.update(dep_map)
                        # Rewrite CSS file using updated mapping
                        self.rewriter.rewrite_css_file(local_css, assets_mapping, html_dir)
                    except Exception:
                        pass

                final_html = self.rewriter.rewrite_html(cleaned, url, assets_mapping, html_dir, assets_relroot='assets')

                if self.config.single_file_html:
                    final_html = self.rewriter.embed_single_file(final_html, assets_mapping, html_dir)

            saved_path = self.files.save_html(final_html, url, ts)

            if progress:
                progress({"type": "url", "index": idx, "stage": "pdf", "url": url})
            base_for_pdf = html_dir
            pdf_ok = self.pdf.generate_pdf(final_html, pdf_path, title=None, original_url=url, base_url=base_for_pdf)
            if not pdf_ok:
                with self._manifest_lock:
                    self.manifest.append(ManifestRecord(url=url, normalized_url=nkey, timestamp=ts, wayback_url=wayback_url,
                                                        status='failed', error='pdf_failed', started_at=time.time(),
                                                        finished_at=time.time(), html_path=saved_path, pdf_path=pdf_path))
                if progress:
                    progress({"type": "url", "index": idx, "stage": "failed", "url": url, "reason": "pdf"})
                return (1, 1, 0, 1)
            with self._manifest_lock:
                self.manifest.append(ManifestRecord(url=url, normalized_url=nkey, timestamp=ts, wayback_url=wayback_url,
                                                    status='completed', started_at=time.time(), finished_at=time.time(),
                                                    html_path=saved_path, pdf_path=pdf_path))
                processed.append({
                    'url': url,
                    'timestamp': ts,
                    'html_path': saved_path,
                    'pdf_path': pdf_path,
                })
            if progress:
                progress({"type": "url", "index": idx, "stage": "completed", "url": url})
            return (1, 1, 1, 0)

        if self.config.offline_assets is None:
            self.config.offline_assets = True

        if getattr(self.config, 'concurrency', 1) and self.config.concurrency > 1:
            # Two-worker mode with shared rate limiter
            with ThreadPoolExecutor(max_workers=min(4, self.config.concurrency)) as ex:
                futures = []
                for idx, page in enumerate(pages, 1):
                    futures.append(ex.submit(process_one, idx, page))
                for fut in as_completed(futures):
                    d,c,p,f = fut.result()
                    stats["downloaded"] += d
                    stats["cleaned"] += c
                    stats["pdf"] += p
                    stats["failed"] += f
            # Recompute precise stats from manifest (optional); keep simple for now
        else:
            for i, page in enumerate(pages, 1):
                if self._stop_event.is_set():
                    break
                d,c,p,f = process_one(i, page)
                stats["downloaded"] += d
                stats["cleaned"] += c
                stats["pdf"] += p
                stats["failed"] += f

        # Generate/refresh index from processed entries
        try:
            if processed:
                self.files.generate_index_file(processed)
        except Exception:
            pass

        if progress:
            progress({"type": "counters", "stats": stats})
        return stats
