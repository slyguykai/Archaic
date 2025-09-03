#!/usr/bin/env python3
"""
Minimal PDF test to debug the issue
"""
import sys
import os
from pathlib import Path

# Add the src directory to the path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

def test_simple_pdf():
    """Test basic ReportLab functionality"""
    print("Testing simple PDF generation...")
    
    # Create output directory
    os.makedirs("test_output", exist_ok=True)
    
    # Test 1: Basic canvas
    try:
        output_path = "test_output/simple_canvas.pdf"
        c = canvas.Canvas(output_path, pagesize=letter)
        c.drawString(100, 750, "Hello World")
        c.save()
        
        if os.path.exists(output_path):
            print(f"✓ Canvas PDF created: {os.path.getsize(output_path)} bytes")
        else:
            print("✗ Canvas PDF failed")
            return False
    except Exception as e:
        print(f"✗ Canvas test failed: {e}")
        return False
    
    # Test 2: SimpleDocTemplate with Paragraph
    try:
        output_path = "test_output/simple_doc.pdf"
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        styles = getSampleStyleSheet()
        
        story = []
        story.append(Paragraph("Test Title", styles['Title']))
        story.append(Paragraph("Test content paragraph", styles['Normal']))
        
        doc.build(story)
        
        if os.path.exists(output_path):
            print(f"✓ Document PDF created: {os.path.getsize(output_path)} bytes")
        else:
            print("✗ Document PDF failed")
            return False
    except Exception as e:
        print(f"✗ Document test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False
    
    print("✓ Basic ReportLab functionality working")
    return True

if __name__ == "__main__":
    test_simple_pdf()