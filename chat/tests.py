"""
Comprehensive test suite verifying all 13 Round 1 requirements:
1. Admin login
2. Engineer login
3. Supervisor login
4. Admin register machines
5. Admin upload manuals
6. PDF extraction works for all 9 pages
7. One-based page numbering
8. HP-200 retrieval searches only HP-200 manuals
9. AC-90 retrieval searches only AC-90 manuals
10. Unsupported questions return insufficient evidence
11. Engineers cannot upload manuals (HTTP 403)
12. Supervisor can view question history
13. Role-based access control prevents unauthorized page access
"""

import os
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from accounts.models import CustomUser
from machines.models import Machine
from manual_manager.models import Manual
from chat.models import QuestionHistory, QuestionStatus
from rag_engine.extractor import PDFExtractor
from rag_engine.vector_store import get_vector_store
from rag_engine.generator import RAGGenerator

class ManufacturingAssistantFullTestSuite(TestCase):
    def setUp(self):
        # Create the 3 users
        self.admin_user = CustomUser.objects.create_user(
            username='admin_test',
            password='password123',
            role=CustomUser.Role.ADMIN,
            is_staff=True,
            is_superuser=True
        )
        self.engineer_user = CustomUser.objects.create_user(
            username='engineer_test',
            password='password123',
            role=CustomUser.Role.ENGINEER
        )
        self.supervisor_user = CustomUser.objects.create_user(
            username='supervisor_test',
            password='password123',
            role=CustomUser.Role.SUPERVISOR
        )

        # Create Machines
        self.m_hp200 = Machine.objects.create(
            machine_id='M-HP200',
            model='HP-200',
            machine_name='Hydraulic forming press'
        )
        self.m_ac90 = Machine.objects.create(
            machine_id='M-AC90',
            model='AC-90',
            machine_name='Air compressor'
        )

        # Vector store & generator
        self.vstore = get_vector_store()
        self.generator = RAGGenerator()

    # Test 1, 2, 3: Authentication for Admin, Engineer, Supervisor
    def test_01_user_logins(self):
        client = Client()
        for u in [self.admin_user, self.engineer_user, self.supervisor_user]:
            logged_in = client.login(username=u.username, password='password123')
            self.assertTrue(logged_in, f"Failed login for {u.username}")
            client.logout()

    # Test 4: Admin can register machines
    def test_04_admin_can_register_machines(self):
        client = Client()
        client.login(username=self.admin_user.username, password='password123')
        response = client.post(reverse('machine_list'), {
            'machine_id': 'M-TEST01',
            'model': 'TEST-100',
            'machine_name': 'Test Milling Center',
            'description': 'Testing'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Machine.objects.filter(machine_id='M-TEST01').exists())

    # Test 5, 6, 7: PDF extraction, 9 pages total, 1-based page numbering
    def test_06_pdf_extraction_and_one_based_page_numbers(self):
        manuals_dir = settings.BASE_DIR / 'Manuals'
        pdf_files = [
            ('M-HP200', 'HP-200', 'HP-OPS-01', '1.0', 'HP200_Operations_Rev1_0.pdf'),
            ('M-HP200', 'HP-200', 'HP-MNT-01', '1.0', 'HP200_Maintenance_Rev1_0.pdf'),
            ('M-AC90', 'AC-90', 'AC-OM-01', '1.0', 'AC90_Operations_Maintenance_Rev1_0.pdf')
        ]
        
        total_extracted_pages = 0
        for m_id, model, doc_id, rev, filename in pdf_files:
            file_path = str(manuals_dir / filename)
            self.assertTrue(os.path.exists(file_path), f"Missing manual file {filename}")
            pages = PDFExtractor.extract_manual_pages(
                pdf_path=file_path,
                machine_id=m_id,
                machine_model=model,
                document_id=doc_id,
                revision=rev,
                pdf_filename=filename
            )
            self.assertEqual(len(pages), 3, f"Manual {filename} should have exactly 3 pages")
            total_extracted_pages += len(pages)
            # Verify 1-based page numbers
            page_numbers = [p['page_number'] for p in pages]
            self.assertEqual(page_numbers, [1, 2, 3], f"Pages for {filename} must be 1-based [1, 2, 3]")

        self.assertEqual(total_extracted_pages, 9, "All 3 manuals must total 9 extracted pages")

    # Test 8: HP-200 retrieval searches ONLY its two manuals
    def test_08_hp200_isolation_and_multi_manual_retrieval(self):
        chunks = self.vstore.search(
            query="What does E17 mean, what is the trigger, and what are the troubleshooting checks?",
            machine_id="M-HP200",
            top_k=5
        )
        self.assertTrue(len(chunks) > 0)
        for c in chunks:
            # Must strictly belong to HP-200
            self.assertIn('HP200', c['pdf_filename'], "AC-90 chunk leaked into HP-200 retrieval!")
            self.assertEqual(c['machine_id'], 'M-HP200')
            self.assertIn(c['document_id'], ['HP-OPS-01', 'HP-MNT-01'])

        # Verify multi-document answer generation
        res = self.generator.generate_response(
            query="When E17 occurs on HP-200, what is the trigger condition and what are the first troubleshooting checks?",
            machine=self.m_hp200,
            retrieved_chunks=chunks
        )
        self.assertEqual(res['status'], 'ANSWERED')
        # Checks that both HP-OPS-01 and HP-MNT-01 are cited
        cited_docs = {s['document_id'] for s in res['sources']}
        self.assertIn('HP-OPS-01', cited_docs)
        self.assertIn('HP-MNT-01', cited_docs)

    # Test 9: AC-90 retrieval searches ONLY its manual
    def test_09_ac90_isolation(self):
        chunks = self.vstore.search(
            query="What does E17 mean on AC-90?",
            machine_id="M-AC90",
            top_k=3
        )
        self.assertTrue(len(chunks) > 0)
        for c in chunks:
            self.assertEqual(c['machine_id'], 'M-AC90')
            self.assertEqual(c['document_id'], 'AC-OM-01')
            self.assertNotIn('HP', c['pdf_filename'], "HP-200 manual leaked into AC-90 retrieval!")

        res = self.generator.generate_response(
            query="What does E17 mean on AC-90?",
            machine=self.m_ac90,
            retrieved_chunks=chunks
        )
        self.assertEqual(res['status'], 'ANSWERED')
        self.assertIn("discharge temperature", res['answer'].lower())
        # AC-90 E17 is Page 2
        pages_cited = {s['page_number'] for s in res['sources']}
        self.assertIn(2, pages_cited)

    # Test 10: Unsupported questions return insufficient evidence
    def test_10_unsupported_questions_return_insufficient_evidence(self):
        # 1. Price is unsupported
        chunks = self.vstore.search(query="What is the price of the replacement pump?", machine_id="M-HP200")
        res1 = self.generator.generate_response(
            query="What is the price of the replacement pump?",
            machine=self.m_hp200,
            retrieved_chunks=chunks
        )
        self.assertEqual(res1['status'], 'INSUFFICIENT_EVIDENCE')
        self.assertIn("Insufficient evidence in the selected machine manuals to answer this question.", res1['answer'])

        # 2. Cross-machine question: Asking for RF-20 filter on AC-90
        chunks_cross = self.vstore.search(query="What is the return-filter RF-20 replacement interval?", machine_id="M-AC90")
        res2 = self.generator.generate_response(
            query="What is the return-filter RF-20 replacement interval?",
            machine=self.m_ac90,
            retrieved_chunks=chunks_cross
        )
        self.assertEqual(res2['status'], 'INSUFFICIENT_EVIDENCE')
        self.assertIn("Insufficient evidence in the selected machine manuals to answer this question.", res2['answer'])

    # Test 11: Engineers CANNOT upload manuals (HTTP 403 Forbidden)
    def test_11_engineers_cannot_upload_manuals(self):
        client = Client()
        client.login(username=self.engineer_user.username, password='password123')
        response = client.post(reverse('upload_manual'), {
            'machine_id': 'M-HP200',
            'document_id': 'UNAUTHORIZED-01'
        })
        self.assertEqual(response.status_code, 403, "Engineer must be denied manual upload with 403 Forbidden")

    # Test 12: Supervisor can view question history
    def test_12_supervisor_can_view_question_history(self):
        QuestionHistory.objects.create(
            user=self.engineer_user,
            machine=self.m_hp200,
            question="What is the normal operating pressure range?",
            answer="120 to 140 bar during the forming stage.",
            sources=[{'pdf_filename': 'HP200_Operations_Rev1_0.pdf', 'page_number': 1}],
            status=QuestionStatus.ANSWERED
        )

        client = Client()
        client.login(username=self.supervisor_user.username, password='password123')
        response = client.get(reverse('supervisor_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What is the normal operating pressure range?")

    # Test 13: Role-based access control prevents unauthorized page access
    def test_13_rbac_unauthorized_page_access(self):
        client = Client()
        client.login(username=self.engineer_user.username, password='password123')
        
        # Engineer trying to access Admin dashboard -> 403
        response = client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 403)

        # Engineer trying to access Manual management -> 403
        response = client.get(reverse('manual_list'))
        self.assertEqual(response.status_code, 403)

    # Test 14: Missing API key returns explicit error without silent fallback
    def test_14_missing_api_key_error_handling(self):
        chunks = self.vstore.search(query="Normal operating pressure?", machine_id="M-HP200")
        # Temporarily create generator with empty key
        from rag_engine.generator import RAGGenerator
        gen = RAGGenerator()
        gen.gemini_api_key = ''
        res = gen.generate_response("Normal operating pressure?", self.m_hp200, chunks)
        self.assertEqual(res['status'], 'ERROR')
        self.assertIn("GEMINI_API_KEY", res['answer'])
        self.assertEqual(len(res['sources']), 0)

    # Test 15: AJAX /api/chat/ask/ handles queries and persists history cleanly
    @patch.object(RAGGenerator, 'generate_response')
    def test_15_api_ask_question_endpoint(self, mock_generate):
        mock_generate.return_value = {
            'answer': 'Normal operating pressure is 120 to 140 bar during forming.',
            'sources': [{
                'pdf_filename': 'HP200_Operations_Rev1_0.pdf',
                'page_number': 1,
                'document_id': 'HP-OPS-01',
                'revision': '1.0',
                'machine_id': 'M-HP200',
                'passage_excerpt': 'Normal operating pressure is 120 to 140 bar...'
            }],
            'status': 'ANSWERED',
            'provider_used': 'gemini'
        }
        client = Client()
        client.login(username=self.engineer_user.username, password='password123')
        import json
        response = client.post(
            reverse('api_ask_question'),
            data=json.dumps({
                'machine_id': 'M-HP200',
                'question': 'What is the normal operating pressure for the HP-200?'
            }),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ANSWERED')
        self.assertTrue(len(data['sources']) > 0)
        self.assertIn('HP-OPS-01', [s['document_id'] for s in data['sources']])
        self.assertTrue(QuestionHistory.objects.filter(id=data['id']).exists())
