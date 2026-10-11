from functools import wraps
from django.shortcuts import redirect

def superadmin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_authenticated and (request.session.get('role') == 'superadmin' or request.user.is_superuser):
            return view_func(request, *args, **kwargs)
        else:
            return redirect('login')  # Redirect to login page if not superadmin
    return _wrapped_view