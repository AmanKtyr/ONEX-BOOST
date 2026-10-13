from django.shortcuts import render, redirect
from django.views.generic import TemplateView, View
from .models import PaymentSetting
from .forms import PaymentSettingForm
from apps.superadmin.models import Gym
from apps.superadmin.forms import GymForm
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from apps.login.decorators import custom_permission_required

class generalsetting(TemplateView):
    template_name = "settings/general_settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        gym = getattr(self.request, 'gym', None)
        context['gym'] = gym
        if gym:
            context['form'] = GymForm(instance=gym)
        return context

    def post(self, request, *args, **kwargs):
        gym = getattr(request, 'gym', None)
        if not gym:
            # Handle case where gym is not found
            messages.error(request, 'Gym not found.')
            return redirect('settings:general_settings')

        form = GymForm(request.POST, request.FILES, instance=gym)
        if form.is_valid():
            form.save()
            messages.success(request, 'General settings saved successfully.')
            return redirect('settings:gym_profile')

        context = self.get_context_data(**kwargs)
        context['form'] = form
        return self.render_to_response(context)

@method_decorator(custom_permission_required('change_paymentsetting'), name='dispatch')
class PaymentSettingView(LoginRequiredMixin, View):
    template_name = 'settings/payment_setting.html'

    def get(self, request, *args, **kwargs):
        gym = request.gym
        payment_settings, created = PaymentSetting.objects.get_or_create(gym=gym)
        form = PaymentSettingForm(instance=payment_settings)
        return render(request, self.template_name, {'form': form, 'payment_settings': payment_settings})

    def post(self, request, *args, **kwargs):
        gym = request.gym
        payment_settings, created = PaymentSetting.objects.get_or_create(gym=gym)
        form = PaymentSettingForm(request.POST, request.FILES, instance=payment_settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Payment settings saved successfully.')
            return redirect('settings:payment_setting')
        return render(request, self.template_name, {'form': form, 'payment_settings': payment_settings})

@method_decorator(custom_permission_required('change_paymentsetting'), name='dispatch')
class GymProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'settings/gym_profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['gym'] = getattr(self.request, 'gym', None)
        return context


from urllib.parse import quote
from apps.superadmin.models import SubscriptionPlan, SaaSUpgradeRequest, PlatformNotification, SystemSetting
from apps.superadmin.subscription_utils import get_gym_quota_status
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


@login_required(login_url='login')
def my_subscription_view(request):
    gym = getattr(request, 'gym', None)
    if not gym:
        messages.error(request, "No active gym associated with your account.")
        return redirect('dashboard')

    quota_status = get_gym_quota_status(gym)
    available_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price')
    recent_requests = SaaSUpgradeRequest.objects.filter(gym=gym).select_related('current_plan', 'target_plan').order_by('-created_at')[:5]

    context = {
        'gym': gym,
        'quota': quota_status,
        'available_plans': available_plans,
        'recent_requests': recent_requests,
        'support_phone': quota_status.get('support_phone', '+91 88875 58415') if quota_status else '+91 88875 58415',
    }
    return render(request, 'settings/my_subscription.html', context)


@login_required(login_url='login')
def request_plan_upgrade(request):
    if request.method != 'POST':
        return redirect('settings:my_subscription')

    gym = getattr(request, 'gym', None)
    if not gym:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': 'No gym found.'}, status=400)
        messages.error(request, 'No gym found.')
        return redirect('dashboard')

    quota_status = get_gym_quota_status(gym)
    target_plan_id = request.POST.get('target_plan_id')
    contact_phone = request.POST.get('contact_phone', '').strip() or gym.phone
    reason = request.POST.get('reason', 'Quota Limit Reached').strip()
    user_note = request.POST.get('notes', '').strip()

    target_plan = None
    if target_plan_id:
        target_plan = SubscriptionPlan.objects.filter(id=target_plan_id, is_active=True).first()

    current_plan = quota_status.get('plan') if quota_status else None
    target_plan_name = target_plan.name if target_plan else 'Custom Upgrade Plan'
    curr_name = current_plan.name if current_plan else 'Standard'

    # Create the upgrade request lead
    SaaSUpgradeRequest.objects.create(
        gym=gym,
        requested_by=request.user,
        current_plan=current_plan,
        target_plan=target_plan,
        contact_phone=contact_phone,
        reason=reason,
        message=user_note,
        status='pending'
    )

    # Notify Superadmin via PlatformNotification
    try:
        PlatformNotification.objects.create(
            title=f"🚀 Upgrade Request: {gym.name}",
            message=f"{gym.name} ({gym.gym_id}) requested an upgrade from {curr_name} to {target_plan_name}. Contact: {contact_phone}. Note: {user_note or reason}",
            notification_type='info',
            target_type='all',
            action_label='Manage Gyms',
            action_url='/superadmin/gym_list'
        )
    except Exception:
        pass

    # Build direct WhatsApp URL for SuperAdmin
    setting = SystemSetting.get_settings()
    clean_phone = ''.join(filter(str.isdigit, setting.support_phone or "918887558415"))
    if not clean_phone.startswith('91') and len(clean_phone) == 10:
        clean_phone = '91' + clean_phone
    wa_text = (
        f"Hello ONEX BOOST Team, I want to upgrade the SaaS subscription plan for our gym *{gym.name}* (ID: {gym.gym_id}).\n"
        f"Current Plan: *{curr_name}*\n"
        f"Requested Plan: *{target_plan_name}*\n"
        f"Contact: {contact_phone}\n"
        f"Please share the upgrade details."
    )
    wa_url = f"https://wa.me/{clean_phone}?text={quote(wa_text)}"

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': f"Upgrade request for '{target_plan_name}' submitted successfully!",
            'wa_url': wa_url,
        })

    messages.success(request, f"Your request to upgrade to '{target_plan_name}' has been submitted. Our team will contact you shortly!")
    return redirect('settings:my_subscription')
