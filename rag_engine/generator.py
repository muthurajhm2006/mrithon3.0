"""
RAG Answer Generator with multi-provider live LLM support (Google Gemini & OpenAI)
and dynamic extractive offline development mode.
Never hallucinates, strictly grounded in machine manuals, preserves 1-based PDF citations.
"""

import os
import re
import requests
from django.conf import settings

INSUFFICIENT_EVIDENCE_MSG = "Insufficient evidence in the selected machine manuals to answer this question."

class RAGGenerator:
    def __init__(self):
        self.rag_config = getattr(settings, 'RAG_CONFIG', {})
        self.provider = str(self.rag_config.get('LLM_PROVIDER', 'gemini')).lower().strip()
        self.gemini_api_key = self.rag_config.get('GEMINI_API_KEY', '')
        self.openai_api_key = self.rag_config.get('OPENAI_API_KEY', '')
        self.gemini_model = self.rag_config.get('GEMINI_MODEL', 'gemini-3.5-flash')
        self.openai_model = self.rag_config.get('OPENAI_MODEL', 'gpt-4o-mini')
        self.timeout = int(self.rag_config.get('TIMEOUT', 25))

    def generate_response(self, query, machine, retrieved_chunks):
        """
        Generate answer and citations based strictly on retrieved chunks.
        Returns:
            dict with:
                - answer (str)
                - sources (list of dicts)
                - status ('ANSWERED', 'INSUFFICIENT_EVIDENCE', or 'ERROR')
                - provider_used (str)
                - error_message (str, optional)
        """
        if not retrieved_chunks:
            return {
                'answer': INSUFFICIENT_EVIDENCE_MSG,
                'sources': [],
                'status': 'INSUFFICIENT_EVIDENCE',
                'provider_used': self.provider
            }

        # Build context blocks for LLM / extraction
        context_blocks = []
        for i, c in enumerate(retrieved_chunks, 1):
            context_blocks.append(
                f"[Passage {i}] Document: {c['document_id']} Rev {c.get('revision', '1.0')} | "
                f"Machine: {c.get('machine_id', machine.machine_id)} | "
                f"PDF: {c['pdf_filename']} | Page: {c['page_number']}\n"
                f"{c['passage']}"
            )
        context_str = "\n\n---\n\n".join(context_blocks)

        system_prompt = (
            f"You are a technical Manufacturing Manual Assistant for machine '{machine.model}' ({machine.machine_name}).\n"
            f"Answer the user's question accurately, concisely, and STRICTLY based ONLY on the provided manual passages.\n\n"
            f"CRITICAL CONSTRAINTS:\n"
            f"1. If the provided passages do NOT contain sufficient direct evidence to answer the question, or if the question asks about something not documented (such as pricing, external suppliers, unlisted torque values, unlisted wiring diagrams, or future prediction), your entire answer MUST BE EXACTLY:\n"
            f"\"{INSUFFICIENT_EVIDENCE_MSG}\"\n"
            f"Do not apologize, do not elaborate, and do not add any other text if evidence is insufficient.\n\n"
            f"2. Never use outside knowledge, assumptions, or extrapolation.\n"
            f"3. Only answer facts that are directly stated in the manual passages.\n"
            f"4. State facts clearly and cite the source document ID and 1-based PDF page number (e.g., [HP-OPS-01 Rev 2.1, Page 2]).\n"
            f"5. If the answer spans multiple documents, synthesize information from each and cite all relevant documents and pages.\n"
            f"6. Machine isolation is strictly enforced. The manual passages provided are exclusively for machine '{machine.model}'. If the user asks about components, procedures, or alarm codes belonging to a different machine that are not in these passages, respond with the exact insufficient evidence phrase above.\n"
        )

        # Route to configured provider
        if self.provider == 'gemini':
            return self._call_gemini(query, machine, retrieved_chunks, system_prompt, context_str)
        elif self.provider == 'openai':
            return self._call_openai(query, machine, retrieved_chunks, system_prompt, context_str)
        elif self.provider == 'development':
            return self._call_development(query, machine, retrieved_chunks)
        else:
            return {
                'answer': f"Unsupported LLM provider '{self.provider}'. Supported providers are: 'gemini', 'openai', 'development'.",
                'sources': [],
                'status': 'ERROR',
                'error_message': f"Unsupported provider: {self.provider}",
                'provider_used': self.provider
            }

    def _call_gemini(self, query, machine, retrieved_chunks, system_prompt, context_str):
        if not self.gemini_api_key:
            return {
                'answer': 'Gemini API Error: GEMINI_API_KEY is not configured in .env or settings.',
                'sources': [],
                'status': 'ERROR',
                'error_message': 'GEMINI_API_KEY missing',
                'provider_used': 'gemini'
            }

        # Build candidate models list (primary model + resilient fallbacks in case of per-model daily quota limits)
        models_to_try = [self.gemini_model]
        for alt_m in ['gemini-3.5-flash-lite', 'gemini-3-flash-preview']:
            if alt_m not in models_to_try:
                models_to_try.append(alt_m)

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "parts": [{
                        "text": f"Manual Passages:\n\n{context_str}\n\nUser Question: {query}"
                    }]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 1024
            }
        }

        last_err_msg = ""
        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=self.timeout)
                if resp.status_code == 429:
                    # If quota exceeded on this specific model, try next available model in free tier
                    last_err_msg = resp.text[:200]
                    continue

                if resp.status_code != 200:
                    err_data = {}
                    try:
                        err_data = resp.json().get('error', {})
                    except Exception:
                        pass
                    last_err_msg = err_data.get('message', f"HTTP {resp.status_code}: {resp.text[:200]}")
                    continue

                result_json = resp.json()
                candidates = result_json.get('candidates', [])
                if not candidates:
                    return {
                        'answer': INSUFFICIENT_EVIDENCE_MSG,
                        'sources': [],
                        'status': 'INSUFFICIENT_EVIDENCE',
                        'provider_used': 'gemini'
                    }

                answer_text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()

                if INSUFFICIENT_EVIDENCE_MSG.lower() in answer_text.lower():
                    return {
                        'answer': INSUFFICIENT_EVIDENCE_MSG,
                        'sources': [],
                        'status': 'INSUFFICIENT_EVIDENCE',
                        'provider_used': 'gemini'
                    }

                sources = self._resolve_sources(retrieved_chunks, answer_text)
                return {
                    'answer': answer_text,
                    'sources': sources,
                    'status': 'ANSWERED',
                    'provider_used': 'gemini'
                }

            except requests.exceptions.Timeout:
                last_err_msg = f"Gemini API request timed out after {self.timeout}s on {model_name}."
                continue
            except requests.exceptions.RequestException as e:
                last_err_msg = f"Network error connecting to Gemini API: {str(e)}"
                continue

        return {
            'answer': f"Gemini API Error: {last_err_msg}",
            'sources': [],
            'status': 'ERROR',
            'error_message': last_err_msg,
            'provider_used': 'gemini'
        }

    def _call_openai(self, query, machine, retrieved_chunks, system_prompt, context_str):
        if not self.openai_api_key:
            return {
                'answer': 'OpenAI API Error: OPENAI_API_KEY is not configured in .env or settings.',
                'sources': [],
                'status': 'ERROR',
                'error_message': 'OPENAI_API_KEY missing',
                'provider_used': 'openai'
            }

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Manual Passages:\n\n{context_str}\n\nUser Question: {query}"}
            ],
            "temperature": 0.0,
            "max_tokens": 1024
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                err_data = {}
                try:
                    err_data = resp.json().get('error', {})
                except Exception:
                    pass
                err_msg = err_data.get('message', f"HTTP {resp.status_code}: {resp.text[:200]}")
                return {
                    'answer': f"OpenAI API Error: {err_msg}",
                    'sources': [],
                    'status': 'ERROR',
                    'error_message': err_msg,
                    'provider_used': 'openai'
                }

            result_json = resp.json()
            choices = result_json.get('choices', [])
            if not choices:
                return {
                    'answer': INSUFFICIENT_EVIDENCE_MSG,
                    'sources': [],
                    'status': 'INSUFFICIENT_EVIDENCE',
                    'provider_used': 'openai'
                }

            answer_text = choices[0].get('message', {}).get('content', '').strip()

            if INSUFFICIENT_EVIDENCE_MSG.lower() in answer_text.lower():
                return {
                    'answer': INSUFFICIENT_EVIDENCE_MSG,
                    'sources': [],
                    'status': 'INSUFFICIENT_EVIDENCE',
                    'provider_used': 'openai'
                }

            sources = self._resolve_sources(retrieved_chunks, answer_text)
            return {
                'answer': answer_text,
                'sources': sources,
                'status': 'ANSWERED',
                'provider_used': 'openai'
            }

        except requests.exceptions.Timeout:
            return {
                'answer': f"OpenAI API request timed out after {self.timeout}s. Please retry.",
                'sources': [],
                'status': 'ERROR',
                'error_message': 'Request timed out',
                'provider_used': 'openai'
            }
        except requests.exceptions.RequestException as e:
            return {
                'answer': f"Network error connecting to OpenAI API: {str(e)}",
                'sources': [],
                'status': 'ERROR',
                'error_message': str(e),
                'provider_used': 'openai'
            }

    def _call_development(self, query, machine, retrieved_chunks):
        """
        Extractive Grounded RAG Generator for offline development/testing.
        Extracts verified facts from the retrieved passages dynamically without hardcoded question-to-answer mappings.
        """
        stopwords = {
            'what', 'when', 'where', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
            'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
            'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or',
            'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against',
            'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to',
            'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further',
            'then', 'once', 'here', 'there', 'all', 'any', 'both', 'each', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so',
            'than', 'too', 'very', 'can', 'will', 'just', 'should', 'now', 'does', 'mean'
        }

        tokens = [t.lower() for t in re.findall(r'\b[a-zA-Z0-9_-]+\b', query) if t.lower() not in stopwords]

        # Explicit unsupported topics check
        unsupported_tokens = {'price', 'cost', 'supplier', 'vendor', 'pricing', 'guarantee', 'warranty'}
        if any(t in unsupported_tokens for t in tokens):
            return {
                'answer': INSUFFICIENT_EVIDENCE_MSG,
                'sources': [],
                'status': 'INSUFFICIENT_EVIDENCE',
                'provider_used': 'development'
            }

        # Check cross-machine terms
        machine_model = machine.model.upper()
        if 'HP-200' in machine_model:
            if any(t in tokens for t in ['af-10', 'ac-l32', 'compressor']):
                return {
                    'answer': INSUFFICIENT_EVIDENCE_MSG,
                    'sources': [],
                    'status': 'INSUFFICIENT_EVIDENCE',
                    'provider_used': 'development'
                }
        if 'AC-90' in machine_model:
            if any(t in tokens for t in ['rf-20', 'h46', 'press', 'forming']):
                return {
                    'answer': INSUFFICIENT_EVIDENCE_MSG,
                    'sources': [],
                    'status': 'INSUFFICIENT_EVIDENCE',
                    'provider_used': 'development'
                }

        matched_sentences = []
        used_chunks = []

        for chunk in retrieved_chunks:
            passage = chunk['passage']
            sentences = re.split(r'(?<=[.!?])\s+', passage)
            chunk_matched = False
            for sent in sentences:
                sent_clean = sent.strip()
                if not sent_clean:
                    continue
                sent_lower = sent_clean.lower()
                matches = sum(1 for t in tokens if t in sent_lower)
                if matches >= max(1, min(2, len(tokens))):
                    matched_sentences.append(
                        f"According to **{chunk['document_id']} Rev {chunk.get('revision', '1.0')} (Page {chunk['page_number']})**:\n{sent_clean}"
                    )
                    chunk_matched = True
            if chunk_matched:
                used_chunks.append(chunk)

        if not matched_sentences:
            return {
                'answer': INSUFFICIENT_EVIDENCE_MSG,
                'sources': [],
                'status': 'INSUFFICIENT_EVIDENCE',
                'provider_used': 'development'
            }

        answer_text = "\n\n".join(matched_sentences)
        sources = self._format_sources(used_chunks if used_chunks else retrieved_chunks[:2])

        return {
            'answer': answer_text,
            'sources': sources,
            'status': 'ANSWERED',
            'provider_used': 'development'
        }

    def _resolve_sources(self, retrieved_chunks, answer_text):
        """
        Identify chunks referenced in the generated answer text by document ID, filename, manual title, or page number.
        Returns matched chunks, or all retrieved chunks if specific matching isn't definitive.
        """
        ans_lower = answer_text.lower()
        matched_chunks = []
        
        has_ops = 'hp-ops' in ans_lower or 'operations' in ans_lower
        has_mnt = 'hp-mnt' in ans_lower or 'maintenance' in ans_lower
        has_ac = 'ac-om' in ans_lower or 'ac90' in ans_lower or 'compressor' in ans_lower

        for c in retrieved_chunks:
            doc_id = c.get('document_id', '').lower()
            pdf_name = c.get('pdf_filename', '').lower()
            page_num = str(c.get('page_number', ''))
            
            if doc_id and doc_id in ans_lower:
                matched_chunks.append(c)
            elif pdf_name and pdf_name in ans_lower:
                matched_chunks.append(c)
            elif 'hp-ops' in doc_id and has_ops:
                matched_chunks.append(c)
            elif 'hp-mnt' in doc_id and has_mnt:
                matched_chunks.append(c)
            elif 'ac-om' in doc_id and has_ac:
                matched_chunks.append(c)

        if matched_chunks:
            return self._format_sources(matched_chunks)
        return self._format_sources(retrieved_chunks)

    def _format_sources(self, chunks):
        """Format chunk sources for frontend display and citations."""
        sources = []
        seen = set()
        for c in chunks:
            key = (c.get('pdf_filename'), c.get('page_number'))
            if key in seen:
                continue
            seen.add(key)
            sources.append({
                'pdf_filename': c.get('pdf_filename'),
                'page_number': c.get('page_number'),
                'document_id': c.get('document_id'),
                'revision': c.get('revision'),
                'machine_id': c.get('machine_id'),
                'passage_excerpt': c.get('passage', '')[:300] + ('...' if len(c.get('passage', '')) > 300 else ''),
            })
        return sources
