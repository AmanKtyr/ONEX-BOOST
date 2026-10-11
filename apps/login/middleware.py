from django.shortcuts import redirect
from django.urls import reverse
from apps.superadmin.models import GymAdmin

class PasswordResetMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if user is authenticated, not a superuser, and not already on the reset page
        if request.user.is_authenticated and not request.user.is_superuser and request.path != reverse('password_reset_page'):
            try:
                gym_admin = request.user.gymadmin
                if gym_admin.gym.password_reset_required:
                    # Redirect to the password reset page
                    return redirect('password_reset_page')
            except GymAdmin.DoesNotExist:
                # This can happen if the user is not a gym admin
                pass
        
        response = self.get_response(request)
        return response