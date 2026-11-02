"""
Vector Store and Hybrid Retrieval Engine using FAISS and Semantic Embeddings.
Enforces strict machine-level isolation before retrieval.
"""

import os
import json
import re
import numpy as np
import faiss
from sklearn.feature_extraction.text import TfidfVectorizer

class HybridVectorStore:
    def __init__(self, storage_dir=None):
        self.storage_dir = storage_dir
        self.chunks = []  # list of chunk dicts
        self.vectorizer = None
        self.index = None
        self.dimension = None
        
        # Try loading SentenceTransformer if network/cache allows, otherwise fall back to local TF-IDF dense vectors
        self.st_model = None
        try:
            from sentence_transformers import SentenceTransformer
            # Only use if already cached or quickly available
            self.st_model = SentenceTransformer('all-MiniLM-L6-v2')
            self.dimension = 384
        except Exception:
            self.st_model = None

    def _extract_technical_tokens(self, text):
        """Extract uppercase alphanumeric codes like E17, RF-20, AC-90, M-HP200, bar, etc."""
        return set(re.findall(r'\b[A-Za-z0-9\-_]{2,}\b', text.lower()))

    def _compute_embeddings(self, texts):
        if self.st_model is not None:
            try:
                embeddings = self.st_model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
                return np.array(embeddings, dtype='float32')
            except Exception:
                pass
                
        # Robust local TF-IDF normalized dense vectors
        if self.vectorizer is None:
            self.vectorizer = TfidfVectorizer(
                ngram_range=(1, 3),
                token_pattern=r'(?u)\b\w+\b|E\d+|RF-\d+|AF-\d+|M-[A-Za-z0-9]+',
                sublinear_tf=True
            )
            tfidf_matrix = self.vectorizer.fit_transform(texts).toarray().astype('float32')
        else:
            tfidf_matrix = self.vectorizer.transform(texts).toarray().astype('float32')

        norms = np.linalg.norm(tfidf_matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = tfidf_matrix / norms
        return normalized

    def build_index(self, chunks):
        """Build FAISS vector index from a list of chunk dicts."""
        self.chunks = list(chunks)
        if not self.chunks:
            self.index = None
            return

        texts = [c['text'] for c in self.chunks]
        embeddings = self._compute_embeddings(texts)
        self.dimension = embeddings.shape[1]

        # Inner product on normalized vectors equals cosine similarity
        self.index = faiss.IndexFlatIP(self.dimension)
        self.index.add(embeddings)

    def add_chunks(self, new_chunks):
        """Add new chunks and re-index."""
        # Deduplicate based on chunk_id
        existing_ids = {c['chunk_id'] for c in self.chunks}
        filtered_new = [c for c in new_chunks if c['chunk_id'] not in existing_ids]
        
        all_chunks = self.chunks + filtered_new
        self.build_index(all_chunks)

    def search(self, query, machine_id, top_k=4):
        """
        Search for relevant passages strictly for the specified machine_id.
        machine_id can be 'M-HP200' or 'HP-200', 'M-AC90' or 'AC-90'.
        
        CRITICAL REQUIREMENT:
        Retrieval excludes passages belonging to another machine before scoring.
        """
        if not self.chunks or self.index is None:
            return []

        # Machine-level isolation filter
        machine_norm = machine_id.strip().upper().replace("M-", "").replace("M_", "")
        
        candidate_indices = []
        for idx, chunk in enumerate(self.chunks):
            chunk_m_id = chunk.get('machine_id', '').upper().replace("M-", "").replace("M_", "")
            chunk_m_model = chunk.get('machine_model', '').upper().replace("M-", "").replace("M_", "")
            
            # Check if chunk matches requested machine
            if machine_norm == chunk_m_id or machine_norm == chunk_m_model or (machine_norm in chunk_m_id) or (machine_norm in chunk_m_model):
                candidate_indices.append(idx)

        if not candidate_indices:
            return []

        # Compute query embedding
        query_emb = self._compute_embeddings([query])
        
        # Score candidates
        candidate_texts = [self.chunks[i]['text'] for i in candidate_indices]
        candidate_embeddings = self._compute_embeddings(candidate_texts)
        
        # Dense vector cosine similarity
        dense_scores = np.dot(candidate_embeddings, query_emb.T).flatten()

        query_tokens = self._extract_technical_tokens(query)
        
        results = []
        for pos, orig_idx in enumerate(candidate_indices):
            chunk = self.chunks[orig_idx]
            base_score = float(dense_scores[pos])
            
            # Technical keyword bonus (exact matches for alarm codes like E17, part names, units)
            chunk_tokens = self._extract_technical_tokens(chunk['text'])
            matched_tokens = query_tokens.intersection(chunk_tokens)
            
            # High boost for critical codes (E17, E24, E08, E31, E42, RF-20, AF-10, pressure, bar, temperature)
            tech_boost = 0.0
            for t in matched_tokens:
                if re.match(r'^e\d+$', t):
                    tech_boost += 0.45
                elif 'rf-' in t or 'af-' in t or 'h46' in t or 'l32' in t:
                    tech_boost += 0.40
                elif t in ('pressure', 'temperature', 'filter', 'leak', 'drain', 'alarm', 'hold', 'bar'):
                    tech_boost += 0.15

            final_score = base_score + tech_boost
            
            results.append({
                'chunk_id': chunk['chunk_id'],
                'machine_id': chunk['machine_id'],
                'machine_model': chunk['machine_model'],
                'document_id': chunk['document_id'],
                'revision': chunk['revision'],
                'pdf_filename': chunk['pdf_filename'],
                'page_number': chunk['page_number'],
                'passage': chunk['text'],
                'score': final_score,
            })

        # Sort by relevance score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        
        # Deduplicate overlapping chunks from same doc and page to maximize document diversity
        unique_results = []
        seen_pages = set()
        for r in results:
            key = (r['document_id'], r['page_number'])
            if key not in seen_pages:
                seen_pages.add(key)
                unique_results.append(r)
                
            if len(unique_results) >= top_k:
                break

        return unique_results

    def save(self, directory):
        """Persist chunks to disk."""
        os.makedirs(directory, exist_ok=True)
        chunks_file = os.path.join(directory, 'chunks.json')
        with open(chunks_file, 'w', encoding='utf-8') as f:
            json.dump(self.chunks, f, indent=2)

    def load(self, directory):
        """Load persisted chunks from disk."""
        chunks_file = os.path.join(directory, 'chunks.json')
        if os.path.exists(chunks_file):
            with open(chunks_file, 'r', encoding='utf-8') as f:
                self.chunks = json.load(f)
            self.build_index(self.chunks)
            return True
        return False

# Global singleton instance for the app
_vector_store_instance = None

def get_vector_store():
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = HybridVectorStore()
        # Auto-load if data exists
        from django.conf import settings
        storage_dir = getattr(settings, 'RAG_CONFIG', {}).get('VECTOR_STORE_DIR')
        if storage_dir and os.path.exists(os.path.join(storage_dir, 'chunks.json')):
            _vector_store_instance.load(storage_dir)
    return _vector_store_instance
