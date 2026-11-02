def user_role_context(request):
    if not request.user.is_authenticated:
        return {
            'user_role': None,
            'is_admin_role': False,
            'is_engineer_role': False,
            'is_supervisor_role': False,
        }
    
    role = getattr(request.user, 'role', None)
    is_admin = role == 'ADMIN' or request.user.is_superuser
    is_engineer = role == 'ENGINEER'
    is_supervisor = role == 'SUPERVISOR'

    return {
        'user_role': role,
        'user_role_display': request.user.get_role_display() if hasattr(request.user, 'get_role_display') else role,
        'is_admin_role': is_admin,
        'is_engineer_role': is_engineer,
        'is_supervisor_role': is_supervisor,
    }
