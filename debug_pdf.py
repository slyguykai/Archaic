#!/usr/bin/env python3
"""
Debug PDF Generation

Isolate and fix the PDF generation issue by testing with the cleaned HTML
from the real archive test.
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from core.pdf_generator import PDFGenerator

def debug_pdf_generation():
    """Debug the PDF generation with actual content."""
    print("🔍 Debugging PDF Generation")
    
    # Try to read the HTML file that was successfully created
    html_file_path = "test_output/html/theverge.com_2011_11_22_2581110_fcc-to-hold-at-t-t-mobile-merger-hearings-andinvestigate-merger-more_20240630_000000.html"
    
    if os.path.exists(html_file_path):
        print(f"✓ Found HTML file: {html_file_path}")
        
        with open(html_file_path, 'r', encoding='utf-8') as f:
            cleaned_html = f.read()
        
        print(f"✓ Loaded HTML content: {len(cleaned_html):,} characters")
        
        # Create a simple PDF generator
        try:
            generator = PDFGenerator()
            
            # Test with absolute path
            output_path = os.path.abspath("debug_test.pdf")
            print(f"✓ Output path: {output_path}")
            
            # Generate PDF with detailed error handling
            print("🔄 Attempting PDF generation...")
            
            success = generator.generate_pdf(
                html_content=cleaned_html,
                output_path=output_path,
                title="Debug Test Article",
                original_url="https://example.com/debug"
            )
            
            if success:
                print(f"✅ PDF generated successfully!")
                if os.path.exists(output_path):
                    size = os.path.getsize(output_path)
                    print(f"   File size: {size:,} bytes")
                else:
                    print("⚠️  Success reported but file not found")
            else:
                print("❌ PDF generation failed")
            
        except Exception as e:
            print(f"💥 Exception during PDF generation: {e}")
            import traceback
            print("📋 Full traceback:")
            print(traceback.format_exc())
    else:
        print(f"❌ HTML file not found: {html_file_path}")
        print("   Run test_real_archive.py first to generate the HTML file")

if __name__ == "__main__":
    debug_pdf_generation()