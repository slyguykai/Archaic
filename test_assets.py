#!/usr/bin/env python3
"""
Focused tests for asset rewriting without network.
"""

import sys
from pathlib import Path

# Add the src directory to the path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from core.assets import AssetRewriter


def test_html_rewrite_basic():
    html = '''<html><head>
    <link rel="stylesheet" href="/css/site.css">
    <style>div{background:url('/img/bg.png')}</style>
    </head><body>
    <img src="https://example.com/img/logo.png">
    </body></html>'''
    mapping = {
        'https://example.com/img/logo.png': '/abs/output/html/assets/page/img/logo.png',
        '/css/site.css': '/abs/output/html/assets/page/css/site.css',
        '/img/bg.png': '/abs/output/html/assets/page/img/bg.png',
    }
    html_dir = '/abs/output/html'
    r = AssetRewriter()
    rewritten = r.rewrite_html(html, 'https://example.com/page', mapping, html_dir, assets_relroot='assets')
    assert 'src="assets/page/img/logo.png"' in rewritten
    assert 'href="assets/page/css/site.css"' in rewritten
    assert "url(assets/page/img/bg.png)" in rewritten


if __name__ == "__main__":
    test_html_rewrite_basic()
    print("✓ asset rewrite tests passed")

