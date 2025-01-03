import os
import requests
from bs4 import BeautifulSoup
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_bytes
import pytesseract

def fetch_page_content(url):
    """Fetch and extract text content from a webpage or PDF."""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            # print(f"Failed to fetch {url}: Status {response.status_code}")
            return None

        # Check if the response is a PDF by content type
        content_type = response.headers.get('Content-Type', '')
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            # Handle PDF content
            pdf_text = extract_pdf_text(response.content)
            # print("\nfetch_page_content (PDF)\n", pdf_text[:3000])  # Print first 500 characters
            return pdf_text
        else:
            # Handle HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            paragraphs = soup.find_all('p')
            content = '\n'.join([para.get_text() for para in paragraphs])
            # print("\nfetch_page_content (HTML)\n", content[:3000])  # Print first 500 characters
            return content
    except Exception as e:
        print(f"Exception while fetching page content from {url}: {e}")
        return None


def extract_pdf_text(pdf_bytes):
    """Extract text from PDF bytes, handle encrypted or image-based PDFs."""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text = ""

        # Handle encrypted PDFs
        if reader.is_encrypted:
            print("PDF is detected as encrypted.")
            try:
                # Attempt decryption with empty password
                decryption_result = reader.decrypt("")
                if decryption_result == 0:
                    print("Failed to decrypt PDF with empty password.")
                    return "[Encrypted PDF - Unable to extract text]"
                else:
                    print("PDF was encrypted but successfully decrypted.")
            except Exception as e:
                print(f"Exception during PDF decryption: {e}")
                return "[Encrypted PDF - Unable to extract text]"

        # Extract text from each page
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text += page_text
            else:
                print(f"Page {page_number} contains no extractable text, attempting OCR...")
                ocr_text = extract_text_with_ocr(page)
                if ocr_text:
                    text += ocr_text
                else:
                    print(f"OCR failed for page {page_number}.")
                    text += f"\n[No text extracted from page {page_number}]"

        return text if text else "[No text extracted from PDF]"
    except Exception as e:
        print(f"Failed to extract text from PDF: {e}")
        return "[Failed to extract text from PDF]"



def extract_text_with_ocr(page):
    """Extract text from a PDF page using OCR (for image-based PDFs)."""
    try:
        # Check if Tesseract is installed
        if not is_tesseract_installed():
            print("Tesseract OCR is not installed or not found in PATH.")
            return "[OCR not performed: Tesseract not installed]"

        # Convert single PDF page to image
        pdf_writer = PdfWriter()
        pdf_writer.add_page(page)
        pdf_bytes = BytesIO()
        pdf_writer.write(pdf_bytes)
        images = convert_from_bytes(pdf_bytes.getvalue())

        text = ""
        for img_number, img in enumerate(images, start=1):
            print(f"Performing OCR on image {img_number}...")
            extracted_text = pytesseract.image_to_string(img)
            if extracted_text:
                text += extracted_text
            else:
                print(f"OCR returned no text for image {img_number}.")
        return text if text else "[OCR could not extract text]"
    except Exception as e:
        print(f"OCR extraction failed: {e}")
        return "[Failed to extract text with OCR]"


def is_tesseract_installed():
    """Check if Tesseract OCR is installed and accessible."""
    from shutil import which
    return which('tesseract') is not None


# Example usage
if __name__ == "__main__":
    url = "https://www.marines.mil/Portals/1/Publications/USMC%20AI%20STRATEGY%20(SECURED).pdf"
    content = fetch_page_content(url)
    # if content:
    #     print("\nExtracted Content:\n", content[:1000])  # Print first 1000 characters
    # else:
    #     print("No content extracted.")
