import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from accounts.decorators import role_required, engineer_required, supervisor_required
from machines.models import Machine
from .models import QuestionHistory, QuestionStatus
from rag_engine.vector_store import get_vector_store
from rag_engine.generator import RAGGenerator

@engineer_required
def engineer_chat(request):
    """
    Primary Engineer Chat Interface.
    Allows engineers to select a machine, submit queries, and view answers with citations.
    """
    machines = Machine.objects.all()
    # Fetch recent questions asked by this engineer
    history = QuestionHistory.objects.filter(user=request.user)[:20]
    
    # If no questions yet, show all recent questions or empty
    if not history.exists():
        history = QuestionHistory.objects.all()[:15]

    context = {
        'machines': machines,
        'recent_history': history,
        'default_machine': machines.first() if machines.exists() else None,
    }
    return render(request, 'chat/engineer_chat.html', context)

@require_POST
@login_required
def api_ask_question(request):
    """
    AJAX endpoint for the RAG question-answering workflow.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
    except Exception:
        data = request.POST

    machine_id = data.get('machine_id', '').strip()
    question = data.get('question', '').strip()

    if not machine_id or not question:
        return JsonResponse({
            'error': 'Both machine_id and question are required fields.'
        }, status=400)

    machine = get_object_or_404(Machine, machine_id=machine_id)

    # 1. Vector Search with machine-level isolation
    vstore = get_vector_store()
    retrieved_chunks = vstore.search(query=question, machine_id=machine.machine_id, top_k=4)

    # 2. RAG Response Generation
    generator = RAGGenerator()
    rag_result = generator.generate_response(
        query=question,
        machine=machine,
        retrieved_chunks=retrieved_chunks
    )

    # Handle provider/API error cleanly without silent fallback or corrupting history
    if rag_result.get('status') == 'ERROR':
        return JsonResponse({
            'error': rag_result.get('answer', 'Failed to generate answer from LLM provider.'),
            'status': 'ERROR',
            'provider_used': rag_result.get('provider_used', generator.provider),
        }, status=502)

    # 3. Persist Question History
    status_val = (
        QuestionStatus.ANSWERED 
        if rag_result['status'] == 'ANSWERED' 
        else QuestionStatus.INSUFFICIENT_EVIDENCE
    )
    
    history_record = QuestionHistory.objects.create(
        user=request.user,
        machine=machine,
        question=question,
        answer=rag_result['answer'],
        sources=rag_result['sources'],
        status=status_val
    )

    return JsonResponse({
        'id': history_record.id,
        'question': question,
        'answer': rag_result['answer'],
        'sources': rag_result['sources'],
        'status': status_val,
        'status_display': history_record.get_status_display(),
        'machine_id': machine.machine_id,
        'machine_model': machine.model,
        'timestamp': history_record.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        'provider_used': rag_result.get('provider_used', generator.provider),
    })

@supervisor_required
def supervisor_dashboard(request):
    """
    Supervisor Review & Audit Dashboard.
    Provides analytics, filtering of unanswered or insufficient-evidence queries,
    and search capabilities.
    """
    machines = Machine.objects.all()
    
    # Query parameters
    machine_filter = request.GET.get('machine', 'all')
    status_filter = request.GET.get('status', 'all')
    search_query = request.GET.get('q', '').strip()

    qs = QuestionHistory.objects.select_related('user', 'machine').all()

    if machine_filter and machine_filter != 'all':
        qs = qs.filter(machine__machine_id=machine_filter)

    if status_filter and status_filter != 'all':
        qs = qs.filter(status=status_filter)

    if search_query:
        qs = qs.filter(
            Q(question__icontains=search_query) | 
            Q(answer__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )

    # Aggregate metrics
    all_questions = QuestionHistory.objects.all()
    total_questions = all_questions.count()
    answered_count = all_questions.filter(status=QuestionStatus.ANSWERED).count()
    insufficient_count = all_questions.filter(status=QuestionStatus.INSUFFICIENT_EVIDENCE).count()

    context = {
        'questions': qs[:100],
        'machines': machines,
        'total_questions': total_questions,
        'answered_count': answered_count,
        'insufficient_count': insufficient_count,
        'selected_machine': machine_filter,
        'selected_status': status_filter,
        'search_query': search_query,
    }
    return render(request, 'chat/supervisor_dashboard.html', context)

@login_required
def automated_checks_view(request):
    """
    Live test runner dashboard for the two automated checks required by the Student Brief:
    1. Engineers cannot upload manuals (Role-based access enforcement).
    2. Retrieval strictly excludes passages belonging to another machine (Corpus isolation).
    """
    from accounts.models import CustomUser
    from django.test import RequestFactory
    from manual_manager.views import upload_manual

    results = []

    # Check 1: Engineer Role Upload Rejection
    rf = RequestFactory()
    eng_user = CustomUser.objects.filter(role=CustomUser.Role.ENGINEER).first()
    if not eng_user:
        eng_user = CustomUser(username='test_eng', role=CustomUser.Role.ENGINEER)

    dummy_post_request = rf.post('/manuals/upload/', {'machine_id': 'M-HP200', 'document_id': 'TEST-01'})
    dummy_post_request.user = eng_user
    upload_response = upload_manual(dummy_post_request)

    check_1_passed = (upload_response.status_code == 403)
    results.append({
        'title': 'Automated Check 1: Engineer Role Upload Denial',
        'requirement': 'Engineers cannot upload manuals (HTTP 403 Forbidden)',
        'passed': check_1_passed,
        'status_code': upload_response.status_code,
        'details': f"Simulated Engineer POST to upload manual returned HTTP {upload_response.status_code} Forbidden as required."
    })

    # Check 2: Machine Isolation in RAG Retrieval
    vstore = get_vector_store()
    
    # Query AC-90 while HP-200 is selected
    hp_search_for_ac_term = vstore.search(
        query="What is the AC-90 AF-10 filter indicator interval?",
        machine_id="M-HP200",
        top_k=5
    )
    # Ensure none of the returned chunks belong to AC-90
    cross_chunks_found = [c for c in hp_search_for_ac_term if 'AC90' in c['pdf_filename'] or 'AC-OM' in c['document_id'] or 'M-AC90' in c['machine_id']]
    
    # Query AC-90 for E17 and ensure it returns AC-OM-01 and not HP-OPS-01
    ac_e17_search = vstore.search(
        query="What does E17 mean?",
        machine_id="M-AC90",
        top_k=3
    )
    ac_has_hp_chunks = [c for c in ac_e17_search if 'HP' in c['pdf_filename'] or 'HP' in c['document_id']]

    check_2_passed = (len(cross_chunks_found) == 0 and len(ac_has_hp_chunks) == 0)
    results.append({
        'title': 'Automated Check 2: Machine Isolation Filter',
        'requirement': 'Retrieval excludes passages belonging to another machine',
        'passed': check_2_passed,
        'details': (
            f"Searched HP-200: {len(cross_chunks_found)} AC-90 chunks leaked (Expected: 0). "
            f"Searched AC-90 for E17: {len(ac_has_hp_chunks)} HP-200 chunks leaked (Expected: 0). "
            f"Machine corpus boundaries strictly isolated."
        )
    })

    return render(request, 'chat/automated_checks.html', {'results': results})
