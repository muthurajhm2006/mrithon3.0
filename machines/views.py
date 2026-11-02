import os
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from accounts.decorators import admin_required, role_required
from .models import Machine
from manual_manager.models import Manual
from chat.models import QuestionHistory

@admin_required
def admin_dashboard(request):
    """Admin Dashboard with system metrics and quick action shortcuts."""
    machines = Machine.objects.all()
    manuals = Manual.objects.all().select_related('machine')
    total_machines = machines.count()
    total_manuals = manuals.count()
    total_indexed_chunks = sum(m.total_chunks for m in manuals)
    total_questions = QuestionHistory.objects.count()
    
    context = {
        'total_machines': total_machines,
        'total_manuals': total_manuals,
        'total_indexed_chunks': total_indexed_chunks,
        'total_questions': total_questions,
        'machines': machines,
        'manuals': manuals,
    }
    return render(request, 'machines/admin_dashboard.html', context)

@admin_required
def machine_list(request):
    """Machine Management Page: view list, register new machine, sync from CSV."""
    if request.method == 'POST':
        machine_id = request.POST.get('machine_id', '').strip()
        model = request.POST.get('model', '').strip()
        machine_name = request.POST.get('machine_name', '').strip()
        description = request.POST.get('description', '').strip()

        if not machine_id or not model or not machine_name:
            messages.error(request, "Machine ID, Model, and Machine Name are required fields.")
        else:
            machine, created = Machine.objects.get_or_create(
                machine_id=machine_id,
                defaults={
                    'model': model,
                    'machine_name': machine_name,
                    'description': description
                }
            )
            if not created:
                machine.model = model
                machine.machine_name = machine_name
                machine.description = description
                machine.save()
                messages.success(request, f"Machine '{machine.model}' ({machine.machine_id}) updated successfully.")
            else:
                messages.success(request, f"Machine '{machine.model}' ({machine.machine_id}) registered successfully.")
        return redirect('machine_list')

    machines = Machine.objects.all()
    return render(request, 'machines/machine_list.html', {'machines': machines})

@admin_required
def sync_csv_metadata(request):
    """
    Reads machine_manual_index.csv as the source of truth to register machines.
    """
    csv_path = settings.BASE_DIR / 'machine_manual_index.csv'
    if not os.path.exists(csv_path):
        messages.error(request, f"File machine_manual_index.csv not found at {csv_path}")
        return redirect('machine_list')

    created_count = 0
    updated_count = 0
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            m_id = row['machine_id'].strip()
            m_model = row['model'].strip()
            m_name = row['machine_name'].strip()
            
            machine, created = Machine.objects.get_or_create(
                machine_id=m_id,
                defaults={
                    'model': m_model,
                    'machine_name': m_name,
                    'description': f"Official training record from metadata CSV for {m_name}"
                }
            )
            if created:
                created_count += 1
            else:
                machine.model = m_model
                machine.machine_name = m_name
                machine.save()
                updated_count += 1

    messages.success(request, f"Metadata sync complete: {created_count} machines added, {updated_count} verified from CSV.")
    return redirect('machine_list')

def api_machine_list(request):
    """API endpoint to get active machines for dropdowns."""
    machines = list(Machine.objects.values('machine_id', 'model', 'machine_name', 'description'))
    return JsonResponse({'machines': machines})
