import os
import csv
import shutil
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse, FileResponse
from django.views.decorators.http import require_POST
from accounts.decorators import admin_required
from machines.models import Machine
from .models import Manual
from rag_engine.extractor import PDFExtractor
from rag_engine.chunker import TextChunker
from rag_engine.vector_store import get_vector_store

def _index_manual_file(manual_instance, local_pdf_path):
    """Internal helper to extract, chunk, and index a manual PDF."""
    machine = manual_instance.machine
    
    # Extract pages page by page
    extracted_pages = PDFExtractor.extract_manual_pages(
        pdf_path=local_pdf_path,
        machine_id=machine.machine_id,
        machine_model=machine.model,
        document_id=manual_instance.document_id,
        revision=manual_instance.revision,
        pdf_filename=manual_instance.pdf_filename
    )
    
    # Chunk text
    chunker = TextChunker()
    chunks = chunker.chunk_pages(extracted_pages)
    
    # Add chunks to Vector Store
    vstore = get_vector_store()
    vstore.add_chunks(chunks)
    
    # Persist vector store to disk
    storage_dir = getattr(settings, 'RAG_CONFIG', {}).get('VECTOR_STORE_DIR', settings.BASE_DIR / 'vector_store_data')
    vstore.save(storage_dir)
    
    # Update manual instance
    manual_instance.page_count = len(extracted_pages)
    manual_instance.total_chunks = len(chunks)
    manual_instance.is_indexed = True
    manual_instance.save()
    
    return len(extracted_pages), len(chunks)

def manual_list(request):
    """Manual Management View."""
    # Check permissions
    if not request.user.is_authenticated or not request.user.is_admin_role:
        return HttpResponseForbidden("Access Denied: Only Administrators can access Manual Management.")

    manuals = Manual.objects.all().select_related('machine')
    machines = Machine.objects.all()
    return render(request, 'manual_manager/manual_list.html', {
        'manuals': manuals,
        'machines': machines,
    })

def upload_manual(request):
    """
    Handle Manual PDF Upload.
    Enforces server-side role check: Only Administrators can upload manuals.
    Non-admin users receive HTTP 403 Forbidden.
    """
    if not request.user.is_authenticated or not request.user.is_admin_role:
        return HttpResponseForbidden("Permission Denied: Only Administrators are authorized to upload manuals.")

    if request.method == 'POST':
        machine_id = request.POST.get('machine_id', '').strip()
        document_id = request.POST.get('document_id', '').strip()
        revision = request.POST.get('revision', '1.0').strip()
        title = request.POST.get('title', '').strip()
        pdf_file = request.FILES.get('pdf_file')

        if not machine_id or not document_id or not pdf_file:
            messages.error(request, "Machine, Document ID, and PDF file are required.")
            return redirect('manual_list')

        # Validate file extension
        if not pdf_file.name.lower().endswith('.pdf'):
            messages.error(request, "Validation Error: Only PDF files (.pdf) are permitted.")
            return redirect('manual_list')

        # Validate size (max 25MB)
        if pdf_file.size > 25 * 1024 * 1024:
            messages.error(request, "Validation Error: File size exceeds the 25MB limit.")
            return redirect('manual_list')

        machine = get_object_or_404(Machine, machine_id=machine_id)
        if not title:
            title = f"{machine.model} Manual ({document_id})"

        # Create or update manual record
        manual, created = Manual.objects.get_or_create(
            machine=machine,
            document_id=document_id,
            revision=revision,
            defaults={
                'title': title,
                'pdf_filename': pdf_file.name,
                'pdf_file': pdf_file,
            }
        )

        if not created:
            manual.title = title
            manual.pdf_filename = pdf_file.name
            manual.pdf_file = pdf_file
            manual.save()

        # Extract and Index
        try:
            pages_count, chunks_count = _index_manual_file(manual, manual.pdf_file.path)
            messages.success(
                request,
                f"Manual '{manual.document_id}' uploaded and indexed successfully! "
                f"({pages_count} pages extracted, {chunks_count} passages vectorized)."
            )
        except Exception as e:
            messages.error(request, f"Error processing PDF: {str(e)}")

        return redirect('manual_list')

    return redirect('manual_list')

@admin_required
def sync_supplied_manuals(request):
    """
    Import and index the three official PDF files from the Manuals folder
    using machine_manual_index.csv as metadata source of truth.
    """
    csv_path = settings.BASE_DIR / 'machine_manual_index.csv'
    manuals_dir = settings.BASE_DIR / 'Manuals'
    media_manuals_dir = settings.MEDIA_ROOT / 'manuals_uploaded'
    os.makedirs(media_manuals_dir, exist_ok=True)

    if not os.path.exists(csv_path) or not os.path.exists(manuals_dir):
        messages.error(request, "Official CSV or Manuals directory not found.")
        return redirect('manual_list')

    indexed_count = 0
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            m_id = row['machine_id'].strip()
            m_model = row['model'].strip()
            m_name = row['machine_name'].strip()
            doc_id = row['document_id'].strip()
            rev = row['revision'].strip()
            pdf_filename = row['pdf_filename'].strip()

            source_pdf = manuals_dir / pdf_filename
            if not os.path.exists(source_pdf):
                continue

            machine, _ = Machine.objects.get_or_create(
                machine_id=m_id,
                defaults={'model': m_model, 'machine_name': m_name}
            )

            # Copy to media folder
            target_path = media_manuals_dir / pdf_filename
            shutil.copyfile(source_pdf, target_path)

            title_map = {
                'HP200_Operations_Rev1_0.pdf': 'HP 200 Operations Manual',
                'HP200_Maintenance_Rev1_0.pdf': 'HP 200 Maintenance Manual',
                'AC90_Operations_Maintenance_Rev1_0.pdf': 'AC 90 Operations and Maintenance Manual',
            }

            manual, created = Manual.objects.get_or_create(
                machine=machine,
                document_id=doc_id,
                revision=rev,
                defaults={
                    'title': title_map.get(pdf_filename, f"{m_model} Manual {doc_id}"),
                    'pdf_filename': pdf_filename,
                    'pdf_file': f'manuals_uploaded/{pdf_filename}',
                }
            )
            if not created:
                manual.pdf_filename = pdf_filename
                manual.pdf_file = f'manuals_uploaded/{pdf_filename}'
                manual.save()

            _index_manual_file(manual, str(source_pdf))
            indexed_count += 1

    messages.success(request, f"Successfully indexed {indexed_count} supplied manuals into the RAG vector store.")
    return redirect('manual_list')

def view_manual_pdf(request, filename):
    """
    Serve manual PDF directly for viewing in browser.
    Supports native browser page linking, e.g. /media/manuals_uploaded/<filename>#page=N
    """
    media_path = settings.MEDIA_ROOT / 'manuals_uploaded' / filename
    if not os.path.exists(media_path):
        # Fallback to Manuals folder
        manuals_path = settings.BASE_DIR / 'Manuals' / filename
        if os.path.exists(manuals_path):
            return FileResponse(open(manuals_path, 'rb'), content_type='application/pdf')
        return HttpResponse("File not found", status=404)
        
    return FileResponse(open(media_path, 'rb'), content_type='application/pdf')

def view_page_preview(request, filename, page_number):
    """
    Renders and serves a PNG image preview of the exact cited PDF page.
    Allows engineers to see the cited page inside a modal dialog immediately!
    """
    # Locate PDF
    pdf_path = settings.MEDIA_ROOT / 'manuals_uploaded' / filename
    if not os.path.exists(pdf_path):
        pdf_path = settings.BASE_DIR / 'Manuals' / filename
        
    if not os.path.exists(pdf_path):
        return HttpResponse("Manual not found", status=404)

    preview_cache_dir = settings.MEDIA_ROOT / 'page_previews'
    os.makedirs(preview_cache_dir, exist_ok=True)
    img_filename = f"{filename}_page_{page_number}.png"
    img_path = str(preview_cache_dir / img_filename)

    if not os.path.exists(img_path):
        PDFExtractor.render_page_image(str(pdf_path), int(page_number), img_path)

    if os.path.exists(img_path):
        return FileResponse(open(img_path, 'rb'), content_type='image/png')
    return HttpResponse("Could not render page preview", status=500)
