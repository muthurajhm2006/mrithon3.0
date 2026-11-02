from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.http import HttpResponseForbidden, JsonResponse

def role_required(allowed_roles):
    """
    Decorator to restrict view access to specific user roles.
    Raises 403 PermissionDenied or returns 403 response if role is disallowed.
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            user_role = getattr(request.user, 'role', None)
            
            # Superusers always have admin access
            if request.user.is_superuser and 'ADMIN' in allowed_roles:
                return view_func(request, *args, **kwargs)

            if user_role not in allowed_roles:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'Permission denied: Your role does not have permission to access this resource.',
                        'required_roles': allowed_roles,
                        'current_role': user_role
                    }, status=403)
                raise PermissionDenied("Access Denied: You do not have the required permissions for this page.")

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def admin_required(view_func):
    return role_required(['ADMIN'])(view_func)

def engineer_required(view_func):
    return role_required(['ENGINEER', 'ADMIN'])(view_func)

def supervisor_required(view_func):
    return role_required(['SUPERVISOR', 'ADMIN'])(view_func)
