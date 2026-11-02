"""
Text chunking module for Manufacturing Manuals.
Splits extracted pages into coherent chunks preserving complete metadata.
"""

import re

class TextChunker:
    def __init__(self, target_chunk_size=500, overlap=100):
        self.target_chunk_size = target_chunk_size
        self.overlap = overlap

    def chunk_pages(self, extracted_pages):
        """
        Takes a list of extracted page dicts from PDFExtractor.
        Returns a list of chunk dicts, each with full provenance metadata.
        """
        all_chunks = []
        chunk_counter = 1

        for page in extracted_pages:
            raw_text = page['text']
            page_num = page['page_number']
            doc_id = page['document_id']
            machine_id = page['machine_id']
            machine_model = page['machine_model']
            pdf_filename = page['pdf_filename']
            revision = page['revision']

            # Split text by sections (paragraphs separated by blank lines or headers)
            paragraphs = [p.strip() for p in raw_text.split('\n\n') if p.strip()]
            
            # Combine paragraphs into chunks of reasonable size
            current_chunk_text = ""
            for p in paragraphs:
                if len(current_chunk_text) + len(p) <= self.target_chunk_size:
                    current_chunk_text += ("\n\n" if current_chunk_text else "") + p
                else:
                    if current_chunk_text:
                        all_chunks.append({
                            'chunk_id': f"{doc_id}_P{page_num}_C{chunk_counter}",
                            'machine_id': machine_id,
                            'machine_model': machine_model,
                            'document_id': doc_id,
                            'revision': revision,
                            'pdf_filename': pdf_filename,
                            'page_number': page_num,
                            'text': current_chunk_text.strip(),
                        })
                        chunk_counter += 1
                    current_chunk_text = p

            if current_chunk_text:
                all_chunks.append({
                    'chunk_id': f"{doc_id}_P{page_num}_C{chunk_counter}",
                    'machine_id': machine_id,
                    'machine_model': machine_model,
                    'document_id': doc_id,
                    'revision': revision,
                    'pdf_filename': pdf_filename,
                    'page_number': page_num,
                    'text': current_chunk_text.strip(),
                })
                chunk_counter += 1

            # Also ensure a full page summary chunk exists if page was split into small pieces,
            # so queries needing cross-section context within the same page receive full context.
            if len(raw_text) > 200:
                all_chunks.append({
                    'chunk_id': f"{doc_id}_P{page_num}_FULL",
                    'machine_id': machine_id,
                    'machine_model': machine_model,
                    'document_id': doc_id,
                    'revision': revision,
                    'pdf_filename': pdf_filename,
                    'page_number': page_num,
                    'text': raw_text.strip(),
                })

        return all_chunks
