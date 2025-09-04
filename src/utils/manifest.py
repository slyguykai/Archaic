"""
Manifest utilities for tracking per-URL processing state and enabling resume.
Stores an append-only JSON Lines file with one record per processed URL.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Iterable


DEFAULT_MANIFEST_NAME = "manifest.jsonl"


@dataclass
class ManifestRecord:
    url: str
    normalized_url: str
    timestamp: str
    wayback_url: str
    status: str  # discovered|downloading|cleaned|assets|pdf|completed|failed
    html_path: Optional[str] = None
    pdf_path: Optional[str] = None
    started_at: float = 0.0
    finished_at: float = 0.0
    error: Optional[str] = None


class Manifest:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.path = os.path.join(self.output_dir, DEFAULT_MANIFEST_NAME)

    def append(self, rec: ManifestRecord) -> None:
        with open(self.path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")

    def iter_records(self) -> Iterable[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue

    def get_completed_set(self) -> set:
        done = set()
        for rec in self.iter_records():
            if rec.get('status') == 'completed' and rec.get('normalized_url'):
                key = (rec['normalized_url'], rec.get('timestamp'))
                done.add(key)
        return done

    def get_status_sets(self):
        """
        Compute latest status per (normalized_url, timestamp) and return sets
        for completed and failed entries.
        """
        latest = {}
        for rec in self.iter_records():
            key = (rec.get('normalized_url'), rec.get('timestamp'))
            if not key[0] or not key[1]:
                continue
            latest[key] = rec.get('status')
        completed = {k for k, v in latest.items() if v == 'completed'}
        failed = {k for k, v in latest.items() if v == 'failed'}
        return completed, failed
