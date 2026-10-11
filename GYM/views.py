from django.shortcuts import render, redirect
from django.conf import settings

def handler404(request, exception):
    return render(request, '404.html', status=404)

def help_view(request):
    if request.user.is_authenticated:
        if request.session.get('role') == 'member' or hasattr(request.user, 'member_profile'):
            return redirect('member_portal:dashboard')
        if request.session.get('role') == 'trainer' or hasattr(request.user, 'trainer_profile'):
            return redirect('trainer_portal:dashboard')
    gym = getattr(request, 'gym', None)
    
    superadmin_phone = "+91 92059 83996"
    superadmin_email = "bhattsquare1@gmail.com"
    
    context = {
        'gym': gym,
        'superadmin_phone': superadmin_phone,
        'superadmin_email': superadmin_email,
    }
    return render(request, 'help.html', context)

def debug(request):
    whatsapp_config = {
        'WHATSAPP_ACCESS_TOKEN': getattr(settings, 'WHATSAPP_ACCESS_TOKEN', ''),
        'WHATSAPP_PHONE_NUMBER_ID': getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', ''),
        'WHATSAPP_VERIFY_TOKEN': getattr(settings, 'WHATSAPP_VERIFY_TOKEN', ''),
        'WHATSAPP_REGISTRATION_PIN': getattr(settings, 'WHATSAPP_REGISTRATION_PIN', ''),
        'WHATSAPP_API_VERSION': getattr(settings, 'WHATSAPP_API_VERSION', ''),
        'WHATSAPP_WEBHOOK_URL': getattr(settings, 'WHATSAPP_WEBHOOK_URL', ''),
        'WHATSAPP_BASE_URL': getattr(settings, 'WHATSAPP_BASE_URL', ''),
        'WHATSAPP_CLOUD_API_URL': getattr(settings, 'WHATSAPP_CLOUD_API_URL', ''),
        'WHATSAPP_APP_SECRET': getattr(settings, 'WHATSAPP_APP_SECRET', ''),
        'WHATSAPP_BUSINESS_ACCOUNT_ID': getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', ''),
        
        # Twilio (Active)
        'TWILIO_ACCOUNT_SID': getattr(settings, 'TWILIO_ACCOUNT_SID', ''),
        'TWILIO_WHATSAPP_NUMBER': getattr(settings, 'TWILIO_WHATSAPP_NUMBER', ''),
        'TWILIO_CONTENT_SID': getattr(settings, 'TWILIO_CONTENT_SID', ''),
        'TWILIO_AUTH_TOKEN_SET': bool(getattr(settings, 'TWILIO_AUTH_TOKEN', '') and settings.TWILIO_AUTH_TOKEN != 'YOUR_TWILIO_AUTH_TOKEN'),
    }
    context = {
        'whatsapp_config': whatsapp_config
    }
    return render(request, 'debug.html', context)

def sitemap_view(request):
    return render(request, 'sitemap.xml', content_type='application/xml')

def robots_view(request):
    return render(request, 'robots.txt', content_type='text/plain')