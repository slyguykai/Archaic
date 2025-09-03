#!/usr/bin/env python3
"""
Real Archive Testing Script

Test the backend with an actual Wayback Machine URL to validate functionality
with real archived content.
"""

import sys
import os
from pathlib import Path

# Add the src directory to the path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Import our modules
from core.logger import initialize_logging, get_logger, create_error_tracker
from core.html_retriever import HTMLRetriever
from core.html_cleaner import HTMLCleaner
from core.pdf_generator import PDFGenerator
from utils.file_manager import FileManager
from utils.validators import validate_url


def test_real_wayback_url():
    """Test with a real Wayback Machine URL."""
    print("🌐 Testing with Real Wayback Machine URL")
    print("=" * 60)
    
    # Initialize logging
    initialize_logging()
    logger = get_logger('real_archive_test')
    error_tracker = create_error_tracker('real_archive_test')
    
    # Test URL - The Verge article from 2011
    wayback_url = "https://web.archive.org/web/20240630/theverge.com/2011/11/22/2581110/fcc-to-hold-at-t-t-mobile-merger-hearings-andinvestigate-merger-more"
    original_url = "https://theverge.com/2011/11/22/2581110/fcc-to-hold-at-t-t-mobile-merger-hearings-andinvestigate-merger-more"
    
    print(f"📍 Target URL: {original_url}")
    print(f"📦 Wayback URL: {wayback_url}")
    print()
    
    try:
        # Step 1: Validate the original URL
        print("1️⃣ Validating URL...")
        is_valid, normalized_url, error = validate_url(original_url)
        if is_valid:
            print(f"   ✓ URL is valid: {normalized_url}")
        else:
            print(f"   ✗ URL validation failed: {error}")
            return False
        
        # Step 2: Retrieve HTML content
        print("\n2️⃣ Retrieving HTML content...")
        retriever = HTMLRetriever(request_delay=2.0)  # Be extra respectful
        
        def progress_callback(status):
            print(f"   📥 {status}")
        
        html_data = retriever.retrieve_page(wayback_url, original_url, progress_callback)
        
        if not html_data:
            print("   ✗ Failed to retrieve HTML content")
            return False
        
        print(f"   ✓ Retrieved {html_data['size']:,} bytes of HTML")
        print(f"   ✓ Encoding: {html_data['encoding']}")
        
        # Step 3: Clean the HTML
        print("\n3️⃣ Cleaning HTML content...")
        cleaner = HTMLCleaner()
        
        cleaned_html = cleaner.clean_html(html_data['html'], original_url)
        
        if not cleaned_html:
            print("   ✗ HTML cleaning failed")
            return False
        
        original_size = len(html_data['html'])
        cleaned_size = len(cleaned_html)
        reduction = ((original_size - cleaned_size) / original_size) * 100
        
        print(f"   ✓ HTML cleaned successfully")
        print(f"   📊 Size reduction: {original_size:,} → {cleaned_size:,} bytes ({reduction:.1f}% smaller)")
        
        # Step 4: Save cleaned HTML
        print("\n4️⃣ Saving cleaned HTML...")
        file_manager = FileManager("test_output")
        
        # Extract timestamp from wayback URL
        timestamp = "20240630000000"  # Extracted from the URL
        
        html_path = file_manager.save_html(cleaned_html, original_url, timestamp)
        
        if html_path:
            print(f"   ✓ HTML saved: {os.path.basename(html_path)}")
        else:
            print("   ✗ Failed to save HTML")
            return False
        
        # Step 5: Generate PDF
        print("\n5️⃣ Generating PDF...")
        pdf_generator = PDFGenerator()
        
        _, pdf_path = file_manager.get_file_paths(original_url, timestamp)
        
        # Extract title for PDF
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(cleaned_html, 'html.parser')
        title_tag = soup.find('title')
        title = title_tag.get_text().strip() if title_tag else "The Verge Article"
        
        print(f"   📄 Title: {title}")
        
        pdf_success = pdf_generator.generate_pdf(
            html_content=cleaned_html,
            output_path=pdf_path,
            title=title,
            original_url=original_url
        )
        
        if pdf_success and os.path.exists(pdf_path):
            pdf_size = os.path.getsize(pdf_path)
            print(f"   ✓ PDF generated: {os.path.basename(pdf_path)} ({pdf_size:,} bytes)")
        else:
            print("   ✗ PDF generation failed")
            return False
        
        # Step 6: Generate index
        print("\n6️⃣ Creating index...")
        urls_processed = [{
            'url': original_url,
            'timestamp': timestamp,
            'html_path': html_path,
            'pdf_path': pdf_path
        }]
        
        index_path = file_manager.generate_index_file(urls_processed)
        if index_path:
            print(f"   ✓ Index created: {os.path.basename(index_path)}")
        
        # Step 7: Final verification
        print("\n7️⃣ Final verification...")
        
        # Check file sizes and content
        if os.path.exists(html_path) and os.path.exists(pdf_path):
            html_file_size = os.path.getsize(html_path)
            pdf_file_size = os.path.getsize(pdf_path)
            
            print(f"   📁 HTML file: {html_file_size:,} bytes")
            print(f"   📁 PDF file: {pdf_file_size:,} bytes")
            
            # Verify HTML content contains expected elements
            with open(html_path, 'r', encoding='utf-8') as f:
                saved_html = f.read()
            
            # Check for common article elements
            checks = {
                'Title preserved': title.lower() in saved_html.lower(),
                'No Wayback toolbar': 'wm-ipp' not in saved_html,
                'No archive scripts': 'web.archive.org' not in saved_html,
                'Content structure': '<body' in saved_html and '</body>' in saved_html
            }
            
            for check_name, passed in checks.items():
                status = "✓" if passed else "⚠️"
                print(f"   {status} {check_name}")
            
            all_checks_passed = all(checks.values())
            
            if all_checks_passed:
                print("\n🎉 SUCCESS! Real archive URL processed successfully!")
                print(f"\n📋 Summary:")
                print(f"   • Original URL: {original_url}")
                print(f"   • HTML cleaned and saved ({html_file_size:,} bytes)")
                print(f"   • PDF generated ({pdf_file_size:,} bytes)")
                print(f"   • Files saved in: test_output/")
                return True
            else:
                print("\n⚠️  Some content validation checks failed")
                return False
        else:
            print("   ✗ Output files not found")
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        error_tracker.log_error(e, "Real archive URL test", original_url)
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False
    
    finally:
        # Cleanup
        if 'retriever' in locals():
            retriever.close()
        if 'pdf_generator' in locals():
            pdf_generator.close()


def main():
    """Run the real archive test."""
    print("🧪 Archaic Real Archive Test")
    print("Testing backend components with actual archived content")
    print()
    
    success = test_real_wayback_url()
    
    if success:
        print("\n✅ All tests passed! Backend is working with real archive content.")
        print("\n📂 Check the 'test_output/' directory for generated files:")
        print("   • test_output/html/ - Cleaned HTML files")
        print("   • test_output/pdf/ - Generated PDF files") 
        print("   • test_output/index.html - Index of processed files")
        print("   • logs/ - Application logs")
    else:
        print("\n❌ Test failed. Check the output above for details.")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)