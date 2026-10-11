from functools import wraps
from urllib.parse import urlparse
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from apps.login.models import SubAdminPermission

def custom_permission_required(perm_name):
    """
    Decorator to check if a subadmin has the required permission.
    GymAdmins and superusers are allowed automatically.
    If permission is denied for a SubAdmin, adds a professional SweetAlert
    warning message and safely redirects.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect('login')
                
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
                
            if hasattr(user, 'gymadmin'):
                return view_func(request, *args, **kwargs)
                
            if hasattr(user, 'subadmin'):
                if isinstance(perm_name, (list, tuple)):
                    has_perm = SubAdminPermission.objects.filter(
                        sub_admin=user.subadmin, 
                        permission_name__in=perm_name
                    ).exists()
                    readable_perm = ", ".join(p.replace('_', ' ').title() for p in perm_name)
                else:
                    has_perm = SubAdminPermission.objects.filter(
                        sub_admin=user.subadmin, 
                        permission_name=perm_name
                    ).exists()
                    readable_perm = perm_name.replace('_', ' ').title()
                    
                if has_perm:
                    return view_func(request, *args, **kwargs)
                else:
                    # Return 403 JSON for AJAX/fetch calls
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                        return JsonResponse({
                            'status': 'error',
                            'permission_denied': True,
                            'message': f'Access Denied: You do not have permission ({readable_perm}).'
                        }, status=403)

                    # SweetAlert warning message with permission_denied tag
                    messages.warning(
                        request,
                        f'You do not have the required operational privileges to access this section ({readable_perm}). Please contact your Gym Administrator if you require access.',
                        extra_tags='permission_denied'
                    )

                    # Safe redirect back to referring page or dashboard
                    referer = request.META.get('HTTP_REFERER')
                    if referer and referer != request.build_absolute_uri():
                        ref_host = urlparse(referer).netloc
                        req_host = request.get_host()
                        if ref_host == req_host:
                            return redirect(referer)
                    return redirect('dashboard')
                    
            # If the user has no known role
            return redirect('login')
            
        return _wrapped_view
    return decorator
