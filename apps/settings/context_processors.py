from .models import PaymentSetting

def payment_settings_context(request):
    if getattr(request, 'user', None) and request.user.is_authenticated:
        gym = getattr(request, 'gym', None)
        if gym:
            try:
                payment_settings = PaymentSetting.objects.get(gym=gym)
            except PaymentSetting.DoesNotExist:
                payment_settings = None
        else:
            payment_settings = None
    else:
        payment_settings = None
    return {'payment_settings': payment_settings}