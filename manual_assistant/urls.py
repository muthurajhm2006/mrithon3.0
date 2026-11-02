"""
URL configuration for manual_assistant project.
"""

from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

import accounts.views as account_views
import machines.views as machine_views
import manual_manager.views as manual_views
import chat.views as chat_views

urlpatterns = [
    # Root redirect
    path('', lambda request: redirect('dashboard_redirect'), name='root'),

    # Django built-in admin
    path('django-admin/', admin.site.urls),

    # Authentication
    path('login/', account_views.login_view, name='login'),
    path('logout/', account_views.logout_view, name='logout'),
    path('quick-login/<str:role>/', account_views.quick_login_view, name='quick_login'),
    path('dashboard/', account_views.dashboard_redirect, name='dashboard_redirect'),

    # Admin Dashboard & Machine Management
    path('admin-dashboard/', machine_views.admin_dashboard, name='admin_dashboard'),
    path('machines/', machine_views.machine_list, name='machine_list'),
    path('machines/sync-csv/', machine_views.sync_csv_metadata, name='sync_csv_metadata'),
    path('api/machines/', machine_views.api_machine_list, name='api_machine_list'),

    # Manual Management
    path('manuals/', manual_views.manual_list, name='manual_list'),
    path('manuals/upload/', manual_views.upload_manual, name='upload_manual'),
    path('manuals/sync-supplied/', manual_views.sync_supplied_manuals, name='sync_supplied_manuals'),
    path('manuals/pdf/<str:filename>/', manual_views.view_manual_pdf, name='view_manual_pdf'),
    path('manuals/preview/<str:filename>/<int:page_number>/', manual_views.view_page_preview, name='view_page_preview'),

    # Engineer Chat Interface
    path('chat/', chat_views.engineer_chat, name='engineer_chat'),
    path('api/chat/ask/', chat_views.api_ask_question, name='api_ask_question'),

    # Supervisor Review Dashboard
    path('supervisor/', chat_views.supervisor_dashboard, name='supervisor_dashboard'),

    # Automated Checks Dashboard
    path('automated-checks/', chat_views.automated_checks_view, name='automated_checks'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
