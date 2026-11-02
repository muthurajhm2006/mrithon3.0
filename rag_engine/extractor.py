"""
PDF text and page extraction using PyMuPDF.
Preserves 1-based PDF page numbers and metadata.
"""

import os
import pymupdf

class PDFExtractor:
    @staticmethod
    def extract_manual_pages(pdf_path, machine_id, machine_model, document_id, revision, pdf_filename):
        """
        Extract each page separately from the PDF document.
        Preserves original one-based page numbers.
        Returns a list of page dicts.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
            
        doc = pymupdf.open(pdf_path)
        extracted_pages = []
        
        for index in range(len(doc)):
            page = doc[index]
            page_number = index + 1  # Exactly 1-based page numbering
            text = page.get_text()
            
            extracted_pages.append({
                'machine_id': machine_id,
                'machine_model': machine_model,
                'document_id': document_id,
                'revision': revision,
                'pdf_filename': pdf_filename,
                'page_number': page_number,
                'text': text.strip(),
            })
            
        doc.close()
        return extracted_pages

    @staticmethod
    def render_page_image(pdf_path, page_number, output_image_path):
        """
        Render a PDF page to an image (PNG) for visual preview in the browser.
        page_number is 1-based.
        """
        if not os.path.exists(pdf_path):
            return None
            
        doc = pymupdf.open(pdf_path)
        if 1 <= page_number <= len(doc):
            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=150)
            os.makedirs(os.path.dirname(output_image_path), exist_ok=True)
            pix.save(output_image_path)
            doc.close()
            return output_image_path
        doc.close()
        return None
