import os
import shutil
import csv
from django.core.management.base import BaseCommand
from django.conf import settings
from accounts.models import CustomUser
from machines.models import Machine
from manual_manager.models import Manual
from manual_manager.views import _index_manual_file

class Command(BaseCommand):
    help = "Initializes demo users, imports machines from CSV, and indexes the 3 official PDF manuals."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("=== Initializing Manufacturing Manual Assistant ==="))

        # 1. Create Demo Users
        users_data = [
            ('admin', 'admin123', CustomUser.Role.ADMIN, True, True),
            ('engineer', 'engineer123', CustomUser.Role.ENGINEER, False, False),
            ('supervisor', 'supervisor123', CustomUser.Role.SUPERVISOR, False, False),
        ]

        for username, password, role, is_staff, is_superuser in users_data:
            user, created = CustomUser.objects.get_or_create(username=username, defaults={
                'role': role,
                'is_staff': is_staff,
                'is_superuser': is_superuser
            })
            user.set_password(password)
            user.role = role
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.save()
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"  [User] {action} {username} ({role})"))

        # 2. Register Machines from CSV
        csv_path = settings.BASE_DIR / 'machine_manual_index.csv'
        if not os.path.exists(csv_path):
            self.stdout.write(self.style.ERROR(f"Error: {csv_path} not found!"))
            return

        machines_created = 0
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                m_id = row['machine_id'].strip()
                m_model = row['model'].strip()
                m_name = row['machine_name'].strip()
                
                m, created = Machine.objects.get_or_create(
                    machine_id=m_id,
                    defaults={'model': m_model, 'machine_name': m_name}
                )
                if created:
                    machines_created += 1

        self.stdout.write(self.style.SUCCESS(f"  [Machines] Synchronized machine registry from CSV ({Machine.objects.count()} machines active)"))

        # 3. Index Supplied PDF Manuals
        manuals_dir = settings.BASE_DIR / 'Manuals'
        media_manuals_dir = settings.MEDIA_ROOT / 'manuals_uploaded'
        os.makedirs(media_manuals_dir, exist_ok=True)

        indexed_manuals = 0
        total_pages = 0
        total_passages = 0

        title_map = {
            'HP200_Operations_Rev1_0.pdf': 'HP 200 Operations Manual',
            'HP200_Maintenance_Rev1_0.pdf': 'HP 200 Maintenance Manual',
            'AC90_Operations_Maintenance_Rev1_0.pdf': 'AC 90 Operations and Maintenance Manual',
        }

        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                m_id = row['machine_id'].strip()
                m_model = row['model'].strip()
                doc_id = row['document_id'].strip()
                rev = row['revision'].strip()
                pdf_filename = row['pdf_filename'].strip()

                source_pdf = manuals_dir / pdf_filename
                if not os.path.exists(source_pdf):
                    self.stdout.write(self.style.WARNING(f"  [Warning] Missing PDF file: {source_pdf}"))
                    continue

                machine = Machine.objects.get(machine_id=m_id)
                target_path = media_manuals_dir / pdf_filename
                shutil.copyfile(source_pdf, target_path)

                manual, _ = Manual.objects.get_or_create(
                    machine=machine,
                    document_id=doc_id,
                    revision=rev,
                    defaults={
                        'title': title_map.get(pdf_filename, f"{m_model} Manual {doc_id}"),
                        'pdf_filename': pdf_filename,
                        'pdf_file': f'manuals_uploaded/{pdf_filename}',
                    }
                )

                manual.pdf_filename = pdf_filename
                manual.pdf_file = f'manuals_uploaded/{pdf_filename}'
                manual.save()

                p_count, c_count = _index_manual_file(manual, str(source_pdf))
                total_pages += p_count
                total_passages += c_count
                indexed_manuals += 1
                self.stdout.write(self.style.SUCCESS(f"  [Manual Indexed] {doc_id} Rev {rev} ({pdf_filename}): {p_count} pages, {c_count} passages vectorized."))

        self.stdout.write(self.style.SUCCESS(f"\nSUCCESS: Indexed {indexed_manuals} manuals ({total_pages} total pages, {total_passages} total passages)."))
        self.stdout.write(self.style.SUCCESS("Demo accounts ready: admin/admin123, engineer/engineer123, supervisor/supervisor123"))
