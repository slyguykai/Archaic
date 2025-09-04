# Archaic

Archival Web Scraper & PDF Converter.

Status: Backend Slice 1 implemented
- CDX discovery (latest captures across http/https + host variants)
- Respectful retrieval with delay/backoff
- Wayback UI cleaning
- Offline assets bundling (images + stylesheets) and HTML rewrite
- WeasyPrint PDF generation (local-only fetch)
- Manifest JSONL for resume

Requirements
- Python 3.10+
- pip install -r requirements.txt
- WeasyPrint system deps: Cairo, Pango, GDK-Pixbuf (platform-specific)
  See https://weasyprint.org/docs/install/

Orchestrator (headless) example
```python
from src.core.controller import ArchaicController, RunConfig

cfg = RunConfig(
    base_url="example.com/articles/",
    output_dir="output",
    delay_secs=1.5,
    offline_assets=True,
    single_file_html=False,
)

ctrl = ArchaicController(cfg)
stats = ctrl.run(progress=lambda s: print(s))
print(stats)
```

GUI
- Run: `python -m src.gui.app`
- Fields: URL, output directory, Offline assets, Single-file HTML.
- Advanced: Concurrency (1 or 2), Delay (seconds).

Notes
- Single-file HTML embedding is available (images + stylesheets). Disable if files get too large.
- Concurrency is serial by default; an advanced 2-worker mode with a global rate limiter is available in Advanced settings.
