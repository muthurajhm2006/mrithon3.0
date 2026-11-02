from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .models import CustomUser

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')
        
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.username} ({user.get_role_display()})!")
            return redirect('dashboard_redirect')
        else:
            messages.error(request, "Invalid username or password. Please try again.")
            
    return render(request, 'accounts/login.html')

def quick_login_view(request, role):
    """
    Convenient helper for student challenge judges to log in instantly as any role.
    """
    role = role.upper()
    role_map = {
        'ADMIN': ('admin', 'admin123', CustomUser.Role.ADMIN),
        'ENGINEER': ('engineer', 'engineer123', CustomUser.Role.ENGINEER),
        'SUPERVISOR': ('supervisor', 'supervisor123', CustomUser.Role.SUPERVISOR),
    }
    
    if role in role_map:
        username, password, role_choice = role_map[role]
        user, created = CustomUser.objects.get_or_create(username=username, defaults={
            'role': role_choice,
            'is_staff': (role_choice == CustomUser.Role.ADMIN),
            'is_superuser': (role_choice == CustomUser.Role.ADMIN),
        })
        if created:
            user.set_password(password)
            user.save()
        else:
            if user.role != role_choice:
                user.role = role_choice
                user.save()
        login(request, user)
        messages.info(request, f"Logged in as demo {role} ({username})")
        return redirect('dashboard_redirect')
        
    messages.error(request, "Unknown role specified.")
    return redirect('login')

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('login')

@login_required
def dashboard_redirect(request):
    """Direct users to their primary dashboard based on role."""
    user = request.user
    if user.is_admin_role:
        return redirect('admin_dashboard')
    elif user.is_supervisor_role:
        return redirect('supervisor_dashboard')
    else:
        return redirect('engineer_chat')
