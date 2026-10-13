import os
import csv
import json
from decimal import Decimal
from datetime import date, datetime, timedelta

from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import models, transaction
from django.db.models import Q, Sum, F, Count, Value
from django.db.models.functions import Concat
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.mail import EmailMessage, get_connection
from apps.website.models import WebsiteContactSubmission
from .forms import GymForm, GymAdminForm, SubscriptionPlanForm
from .models import (
    Gym, GymAdmin, SubscriptionPlan, GymSubscription,
    PlatformNotification, NotificationUserStatus,
    SystemSetting, BackupLog, SaaSUpgradeRequest
)
from . import backup_service
from . import email_service
from .email_service import (
    send_gym_welcome_email,
    send_gym_admin_credentials_email,
    send_password_reset_email
)
from .decorators import superadmin_required
from .notifications import (
    get_user_applicable_notifications_qs,
    get_active_popup_for_user,
    acknowledge_popup,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    estimate_audience,
)
from apps.members.models import Member, MembershipHistory
from apps.trainers.models import Trainer
from apps.billing.models import Payment

@login_required
@superadmin_required
def invoice_view(request, subscription_id):
    subscription = get_object_or_404(
        GymSubscription.objects.select_related('gym', 'subscription'),
        id=subscription_id
    )
    return render(request, 'superadmin/invoice.html', {'subscription': subscription})

@login_required
@superadmin_required
def toggle_gym_freeze(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    gym.is_frozen = not gym.is_frozen
    gym.save()
    messages.success(request, f"Gym '{gym.name}' has been {'frozen' if gym.is_frozen else 'unfrozen'}.")
    return redirect('superadmin:gym_profile', gym_id=gym.id)

@login_required
@superadmin_required
def toggle_whatsapp(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    gym.whatsapp_enabled = not gym.whatsapp_enabled
    gym.save()
    status = 'enabled' if gym.whatsapp_enabled else 'disabled'
    messages.success(request, f"WhatsApp messaging for '{gym.name}' has been {status}.")
    return redirect('superadmin:gym_profile', gym_id=gym.id)

@login_required
@superadmin_required
def dashboard(request):
    total_gyms = Gym.objects.count()
    active_gyms = Gym.objects.filter(is_frozen=False).count()
    frozen_gyms = Gym.objects.filter(is_frozen=True).count()
    total_members = Member.objects.filter(is_deleted=False).count()

    today = timezone.now().date()
    subscriptions = GymSubscription.objects.filter(is_deleted=False)
    
    # Financial metrics for Superadmin
    total_sub_revenue = subscriptions.aggregate(Sum('paid_amount'))['paid_amount__sum'] or Decimal('0.00')
    total_due_payment_rev = Payment.objects.filter(member__isnull=True, is_deleted=False).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_platform_revenue = total_sub_revenue + total_due_payment_rev

    due_agg = subscriptions.aggregate(
        total=Sum('total_amount'),
        paid=Sum('paid_amount')
    )
    total_due_amount = (due_agg['total'] or Decimal('0.00')) - (due_agg['paid'] or Decimal('0.00'))

    # Active gym subscriptions (SaaS plans)
    active_gym_subscriptions = subscriptions.filter(start_date__lte=today, end_date__gte=today).count()
    
    # Subscriptions expiring soon (within next 15 days)
    upcoming_limit = today + timedelta(days=15)
    expiring_soon_subscriptions = subscriptions.filter(
        end_date__gte=today,
        end_date__lte=upcoming_limit
    ).select_related('gym', 'subscription').order_by('end_date')

    # Expired subscriptions
    expired_subscriptions = subscriptions.filter(end_date__lt=today).select_related('gym', 'subscription').order_by('-end_date')[:5]

    # Recent gym payments to Superadmin
    sub_payments = list(subscriptions.filter(paid_amount__gt=0).select_related('gym', 'subscription'))
    platform_due_payments = list(Payment.objects.filter(member__isnull=True, is_deleted=False).select_related('gym'))
    recent_transactions = sorted(
        sub_payments + platform_due_payments,
        key=lambda item: item.start_date if isinstance(item, GymSubscription) else item.payment_date.date(),
        reverse=True
    )[:8]

    # Website inquiries
    recent_inquiries = WebsiteContactSubmission.objects.order_by('-created_at')[:5]
    unread_inquiries_count = WebsiteContactSubmission.objects.filter(is_read=False).count()

    # 6-Month Monthly Revenue Analytics for Chart.js
    months_labels = []
    revenue_chart_data = []
    current_date = today.replace(day=1)
    for i in range(5, -1, -1):
        m_year = current_date.year
        m_month = current_date.month - i
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        m_start = date(m_year, m_month, 1)
        if m_month == 12:
            m_end = date(m_year + 1, 1, 1) - timedelta(days=1)
        else:
            m_end = date(m_year, m_month + 1, 1) - timedelta(days=1)
        months_labels.append(m_start.strftime("%b %Y"))

        m_sub = GymSubscription.objects.filter(
            start_date__gte=m_start, 
            start_date__lte=m_end,
            is_deleted=False
        ).aggregate(s=Sum('paid_amount'))['s'] or Decimal('0.00')

        m_due = Payment.objects.filter(
            member__isnull=True, 
            is_deleted=False, 
            payment_date__gte=m_start, 
            payment_date__lte=m_end
        ).aggregate(s=Sum('amount'))['s'] or Decimal('0.00')

        revenue_chart_data.append(float(m_sub + m_due))

    # Plan Tier Distribution for Doughnut Chart
    active_subs_by_plan = GymSubscription.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        is_deleted=False
    ).values('subscription__name').annotate(count=Count('id')).order_by('-count')

    plan_dist_labels = [item['subscription__name'] or 'Custom Plan' for item in active_subs_by_plan]
    plan_dist_counts = [item['count'] for item in active_subs_by_plan]

    if not plan_dist_labels:
        plan_dist_labels = ['No Active Subscriptions']
        plan_dist_counts = [0]

    pending_upgrade_requests = SaaSUpgradeRequest.objects.filter(status='pending').select_related('gym', 'current_plan', 'target_plan').order_by('-created_at')

    context = {
        'total_gyms': total_gyms,
        'active_gyms': active_gyms,
        'frozen_gyms': frozen_gyms,
        'total_members': total_members,
        'total_platform_revenue': total_platform_revenue,
        'total_due_amount': total_due_amount,
        'active_gym_subscriptions': active_gym_subscriptions,
        'expiring_soon_subscriptions': expiring_soon_subscriptions,
        'expired_subscriptions': expired_subscriptions,
        'recent_transactions': recent_transactions,
        'recent_inquiries': recent_inquiries,
        'unread_inquiries_count': unread_inquiries_count,
        'pending_upgrade_requests': pending_upgrade_requests,
        'pending_upgrade_count': pending_upgrade_requests.count(),
        'months_labels_json': json.dumps(months_labels),
        'revenue_chart_data_json': json.dumps(revenue_chart_data),
        'plan_dist_labels_json': json.dumps(plan_dist_labels),
        'plan_dist_counts_json': json.dumps(plan_dist_counts),
    }
    return render(request, 'superadmin/dashboard.html', context)


@login_required
@superadmin_required
def add_gym(request):
    if request.method == 'POST':
        form = GymForm(request.POST, request.FILES)
        if form.is_valid():
            gym = form.save(commit=False)
            
            # Handle GST fields
            gst_enabled = form.cleaned_data.get('gst_enabled', False)
            if gst_enabled:
                gym.gst_enabled = True
                gym.gst_rate = form.cleaned_data.get('gst_rate')
                gym.gst_number = form.cleaned_data.get('gst_number')
            else:
                gym.gst_enabled = False
                gym.gst_rate = None
                gym.gst_number = None

            gym.save()

            # Dispatch welcome onboarding email
            if gym.email:
                email_sent, _ = send_gym_welcome_email(gym, request=request)
                if email_sent:
                    messages.success(request, f"Gym '{gym.name}' has been added successfully. Onboarding welcome email sent to {gym.email}.")
                else:
                    messages.success(request, f"Gym '{gym.name}' has been added successfully.")
            else:
                messages.success(request, f"Gym '{gym.name}' has been added successfully.")

            return redirect('superadmin:create_gym_admin', gym_id=gym.id)
    else:
        initial_data = {}
        if request.GET.get('name'):
            initial_data['name'] = request.GET.get('name')
        if request.GET.get('phone'):
            initial_data['phone'] = request.GET.get('phone')
        if request.GET.get('email'):
            initial_data['email'] = request.GET.get('email')
        form = GymForm(initial=initial_data)
    return render(request, 'superadmin/add_gym.html', {'form': form, 'page_title': 'Add Gym', 'button_text': 'Add Gym'})


@login_required
@superadmin_required
def create_gym_admin(request, gym_id):
    gym = get_object_or_404(Gym, id=gym_id)
    if request.method == 'POST':
        form = GymAdminForm(request.POST, request.FILES)
        if form.is_valid():
            raw_password = form.cleaned_data.get('password')
            user = form.save()
            user.is_staff = True
            user.save()

            gym_admin = GymAdmin.objects.create(
                user=user,
                gym=gym,
                name=form.cleaned_data['name'],
                Phone_number=form.cleaned_data['Phone_number'],
                Department=form.cleaned_data.get('Department'),
                notes=form.cleaned_data.get('notes')
            )

            if 'photo' in request.FILES:
                gym_admin.photo = request.FILES['photo']
                gym_admin.save()

            # Dispatch credentials email to new gym administrator
            if user.email and raw_password:
                email_sent, _ = send_gym_admin_credentials_email(gym_admin, raw_password, request=request)
                if email_sent:
                    messages.success(request, f"Admin for '{gym.name}' has been created successfully. Login credentials emailed to {user.email}.")
                else:
                    messages.success(request, f"Admin for '{gym.name}' has been created successfully.")
            else:
                messages.success(request, f"Admin for '{gym.name}' has been created successfully.")

            return redirect('superadmin:gym_list')
    else:
        form = GymAdminForm()
    return render(request, 'superadmin/create_gym_admin.html', {'form': form, 'gym': gym})



@login_required
@superadmin_required
def gym_list(request):
    query = request.GET.get('q')
    status_filter = request.GET.get('status')
    
    gyms_qs = Gym.objects.all().order_by('-id')
    if query:
        gyms_qs = gyms_qs.filter(
            Q(name__icontains=query) |
            Q(gym_id__icontains=query) |
            Q(address__icontains=query) |
            Q(city__icontains=query) |
            Q(phone__icontains=query)
        ).distinct()

    today = timezone.now().date()
    gym_items = []
    total_active_count = 0
    total_expired_count = 0
    total_expiring_soon_count = 0
    total_frozen_count = 0

    for gym in gyms_qs:
        admin = GymAdmin.objects.filter(gym=gym).first()
        gym.has_admin = bool(admin)
        gym.admin_name = f"{admin.user.first_name} {admin.user.last_name}".strip() or admin.user.username if admin else "N/A"
        gym.admin_username = admin.user.username if admin else "N/A"

        # Calculate registered members and trainers for this gym
        gym.total_members = Member.objects.filter(gym=gym, is_deleted=False).count()
        gym.active_members = Member.objects.filter(
            gym=gym,
            is_deleted=False,
            membership_history__status='active',
            membership_history__is_deleted=False
        ).distinct().count()
        gym.total_trainers = Trainer.objects.filter(gym=gym).count()

        latest_subscription = GymSubscription.objects.filter(gym=gym, is_deleted=False).order_by('-end_date').first()
        if latest_subscription:
            gym.latest_subscription = latest_subscription
            gym.expiry_date = latest_subscription.end_date
            if gym.expiry_date < today:
                gym.membership_status = 'Expired'
                gym.days_remaining = 0
                total_expired_count += 1
            else:
                remaining_time = gym.expiry_date - today
                total_days = remaining_time.days
                gym.days_remaining = total_days
                if total_days <= 7:
                    gym.membership_status = 'Expiring Soon'
                    total_expiring_soon_count += 1
                else:
                    gym.membership_status = 'Active'
                    total_active_count += 1
                gym.remaining_months = total_days // 30
                gym.remaining_days = total_days % 30
        else:
            gym.latest_subscription = None
            gym.expiry_date = None
            gym.membership_status = 'No Subscription'
            gym.days_remaining = 0
            gym.remaining_months = 0
            gym.remaining_days = 0

        if gym.is_frozen:
            total_frozen_count += 1

        # Calculate due amount for this gym
        due_agg = GymSubscription.objects.filter(gym=gym, is_deleted=False).aggregate(
            tot=Sum('total_amount'),
            pd=Sum('paid_amount')
        )
        gym.due_amount = (due_agg['tot'] or Decimal('0.00')) - (due_agg['pd'] or Decimal('0.00'))

        # Apply status filter if selected
        if status_filter:
            if status_filter == 'active' and (gym.membership_status != 'Active' or gym.is_frozen):
                continue
            elif status_filter == 'expiring_soon' and gym.membership_status != 'Expiring Soon':
                continue
            elif status_filter == 'expired' and gym.membership_status != 'Expired':
                continue
            elif status_filter == 'frozen' and not gym.is_frozen:
                continue

        gym_items.append(gym)

    paginator = Paginator(gym_items, 10)  # Show 10 gyms per page
    page = request.GET.get('page')
    gyms = paginator.get_page(page)

    open_invoice_id = request.session.pop('open_invoice_id', None)
    return render(request, 'superadmin/gym_list.html', {
        'gyms': gyms,
        'open_invoice_id': open_invoice_id,
        'query': query,
        'status_filter': status_filter,
        'total_gyms_count': Gym.objects.count(),
        'total_active_count': total_active_count,
        'total_expiring_soon_count': total_expiring_soon_count,
        'total_expired_count': total_expired_count,
        'total_frozen_count': total_frozen_count,
    })


@login_required
@superadmin_required
def update_gym(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    if request.method == 'POST':
        form = GymForm(request.POST, request.FILES, instance=gym)
        if form.is_valid():
            gym = form.save()
            messages.success(request, f"Gym '{gym.name}' has been updated successfully.")
            return redirect('superadmin:gym_list')
    else:
        form = GymForm(instance=gym)
    return render(request, 'superadmin/add_gym.html', {'form': form, 'page_title': 'Update Gym', 'button_text': 'Update Gym'})

@login_required
@superadmin_required
@require_POST
def delete_gym(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    try:
        gym.delete()
        messages.success(request, 'Gym has been deleted successfully.')
        return JsonResponse({'status': 'success', 'message': 'Gym deleted successfully.'})
    except Exception as e:
        messages.error(request, f'An error occurred: {e}')
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@superadmin_required
def gym_profile(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    form = GymForm(instance=gym)

    # Subscriptions of this gym
    gym_subscriptions = GymSubscription.objects.filter(gym=gym, is_deleted=False).order_by('-start_date')
    today = timezone.now().date()
    active_subscription = gym_subscriptions.filter(start_date__lte=today, end_date__gte=today).first()
    gym_admins = GymAdmin.objects.filter(gym=gym)
    admin_form = GymAdminForm()

    # Calculate SaaS financial metrics for this gym
    aggregation = gym_subscriptions.aggregate(
        total_amount=Sum('total_amount'),
        paid_amount=Sum('paid_amount')
    )
    total_billed = aggregation['total_amount'] or Decimal('0.00')
    total_paid = aggregation['paid_amount'] or Decimal('0.00')
    due_amount = total_billed - total_paid

    # Platform payments from this gym (only member__isnull=True, eliminating all member payments)
    platform_due_payments = list(Payment.objects.filter(gym=gym, member__isnull=True, is_deleted=False).order_by('-payment_date'))
    
    # Subscriptions that had an upfront payment
    subscription_payments = [sub for sub in gym_subscriptions if sub.paid_amount > 0]

    # Combine into a unified payment timeline showing only payments from this Gym to Superadmin
    combined_history = sorted(
        subscription_payments + platform_due_payments,
        key=lambda item: item.start_date if isinstance(item, GymSubscription) else item.payment_date.date(),
        reverse=True
    )

    paginator_payments = Paginator(combined_history, 10)  # Show 10 payments per page
    page_payments = request.GET.get('page_payments')
    try:
        payment_history = paginator_payments.page(page_payments)
    except PageNotAnInteger:
        payment_history = paginator_payments.page(1)
    except EmptyPage:
        payment_history = paginator_payments.page(paginator_payments.num_pages)

    payment_modes = GymSubscription.PAYMENT_MODE_CHOICES

    # Calculate Quota usage percentages and resource counts
    registered_members_count = Member.objects.filter(gym=gym, is_deleted=False).count()
    active_members_count = Member.objects.filter(
        gym=gym,
        is_deleted=False,
        membership_history__status='active',
        membership_history__is_deleted=False
    ).distinct().count()
    trainers_count = Trainer.objects.filter(gym=gym).count()
    admins_count = gym_admins.count()

    plan = active_subscription.subscription if active_subscription else None
    
    max_members = plan.max_members if plan else None
    max_trainers = plan.max_trainers if plan else None
    max_admins = plan.max_admins if plan else None

    members_pct = min(100, round((registered_members_count / max_members * 100), 1)) if max_members else 0
    trainers_pct = min(100, round((trainers_count / max_trainers * 100), 1)) if max_trainers else 0
    admins_pct = min(100, round((admins_count / max_admins * 100), 1)) if max_admins else 0

    plan_modules = [
        {'name': 'Attendance Tracking', 'enabled': getattr(plan, 'has_biometric_attendance', getattr(plan, 'enable_attendance', True)) if plan else True, 'icon': 'mdi-calendar-check'},
        {'name': 'Billing & Invoicing', 'enabled': getattr(plan, 'has_billing_invoicing', getattr(plan, 'enable_billing', True)) if plan else True, 'icon': 'mdi-receipt'},
        {'name': 'Diet Plans', 'enabled': getattr(plan, 'has_diet_workout', getattr(plan, 'enable_diet_plans', True)) if plan else True, 'icon': 'mdi-food-apple'},
        {'name': 'Workout Plans', 'enabled': getattr(plan, 'has_diet_workout', getattr(plan, 'enable_workout_plans', True)) if plan else True, 'icon': 'mdi-dumbbell'},
        {'name': 'WhatsApp Reminders', 'enabled': getattr(plan, 'has_whatsapp_support', getattr(plan, 'enable_whatsapp_reminders', gym.whatsapp_enabled)) if plan else gym.whatsapp_enabled, 'icon': 'mdi-whatsapp'},
        {'name': 'Reports & Analytics', 'enabled': getattr(plan, 'has_reports_analytics', getattr(plan, 'enable_reports', True)) if plan else True, 'icon': 'mdi-chart-bar'},
        {'name': 'Expense Management', 'enabled': getattr(plan, 'has_expense_management', getattr(plan, 'enable_expenses', True)) if plan else True, 'icon': 'mdi-cash-multiple'},
        {'name': 'Custom Branding', 'enabled': getattr(plan, 'enable_custom_branding', True) if plan else True, 'icon': 'mdi-palette'},
        {'name': 'Public Landing Page', 'enabled': getattr(plan, 'enable_landing_page', True) if plan else True, 'icon': 'mdi-web'},
    ]

    return render(request, 'superadmin/gym_profile.html', {
        'gym': gym,
        'form': form,
        'payment_history': payment_history,
        'gym_subscriptions': gym_subscriptions,
        'active_subscription': active_subscription,
        'gym_admins': gym_admins,
        'admin_form': admin_form,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'due_amount': due_amount,
        'payment_modes': payment_modes,
        'registered_members_count': registered_members_count,
        'active_members_count': active_members_count,
        'trainers_count': trainers_count,
        'admins_count': admins_count,
        'max_members': max_members,
        'max_trainers': max_trainers,
        'max_admins': max_admins,
        'members_pct': members_pct,
        'trainers_pct': trainers_pct,
        'admins_pct': admins_pct,
        'plan_modules': plan_modules,
    })


@login_required
@superadmin_required
@require_POST
def update_gym_settings(request, gym_id):
    gym = get_object_or_404(Gym, pk=gym_id)
    gym.attendance_code_required = request.POST.get('attendance_code_required') == 'on'
    new_attendance_code = request.POST.get('attendance_code', '').strip()
    if new_attendance_code:
        gym.attendance_code = new_attendance_code

    gym.gst_enabled = request.POST.get('gst_enabled') == 'on'
    if gym.gst_enabled:
        gym.gst_number = request.POST.get('gst_number', '').strip()
        gst_rate = request.POST.get('gst_rate', '0').strip()
        gym.gst_rate = int(gst_rate) if gst_rate.isdigit() else 0
    else:
        gym.gst_number = None
        gym.gst_rate = 0

    gym.save()
    messages.success(request, f"Settings for '{gym.name}' updated successfully.")
    return redirect('superadmin:gym_profile', gym_id=gym.id)

@login_required
@superadmin_required
def reset_admin_password(request, admin_id):
    admin = get_object_or_404(GymAdmin, id=admin_id)
    user = admin.user
    user.set_password('BTsquare@123')
    user.save()
    
    # Mark the gym for password reset
    admin.gym.password_reset_required = True
    admin.gym.save()

    # Dispatch password reset email
    if user.email:
        email_sent, _ = send_password_reset_email(user, 'BTsquare@123', gym_name=admin.gym.name, request=request)
        if email_sent:
            messages.success(request, f"Password for {user.username} has been reset successfully and credentials emailed to {user.email}.")
        else:
            messages.success(request, f"Password for {user.username} has been reset to default 'BTsquare@123'.")
    else:
        messages.success(request, f"Password for {user.username} has been reset to default 'BTsquare@123'.")

    return redirect('superadmin:gym_profile', gym_id=admin.gym.id)


@login_required
@superadmin_required
def subscription_plan_list(request):
    query = request.GET.get('q')
    tier_filter = request.GET.get('tier')
    status_filter = request.GET.get('status')

    plans = SubscriptionPlan.objects.all().order_by('-is_popular', 'price')
    if query:
        plans = plans.filter(
            Q(name__icontains=query) |
            Q(tagline__icontains=query) |
            Q(features__icontains=query)
        ).distinct()

    if tier_filter:
        plans = plans.filter(plan_tier=tier_filter)

    if status_filter == 'active':
        plans = plans.filter(is_active=True)
    elif status_filter == 'inactive':
        plans = plans.filter(is_active=False)

    return render(request, 'superadmin/subscription_plan_list.html', {
        'plans': plans,
        'query': query,
        'tier_filter': tier_filter,
        'status_filter': status_filter,
        'tier_choices': SubscriptionPlan.TIER_CHOICES,
    })

@login_required
@superadmin_required
def add_subscription_plan(request):
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Subscription plan '{plan.name}' created successfully with configured limits.")
            return redirect('superadmin:subscription_plan_list')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        form = SubscriptionPlanForm()
    return render(request, 'superadmin/add_subscription_plan.html', {'form': form})

@login_required
@superadmin_required
def update_subscription_plan(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    if request.method == 'POST':
        form = SubscriptionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, f"Subscription plan '{plan.name}' updated successfully.")
            return redirect('superadmin:subscription_plan_list')
        else:
            messages.error(request, "Please correct the errors in the form below.")
    else:
        form = SubscriptionPlanForm(instance=plan)
    return render(request, 'superadmin/update_subscription_plan.html', {'form': form, 'plan': plan})

@login_required
@superadmin_required
@require_POST
def delete_subscription_plan(request, plan_id):
    plan = get_object_or_404(SubscriptionPlan, id=plan_id)
    try:
        plan.delete()
        messages.success(request, 'Subscription plan has been deleted successfully.')
        return JsonResponse({'status': 'success', 'message': 'Subscription plan deleted successfully.'})
    except Exception as e:
        messages.error(request, f'An error occurred: {e}')
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
@superadmin_required
def assign_subscription(request):
    if request.method == 'POST':
        gym_id = request.POST.get('gym')
        subscription_id = request.POST.get('subscription')
        start_date = request.POST.get('start_date')
        discount = request.POST.get('discount')
        total_amount = request.POST.get('total_amount')
        paid_amount = request.POST.get('paid_amount')
        payment_mode = request.POST.get('payment_mode')
        transaction_id = request.POST.get('transaction_id')
        remark = request.POST.get('remark')

        gym = get_object_or_404(Gym, id=gym_id)
        subscription = get_object_or_404(SubscriptionPlan, id=subscription_id)

        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = start_date_obj + timedelta(days=subscription.duration_months * 30)

        new_subscription = GymSubscription.objects.create(
            gym=gym,
            subscription=subscription,
            start_date=start_date,
            end_date=end_date,
            discount=discount,
            total_amount=total_amount,
            paid_amount=paid_amount,
            payment_mode=payment_mode,
            transaction_id=transaction_id,
            remark=remark
        )
        messages.success(request, f'Subscription assigned to {gym.name} successfully.')
        request.session['open_invoice_id'] = new_subscription.id
        return redirect('superadmin:gym_list')

    else:
        gyms = Gym.objects.all().order_by('name')
        subscriptions = SubscriptionPlan.objects.all().order_by('price')
        payment_modes = GymSubscription.PAYMENT_MODE_CHOICES
        selected_gym_id = request.GET.get('gym_id')
        selected_plan_id = request.GET.get('plan_id')

        subscriptions_data = [
            {
                'id': s.id,
                'name': s.name,
                'price': str(s.price),
                'duration_months': s.duration_months,
                'plan_tier': s.get_plan_tier_display() if hasattr(s, 'get_plan_tier_display') else getattr(s, 'plan_tier', ''),
                'color_theme': getattr(s, 'color_theme', 'blue'),
                'badge_text': getattr(s, 'tagline', '') or ('Most Popular' if getattr(s, 'is_popular', False) else ''),
                'max_members': s.max_members if s.max_members else 'Unlimited',
                'max_trainers': s.max_trainers if s.max_trainers else 'Unlimited',
                'max_admins': s.max_admins if s.max_admins else 'Unlimited',
                'modules': [
                    {'name': 'Attendance', 'enabled': getattr(s, 'has_biometric_attendance', getattr(s, 'enable_attendance', True))},
                    {'name': 'Billing', 'enabled': getattr(s, 'has_billing_invoicing', getattr(s, 'enable_billing', True))},
                    {'name': 'Diet Plans', 'enabled': getattr(s, 'has_diet_workout', getattr(s, 'enable_diet_plans', True))},
                    {'name': 'Workout Plans', 'enabled': getattr(s, 'has_diet_workout', getattr(s, 'enable_workout_plans', True))},
                    {'name': 'WhatsApp Reminders', 'enabled': getattr(s, 'has_whatsapp_support', getattr(s, 'enable_whatsapp_reminders', True))},
                    {'name': 'Reports & Analytics', 'enabled': getattr(s, 'has_reports_analytics', getattr(s, 'enable_reports', True))},
                    {'name': 'Expenses', 'enabled': getattr(s, 'has_expense_management', getattr(s, 'enable_expenses', True))},
                    {'name': 'Custom Branding', 'enabled': getattr(s, 'enable_custom_branding', True)},
                    {'name': 'Landing Page', 'enabled': getattr(s, 'enable_landing_page', True)},
                ]
            }
            for s in subscriptions
        ]

        return render(request, 'superadmin/assign_subscription.html', {
            'gyms': gyms,
            'subscriptions': subscriptions,
            'payment_modes': payment_modes,
            'selected_plan_id': selected_plan_id,
            'selected_gym_id': selected_gym_id,
            'subscriptions_data_json': json.dumps(subscriptions_data),
        })


@login_required
@superadmin_required
def billing_history(request):
    query = request.GET.get('q')
    status_filter = request.GET.get('status')
    type_filter = request.GET.get('type')

    base_queryset = GymSubscription.objects.filter(is_deleted=False) if request.user.is_superuser else GymSubscription.objects.filter(gym=request.user.gymadmin.gym, is_deleted=False)

    subscriptions = base_queryset.annotate(
        due_amount_calculated=F('total_amount') - F('paid_amount')
    ).order_by('-start_date')

    if query:
        subscriptions = subscriptions.filter(gym__name__icontains=query)

    if status_filter:
        if status_filter == 'paid':
            subscriptions = subscriptions.filter(due_amount_calculated=0)
        elif status_filter == 'unpaid':
            subscriptions = subscriptions.filter(due_amount_calculated__gt=0)

    # Get payments that are submitted via super admin (gym-to-platform payments)
    # These payments have no member associated with them
    payments = Payment.objects.filter(
        gym__in=subscriptions.values('gym'), 
        member__isnull=True, 
        is_deleted=False
    ).order_by('-payment_date')

    if type_filter == 'subscription':
        history = list(subscriptions)
    elif type_filter == 'payment':
        history = list(payments)
    else:
        # Combine and sort both types
        history = sorted(
            list(subscriptions) + list(payments),
            key=lambda item: item.start_date if isinstance(item, GymSubscription) else item.payment_date.date(),
            reverse=True
        )

    paginator = Paginator(history, 10)
    page = request.GET.get('page')
    try:
        history_page = paginator.page(page)
    except PageNotAnInteger:
        history_page = paginator.page(1)
    except EmptyPage:
        history_page = paginator.page(paginator.num_pages)

    # Calculate stats for the dashboard cards
    total_revenue = GymSubscription.objects.filter(is_deleted=False).aggregate(Sum('paid_amount'))['paid_amount__sum'] or 0
    total_revenue += Payment.objects.filter(member__isnull=True, is_deleted=False).aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_due = GymSubscription.objects.filter(is_deleted=False).aggregate(
        total=Sum('total_amount'),
        paid=Sum('paid_amount')
    )
    total_due_amount = (total_due['total'] or 0) - (total_due['paid'] or 0)

    context = {
        'history': history_page,
        'query': query,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'total_revenue': total_revenue,
        'total_due': total_due_amount,
        'active_gyms_count': Gym.objects.filter(is_frozen=False).count(),
    }
    return render(request, 'superadmin/billing_history.html', context)


@login_required
@superadmin_required
def submit_due(request):
    if request.method == 'POST':
        gym_id = request.POST.get('gym')
        amount_to_pay = request.POST.get('amount_to_pay')
        payment_method = request.POST.get('payment_method')
        notes = request.POST.get('notes')
        
        if gym_id and amount_to_pay:
            gym = get_object_or_404(Gym, id=gym_id)
            amount_to_pay_decimal = Decimal(amount_to_pay)

            # Total due for the gym
            aggregation = GymSubscription.objects.filter(gym=gym, is_deleted=False).aggregate(
                total_amount=Sum('total_amount'),
                paid_amount=Sum('paid_amount')
            )
            gym_total_due = (aggregation['total_amount'] or 0) - (aggregation['paid_amount'] or 0)

            if amount_to_pay_decimal > gym_total_due:
                messages.error(request, 'Amount to pay cannot be greater than the total due amount.')
            else:
                # Apply payment to subscriptions, oldest first
                with transaction.atomic():
                    subscriptions = list(GymSubscription.objects.filter(gym=gym, is_deleted=False).annotate(
                        due=F('total_amount') - F('paid_amount')
                    ).filter(due__gt=0).order_by('start_date'))
                    
                    payment_to_apply = amount_to_pay_decimal
                    last_updated_sub = None
                    for sub in subscriptions:
                        if payment_to_apply <= 0:
                            break
                        
                        current_due = sub.total_amount - sub.paid_amount
                        payable = min(payment_to_apply, current_due)
                        sub.paid_amount += payable
                        sub.save()
                        payment_to_apply -= payable
                        last_updated_sub = sub

                    Payment.objects.create(
                        gym=gym,
                        amount=amount_to_pay_decimal,
                        payment_date=timezone.now(),
                        payment_mode=payment_method,
                        comment=notes
                    )

                messages.success(request, 'Due amount submitted successfully.')
                # Open invoice in new tab via session safely
                target_sub = last_updated_sub or (subscriptions[-1] if subscriptions else None)
                if not target_sub:
                    target_sub = GymSubscription.objects.filter(gym=gym, is_deleted=False).order_by('-start_date').first()
                if target_sub:
                    request.session['open_invoice_id'] = target_sub.id
        
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('superadmin:submit_due')

    gyms_with_due = Gym.objects.filter(gymsubscription__is_deleted=False).annotate(
        total_subscription_amount=Sum('gymsubscription__total_amount'),
        total_paid_amount=Sum('gymsubscription__paid_amount')
    ).filter(total_subscription_amount__gt=F('total_paid_amount')).annotate(
        total_due=F('total_subscription_amount') - F('total_paid_amount'),
        admin_name=F('gymadmin__name'),
        contact_no=F('phone'),
    )

    for gym in gyms_with_due:
        gym.latest_subscription = GymSubscription.objects.filter(gym=gym).latest('start_date')

    query = request.GET.get('q')
    selected_gym_id = request.GET.get('gym_id')
    if query:
        gyms_with_due = gyms_with_due.filter(
            Q(name__icontains=query) |
            Q(gym_id__icontains=query) |
            Q(admin_name__icontains=query)
        ).distinct()

    open_invoice_id = request.session.pop('open_invoice_id', None)

    return render(request, 'superadmin/submit_due.html', {
        'gyms': gyms_with_due, 
        'query': query,
        'open_invoice_id': open_invoice_id,
        'selected_gym_id': selected_gym_id,
    })

@login_required
@superadmin_required
def get_due_amount(request, gym_id):
    gym = get_object_or_404(Gym, id=gym_id)
    aggregation = GymSubscription.objects.filter(gym=gym).aggregate(
        total_amount=Sum('total_amount'),
        paid_amount=Sum('paid_amount')
    )
    due_amount = (aggregation['total_amount'] or 0) - (aggregation['paid_amount'] or 0)
    return JsonResponse({'due_amount': due_amount})

@login_required
@superadmin_required
def website_contact_submissions(request):
    query = request.GET.get('q')
    type_filter = request.GET.get('type')
    
    submissions_list = WebsiteContactSubmission.objects.all()
    
    if query:
        submissions_list = submissions_list.annotate(
            full_name=Concat('first_name', Value(' '), 'last_name')
        ).filter(
            Q(full_name__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(business_name__icontains=query) |
            Q(message__icontains=query)
        )
        
    if type_filter:
        submissions_list = submissions_list.filter(inquiry_type=type_filter)

    paginator = Paginator(submissions_list, 20)
    page = request.GET.get('page')
    submissions = paginator.get_page(page)
    
    context = {
        'submissions': submissions,
        'page_title': 'Website Contact Submissions',
        'query': query,
        'type_filter': type_filter,
    }
    return render(request, 'superadmin/website_contact_submissions.html', context)

@login_required
@superadmin_required
@require_POST
def mark_submission_read(request, submission_id):
    submission = get_object_or_404(WebsiteContactSubmission, id=submission_id)
    submission.is_read = True
    submission.save()
    return JsonResponse({'status': 'success'})

@login_required
@superadmin_required
@require_POST
def delete_submission(request, submission_id):
    submission = get_object_or_404(WebsiteContactSubmission, id=submission_id)
    submission.delete()
    return JsonResponse({'status': 'success'})

@login_required
@superadmin_required
@require_POST
def delete_subscription(request, subscription_id):
    subscription = get_object_or_404(GymSubscription, id=subscription_id)
    subscription.is_deleted = True
    subscription.save()
    messages.success(request, 'Subscription moved to trash.')
    return JsonResponse({'status': 'success'})

@login_required
@superadmin_required
@require_POST
def delete_payment(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    payment.is_deleted = True
    payment.save()
    messages.success(request, 'Payment moved to trash.')
    return JsonResponse({'status': 'success'})

@login_required
@superadmin_required
def billing_trash(request):
    query = request.GET.get('q')
    
    subscriptions = GymSubscription.objects.filter(is_deleted=True).annotate(
        due_amount_calculated=F('total_amount') - F('paid_amount')
    )
    payments = Payment.objects.filter(is_deleted=True, member__isnull=True)

    if query:
        subscriptions = subscriptions.filter(gym__name__icontains=query)
        payments = payments.filter(gym__name__icontains=query)

    history = sorted(
        list(subscriptions) + list(payments),
        key=lambda item: item.start_date if isinstance(item, GymSubscription) else item.payment_date.date(),
        reverse=True
    )

    paginator = Paginator(history, 10)
    page = request.GET.get('page')
    history_page = paginator.get_page(page)

    return render(request, 'superadmin/billing_trash.html', {'history': history_page, 'query': query})

@login_required
@superadmin_required
@require_POST
def restore_billing(request, item_id, item_type):
    if item_type == 'subscription':
        item = get_object_or_404(GymSubscription, id=item_id)
    else:
        item = get_object_or_404(Payment, id=item_id)
    
    item.is_deleted = False
    item.save()
    messages.success(request, 'Record restored successfully.')
    return JsonResponse({'status': 'success'})

@login_required
@superadmin_required
@require_POST
def permanent_delete_billing(request, item_id, item_type):
    if item_type == 'subscription':
        item = get_object_or_404(GymSubscription, id=item_id)
    else:
        item = get_object_or_404(Payment, id=item_id)
    
    item.delete()
    messages.success(request, 'Record deleted permanently.')
    return JsonResponse({'status': 'success'})


# ====================================================
# SUPERADMIN NOTIFICATIONS & BROADCAST MANAGEMENT
# ====================================================

@login_required
@superadmin_required
def notification_list(request):
    """
    Displays list of all platform notifications with status, recipient metrics, and filters.
    """
    notifications = PlatformNotification.objects.annotate(
        read_count=Sum(
            models.Case(
                models.When(user_statuses__is_read=True, then=1),
                default=0,
                output_field=models.IntegerField()
            )
        ),
        popup_ack_count=Sum(
            models.Case(
                models.When(user_statuses__popup_acknowledged=True, then=1),
                default=0,
                output_field=models.IntegerField()
            )
        )
    ).select_related('target_gym', 'target_user', 'created_by').order_by('-created_at')

    # Status filter
    status_filter = request.GET.get('status', 'all')
    now = timezone.now()
    if status_filter == 'active':
        notifications = notifications.filter(is_active=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
    elif status_filter == 'inactive':
        notifications = notifications.filter(is_active=False)
    elif status_filter == 'popups':
        notifications = notifications.filter(show_popup=True)

    # Creator / Author filter
    created_by_filter = request.GET.get('created_by', '').strip()
    if created_by_filter:
        if created_by_filter in ('superadmin', 'me', 'self'):
            notifications = notifications.filter(created_by__isnull=False)
        elif created_by_filter == 'system':
            notifications = notifications.filter(created_by__isnull=True)
        elif created_by_filter.isdigit():
            notifications = notifications.filter(created_by_id=created_by_filter)

    # Search filter
    q = request.GET.get('q', '').strip()
    if q:
        notifications = notifications.filter(
            Q(title__icontains=q) |
            Q(message__icontains=q) |
            Q(created_by__username__icontains=q) |
            Q(created_by__first_name__icontains=q) |
            Q(created_by__last_name__icontains=q)
        )

    # Counts for creators
    superadmin_notifications_count = PlatformNotification.objects.filter(created_by__isnull=False).count()
    system_notifications_count = PlatformNotification.objects.filter(created_by__isnull=True).count()

    paginator = Paginator(notifications, 15)
    page = request.GET.get('page')
    notifications_page = paginator.get_page(page)

    context = {
        'notifications': notifications_page,
        'status_filter': status_filter,
        'created_by_filter': created_by_filter,
        'superadmin_notifications_count': superadmin_notifications_count,
        'system_notifications_count': system_notifications_count,
        'q': q,
        'now': now,
    }
    return render(request, 'superadmin/notification_list.html', context)


@login_required
@superadmin_required
def create_notification(request):
    """
    Form view to compose and send a new broadcast notification / popup.
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        message_body = request.POST.get('message', '').strip()
        notification_type = request.POST.get('notification_type', 'info')
        target_type = request.POST.get('target_type', 'all')
        target_gym_id = request.POST.get('target_gym') or None
        target_user_id = request.POST.get('target_user') or None
        show_popup = request.POST.get('show_popup') == 'on'
        is_dismissible = request.POST.get('is_dismissible') == 'on'
        action_label = request.POST.get('action_label', '').strip() or None
        action_url = request.POST.get('action_url', '').strip() or None
        expires_at_str = request.POST.get('expires_at', '').strip()

        if not title or not message_body:
            messages.error(request, 'Please provide both a Title and Message.')
            return redirect('superadmin:create_notification')

        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.strptime(expires_at_str, '%Y-%m-%dT%H:%M')
                expires_at = timezone.make_aware(expires_at)
            except ValueError:
                pass

        target_gym = None
        if target_gym_id:
            target_gym = Gym.objects.filter(id=target_gym_id).first()

        target_user = None
        if target_user_id:
            target_user = User.objects.filter(id=target_user_id).first()

        image = request.FILES.get('image')
        popup_frequency = request.POST.get('popup_frequency', 'once')
        max_popup_views_str = request.POST.get('max_popup_views', '1').strip()
        try:
            max_popup_views = max(1, int(max_popup_views_str))
        except (ValueError, TypeError):
            max_popup_views = 1

        notification = PlatformNotification.objects.create(
            title=title,
            message=message_body,
            notification_type=notification_type,
            target_type=target_type,
            target_gym=target_gym,
            target_user=target_user,
            image=image,
            show_popup=show_popup,
            is_dismissible=is_dismissible,
            popup_frequency=popup_frequency,
            max_popup_views=max_popup_views,
            action_label=action_label,
            action_url=action_url,
            expires_at=expires_at,
            created_by=request.user,
        )

        messages.success(request, f"Notification '{notification.title}' broadcasted successfully!")
        return redirect('superadmin:notification_list')

    gyms = Gym.objects.all().order_by('name')
    users = User.objects.filter(is_active=True).order_by('username')[:100]

    context = {
        'gyms': gyms,
        'users': users,
    }
    return render(request, 'superadmin/create_notification.html', context)


@login_required
@superadmin_required
def toggle_notification_status(request, notification_id):
    """
    Toggles the active state of a notification.
    """
    notification = get_object_or_404(PlatformNotification, id=notification_id)
    notification.is_active = not notification.is_active
    notification.save(update_fields=['is_active'])
    status_str = 'activated' if notification.is_active else 'deactivated'
    messages.success(request, f"Notification '{notification.title}' has been {status_str}.")
    return redirect('superadmin:notification_list')


@login_required
@superadmin_required
@require_POST
def delete_notification(request, notification_id):
    """
    Deletes a notification and its delivery statuses.
    """
    notification = get_object_or_404(PlatformNotification, id=notification_id)
    title = notification.title
    notification.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': f"Notification '{title}' deleted."})
    messages.success(request, f"Notification '{title}' was deleted successfully.")
    return redirect('superadmin:notification_list')


@login_required
@superadmin_required
def estimate_audience_api(request):
    """
    AJAX endpoint returning estimated recipient count breakdown.
    """
    target_type = request.GET.get('target_type', 'all')
    target_gym_id = request.GET.get('target_gym_id')
    target_user_id = request.GET.get('target_user_id')

    breakdown = estimate_audience(target_type, target_gym_id, target_user_id)
    return JsonResponse({'status': 'success', 'data': breakdown})


# ====================================================
# CLIENT-FACING NOTIFICATIONS & POPUP APIS
# ====================================================

@login_required
def get_active_popup_api(request):
    """
    Returns active unacknowledged popup announcement for the current user.
    """
    popup = get_active_popup_for_user(request.user, session=request.session)
    if popup:
        return JsonResponse({'status': 'success', 'has_popup': True, 'popup': popup})
    return JsonResponse({'status': 'success', 'has_popup': False})


@login_required
@require_POST
def acknowledge_popup_api(request, notification_id):
    """
    Records popup acknowledgment so the user is not shown this modal again.
    """
    success = acknowledge_popup(request.user, notification_id, session=request.session)
    return JsonResponse({'status': 'success' if success else 'error'})


@login_required
@require_POST
def mark_notification_read_api(request, notification_id):
    """
    Marks an individual notification as read.
    """
    success = mark_notification_as_read(request.user, notification_id)
    return JsonResponse({'status': 'success' if success else 'error'})


@login_required
@require_POST
def mark_all_notifications_read_api(request):
    """
    Marks all notifications as read for current user.
    """
    count = mark_all_notifications_as_read(request.user)
    return JsonResponse({'status': 'success', 'updated_count': count})


@login_required
def user_notifications_inbox(request):
    """
    Dedicated notifications inbox for any authenticated user.
    """
    all_notifications = get_user_applicable_notifications_qs(request.user)
    
    statuses = {
        s.notification_id: s
        for s in NotificationUserStatus.objects.filter(user=request.user, notification__in=all_notifications)
    }

    filter_type = request.GET.get('filter', 'all')
    items = []
    for n in all_notifications:
        status = statuses.get(n.id)
        is_read = status.is_read if status else False
        if filter_type == 'unread' and is_read:
            continue
        items.append({
            'notification': n,
            'is_read': is_read,
            'read_at': status.read_at if status else None,
        })

    paginator = Paginator(items, 15)
    page = request.GET.get('page')
    page_obj = paginator.get_page(page)

    context = {
        'page_obj': page_obj,
        'filter_type': filter_type,
        'total_count': len(items),
    }

    template_name = 'superadmin/notifications_inbox.html' if request.user.is_superuser else 'notifications/inbox.html'
    return render(request, template_name, context)


@login_required
@superadmin_required
def impersonate_gym_admin(request, gym_id):
    """
    Allows superadmin to securely switch into a gym's dashboard view for testing/support.
    """
    gym = get_object_or_404(Gym, pk=gym_id)
    
    # Store superadmin restore session
    request.session['impersonator_superadmin_id'] = request.user.id
    request.session['gym_id'] = gym.id
    request.session['gym_name'] = gym.name
    request.session['gym_logo'] = gym.logo.url if gym.logo else None
    request.session['gym_phone'] = gym.phone
    request.session['role'] = 'gym_admin'
    
    messages.info(request, f"You are now accessing {gym.name} portal as Gym Admin.")
    return redirect('dashboard')


@login_required
@superadmin_required
def export_gyms_csv(request):
    """
    Exports registered gyms directory to CSV with subscription status and member counts.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="gyms_export_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Gym ID', 'Gym Name', 'Phone', 'Email', 'City', 'State', 
        'Status', 'Active Plan', 'Plan End Date', 'Registered Members', 
        'Active Members', 'Staff Count', 'Pending Due (INR)', 'Created At'
    ])
    
    today = timezone.now().date()
    gyms = Gym.objects.annotate(
        reg_count=Count('member', filter=Q(member__is_deleted=False), distinct=True),
        act_count=Count('member', filter=Q(member__is_deleted=False, member__membership_history__status='active', member__membership_history__is_deleted=False), distinct=True),
        trainer_count=Count('trainer', filter=Q(trainer__is_active=True), distinct=True),
        admin_count=Count('gymadmin', distinct=True),
    ).order_by('-id')
    
    for g in gyms:
        active_sub = GymSubscription.objects.filter(
            gym=g, start_date__lte=today, end_date__gte=today, is_deleted=False
        ).select_related('subscription').first()
        
        plan_name = active_sub.subscription.name if (active_sub and active_sub.subscription) else 'No Active Plan'
        end_date = active_sub.end_date.strftime('%Y-%m-%d') if active_sub else 'N/A'
        status = 'Frozen' if g.is_frozen else 'Active'
        
        total_sub_amount = GymSubscription.objects.filter(gym=g, is_deleted=False).aggregate(s=Sum('total_amount'))['s'] or Decimal('0.00')
        paid_sub_amount = GymSubscription.objects.filter(gym=g, is_deleted=False).aggregate(s=Sum('paid_amount'))['s'] or Decimal('0.00')
        due = total_sub_amount - paid_sub_amount
        
        writer.writerow([
            g.gym_id,
            g.name,
            g.phone or '',
            g.email or '',
            g.city or '',
            g.state or '',
            status,
            plan_name,
            end_date,
            g.reg_count,
            g.act_count,
            (g.trainer_count + g.admin_count),
            float(due),
            g.created_at.strftime('%Y-%m-%d %H:%M') if g.created_at else ''
        ])
        
    return response


@login_required
@superadmin_required
def export_billing_csv(request):
    """
    Exports platform billing & payment transactions to CSV.
    """
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="billing_export_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Record ID', 'Type', 'Gym Name', 'Gym ID', 'Plan / Description', 
        'Start / Payment Date', 'End Date', 'Total Amount (INR)', 'Paid Amount (INR)', 
        'Due Amount (INR)', 'Payment Mode', 'Status'
    ])
    
    subs = GymSubscription.objects.filter(is_deleted=False).select_related('gym', 'subscription').order_by('-start_date')
    for s in subs:
        due = s.total_amount - s.paid_amount
        status = 'Paid' if due <= 0 else 'Pending'
        writer.writerow([
            f"SUB-{s.id}",
            'Subscription Plan',
            s.gym.name,
            s.gym.gym_id,
            s.subscription.name if s.subscription else 'Custom Plan',
            s.start_date.strftime('%Y-%m-%d'),
            s.end_date.strftime('%Y-%m-%d'),
            float(s.total_amount),
            float(s.paid_amount),
            float(due),
            s.payment_mode or 'N/A',
            status
        ])
        
    payments = Payment.objects.filter(member__isnull=True, is_deleted=False).select_related('gym').order_by('-payment_date')
    for p in payments:
        writer.writerow([
            f"PAY-{p.id}",
            'Due Payment',
            p.gym.name,
            p.gym.gym_id,
            'Platform Due Submission',
            p.payment_date.strftime('%Y-%m-%d'),
            '-',
            float(p.amount),
            float(p.amount),
            0.0,
            getattr(p, 'payment_mode', getattr(p, 'payment_method', 'N/A')) or 'N/A',
            'Completed'
        ])
        
    return response


@login_required
@superadmin_required
def whatsapp_messages_hub(request):
    """
    Superadmin centralized hub for WhatsApp communications:
    - Tracks which messages were sent or failed
    - Enables 1-click resending/sending via personal WhatsApp number
    - Direct WhatsApp chat integration
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    from apps.website.models import WebsiteContactSubmission
    from django.core.paginator import Paginator
    
    # Auto-seed initial message logs from website inquiries & gyms if empty, so the admin has real logs to test immediately
    if WhatsAppMessageLog.objects.count() == 0:
        inquiries = WebsiteContactSubmission.objects.all()[:5]
        for idx, inq in enumerate(inquiries):
            is_sent = (idx % 2 == 0)
            status = 'sent' if is_sent else 'failed'
            err = '' if is_sent else 'Twilio Delivery Notice: Message undelivered - recipient phone not active or sandbox invitation pending'
            clean_p = ''.join(c for c in inq.phone if c.isdigit())
            WhatsAppMessageLog.objects.create(
                recipient_name=f"{inq.first_name} {inq.last_name}",
                recipient_phone=clean_p or inq.phone,
                recipient_type='Website Lead',
                message_type='lead',
                message_content=f"Hello {inq.first_name}! Thank you for your inquiry about '{inq.get_inquiry_type_display()}'. How can the OneX-Fitness platform assist your fitness business today?",
                status=status,
                error_message=err,
                provider='twilio',
                sent_at=timezone.now() if is_sent else None,
                created_by=request.user
            )

    # Ensure an inbound message is also seeded if none exists to demonstrate received messages
    if not WhatsAppMessageLog.objects.filter(direction='inbound').exists():
        sample_gym = Gym.objects.first()
        WhatsAppMessageLog.objects.create(
            gym=sample_gym,
            direction='inbound',
            status='received',
            recipient_name='Priya Sharma',
            recipient_phone='9812345678',
            recipient_type='Gym Member',
            message_type='inbound_reply',
            message_content='Hi! I wanted to check if personal training sessions are available this weekend?',
            provider='twilio',
            sent_at=timezone.now() - timezone.timedelta(minutes=45)
        )

    queryset = WhatsAppMessageLog.objects.select_related('gym', 'created_by').all().order_by('-created_at')

    # Direction filter (inbound vs outbound)
    direction_filter = request.GET.get('direction', 'all')
    if direction_filter in ('inbound', 'received'):
        queryset = queryset.filter(Q(direction='inbound') | Q(status='received'))
    elif direction_filter in ('outbound', 'sent'):
        queryset = queryset.filter(direction='outbound')

    # Status Filtering
    status_filter = request.GET.get('status', 'all')
    if status_filter == 'sent':
        queryset = queryset.filter(status='sent', direction='outbound')
    elif status_filter == 'received':
        queryset = queryset.filter(Q(status='received') | Q(direction='inbound'))
    elif status_filter == 'failed':
        queryset = queryset.filter(status='failed')
    elif status_filter == 'sent_manually':
        queryset = queryset.filter(status='sent_manually')

    # Gym Filter
    gym_filter = request.GET.get('gym_id', 'all')
    if gym_filter != 'all' and gym_filter.isdigit():
        queryset = queryset.filter(gym_id=int(gym_filter))

    type_filter = request.GET.get('type', 'all')
    if type_filter != 'all':
        queryset = queryset.filter(message_type=type_filter)

    search_query = request.GET.get('q', '').strip()
    if search_query:
        queryset = queryset.filter(
            Q(recipient_name__icontains=search_query) |
            Q(recipient_phone__icontains=search_query) |
            Q(message_content__icontains=search_query)
        )

    # KPI Aggregates
    all_logs = WhatsAppMessageLog.objects.all()
    if gym_filter != 'all' and gym_filter.isdigit():
        all_logs = all_logs.filter(gym_id=int(gym_filter))

    total_count = all_logs.count()
    sent_count = all_logs.filter(status='sent', direction='outbound').count()
    received_count = all_logs.filter(Q(status='received') | Q(direction='inbound')).count()
    failed_count = all_logs.filter(status='failed').count()
    manual_count = all_logs.filter(status='sent_manually').count()
    
    total_resolved = sent_count + manual_count
    total_outgoing = sent_count + failed_count + manual_count
    delivery_rate = round((total_resolved / total_outgoing * 100), 1) if total_outgoing > 0 else 100.0

    # Pagination
    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Quick Contacts for new message modal
    quick_leads = WebsiteContactSubmission.objects.all().order_by('-created_at')[:8]
    quick_gyms = Gym.objects.filter(is_frozen=False).order_by('name')[:8]
    all_gyms = Gym.objects.all().order_by('name')

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'direction_filter': direction_filter,
        'gym_filter': gym_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        'total_count': total_count,
        'sent_count': sent_count,
        'received_count': received_count,
        'failed_count': failed_count,
        'manual_count': manual_count,
        'delivery_rate': delivery_rate,
        'quick_leads': quick_leads,
        'quick_gyms': quick_gyms,
        'all_gyms': all_gyms,
    }
    return render(request, 'superadmin/whatsapp_messages_hub.html', context)


@login_required
@superadmin_required
def mark_whatsapp_sent_manually(request, log_id):
    """
    Marks a message as sent via personal WhatsApp after the admin clicks to send.
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    log = get_object_or_404(WhatsAppMessageLog, pk=log_id)
    log.status = 'sent_manually'
    log.provider = 'personal_whatsapp'
    log.sent_at = timezone.now()
    log.error_message = None
    log.save()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({'success': True, 'status': 'sent_manually', 'message': 'Status updated to Sent with Personal WhatsApp'})

    messages.success(request, f"Marked message to {log.recipient_name} as sent via personal WhatsApp.")
    return redirect(request.META.get('HTTP_REFERER', 'superadmin:whatsapp_messages_hub'))


@login_required
@superadmin_required
def send_direct_whatsapp_message(request):
    """
    Composes a new direct WhatsApp message, saves the log, and redirects to wa.me to send.
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    if request.method == 'POST':
        recipient_name = request.POST.get('recipient_name', '').strip()
        recipient_phone = request.POST.get('recipient_phone', '').strip()
        message_content = request.POST.get('message_content', '').strip()
        recipient_type = request.POST.get('recipient_type', 'Direct Contact')
        action_type = request.POST.get('action_type', 'open_wa')

        if not recipient_phone or not message_content:
            messages.error(request, "Recipient phone number and message content are required.")
            return redirect('superadmin:whatsapp_messages_hub')

        log = WhatsAppMessageLog.objects.create(
            recipient_name=recipient_name or recipient_phone,
            recipient_phone=recipient_phone,
            recipient_type=recipient_type,
            message_type='direct_chat',
            message_content=message_content,
            status='sent_manually' if action_type == 'open_wa' else 'pending',
            provider='personal_whatsapp',
            created_by=request.user,
            sent_at=timezone.now() if action_type == 'open_wa' else None
        )

        messages.success(request, f"WhatsApp link prepared for {recipient_name}. Launching WhatsApp...")
        return redirect(log.whatsapp_url)

    return redirect('superadmin:whatsapp_messages_hub')


@login_required
@superadmin_required
def whatsapp_conversations_api(request):
    """
    Returns list of distinct WhatsApp conversation threads grouped by contact phone number.
    Includes last message snippet, status, time, unread indicator, and contact metadata.
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    search_q = request.GET.get('q', '').strip()
    gym_id = request.GET.get('gym_id', 'all')
    filter_type = request.GET.get('filter', 'all')

    qs = WhatsAppMessageLog.objects.select_related('gym').all().order_by('-created_at')
    if gym_id != 'all' and gym_id.isdigit():
        qs = qs.filter(gym_id=int(gym_id))

    if search_q:
        qs = qs.filter(
            Q(recipient_name__icontains=search_q) |
            Q(recipient_phone__icontains=search_q) |
            Q(message_content__icontains=search_q)
        )

    # Grouping by normalized 10-digit phone
    threads_map = {}
    for log in qs:
        raw_phone = log.recipient_phone or ''
        digits = ''.join(c for c in raw_phone if c.isdigit())
        key = digits[-10:] if len(digits) >= 10 else (digits or raw_phone)
        if not key:
            continue

        if key not in threads_map:
            threads_map[key] = {
                'phone': raw_phone,
                'clean_digits': key,
                'name': log.recipient_name or raw_phone,
                'recipient_type': log.recipient_type or 'Contact',
                'gym_name': log.gym.name if log.gym else 'OneX-Fitness Platform',
                'gym_id': log.gym.id if log.gym else None,
                'last_message': log.message_content or '',
                'last_time': log.created_at.strftime('%I:%M %p'),
                'last_date': log.created_at.strftime('%d %b'),
                'last_timestamp': log.created_at.isoformat(),
                'last_status': log.status,
                'last_direction': log.direction,
                'is_inbound': log.is_inbound,
                'inbound_count': 0,
                'total_count': 0,
                'has_failed': False,
            }
        thread = threads_map[key]
        thread['total_count'] += 1
        if log.is_inbound:
            thread['inbound_count'] += 1
        if log.status == 'failed':
            thread['has_failed'] = True

    conversations = list(threads_map.values())

    if filter_type == 'inbound':
        conversations = [c for c in conversations if c['inbound_count'] > 0]
    elif filter_type == 'failed':
        conversations = [c for c in conversations if c['has_failed']]
    elif filter_type == 'outbound':
        conversations = [c for c in conversations if c['last_direction'] == 'outbound']

    return JsonResponse({'success': True, 'conversations': conversations})


@login_required
@superadmin_required
def whatsapp_thread_api(request, phone):
    """
    Returns the complete chronological message history for a phone number.
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    digits = ''.join(c for c in phone if c.isdigit())
    search_key = digits[-10:] if len(digits) >= 10 else digits

    if not search_key:
        return JsonResponse({'success': False, 'error': 'Invalid phone number'}, status=400)

    logs = WhatsAppMessageLog.objects.select_related('gym', 'created_by').filter(
        recipient_phone__icontains=search_key
    ).order_by('created_at')

    latest_log = logs.last()
    contact_data = {
        'name': latest_log.recipient_name if latest_log else phone,
        'phone': phone,
        'clean_phone': latest_log.clean_phone if latest_log else digits,
        'recipient_type': latest_log.recipient_type if latest_log else 'Contact',
        'gym_name': latest_log.gym.name if (latest_log and latest_log.gym) else 'OneX-Fitness Platform',
        'gym_id': latest_log.gym.id if (latest_log and latest_log.gym) else None,
        'direct_chat_url': latest_log.direct_chat_url if latest_log else f"https://wa.me/{digits}",
    }

    message_list = []
    for m in logs:
        message_list.append({
            'id': m.id,
            'direction': m.direction,
            'is_inbound': m.is_inbound,
            'status': m.status,
            'status_display': m.get_status_display(),
            'message_type': m.get_message_type_display(),
            'message_content': m.message_content,
            'error_message': m.error_message or '',
            'provider': m.provider,
            'time': m.created_at.strftime('%I:%M %p'),
            'date': m.created_at.strftime('%d %b, %Y'),
            'timestamp': m.created_at.isoformat(),
            'whatsapp_url': m.whatsapp_url,
        })

    return JsonResponse({
        'success': True,
        'contact': contact_data,
        'messages': message_list
    })


@login_required
@superadmin_required
def whatsapp_send_api(request):
    """
    Sends or logs an outbound WhatsApp message from the live console.
    Supports Twilio Cloud API dispatch or 1-click personal WhatsApp generation.
    """
    from apps.whatsapp.models import WhatsAppMessageLog
    from apps.whatsapp.services import WhatsAppService

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'}, status=405)

    recipient_phone = request.POST.get('recipient_phone', '').strip()
    recipient_name = request.POST.get('recipient_name', '').strip() or recipient_phone
    message_content = request.POST.get('message_content', '').strip()
    send_method = request.POST.get('send_method', 'twilio')
    gym_id = request.POST.get('gym_id')

    if not recipient_phone or not message_content:
        return JsonResponse({'success': False, 'error': 'Phone number and message content are required'}, status=400)

    gym = None
    if gym_id and str(gym_id).isdigit():
        gym = Gym.objects.filter(pk=int(gym_id)).first()

    if send_method == 'twilio':
        svc = WhatsAppService(gym_id=gym.id if gym else None)
        res, log = svc.send_direct_message(
            to_number=recipient_phone,
            recipient_name=recipient_name,
            message_text=message_content,
            gym=gym,
            recipient_type='Direct Contact',
            created_by=request.user
        )
        is_success = bool(res and res.get('success'))
        return JsonResponse({
            'success': is_success,
            'status': log.status if log else ('sent' if is_success else 'failed'),
            'error': res.get('error') if (res and not is_success) else None,
            'log_id': log.id if log else None,
            'whatsapp_url': log.whatsapp_url if log else f"https://wa.me/{recipient_phone}",
            'message': {
                'id': log.id if log else None,
                'direction': 'outbound',
                'is_inbound': False,
                'status': log.status if log else 'sent',
                'status_display': log.get_status_display() if log else 'Delivered',
                'message_content': message_content,
                'error_message': log.error_message if log else '',
                'provider': 'twilio',
                'time': timezone.now().strftime('%I:%M %p'),
                'date': timezone.now().strftime('%d %b, %Y'),
                'whatsapp_url': log.whatsapp_url if log else f"https://wa.me/{recipient_phone}",
            }
        })
    else:
        # Personal WhatsApp dispatch
        log = WhatsAppMessageLog.objects.create(
            gym=gym,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            recipient_type='Direct Contact',
            message_type='direct_chat',
            message_content=message_content,
            status='sent_manually',
            provider='personal_whatsapp',
            created_by=request.user,
            sent_at=timezone.now()
        )
        return JsonResponse({
            'success': True,
            'status': 'sent_manually',
            'log_id': log.id,
            'whatsapp_url': log.whatsapp_url,
            'message': {
                'id': log.id,
                'direction': 'outbound',
                'is_inbound': False,
                'status': 'sent_manually',
                'status_display': 'Sent via Personal WA',
                'message_content': message_content,
                'error_message': '',
                'provider': 'personal_whatsapp',
                'time': log.created_at.strftime('%I:%M %p'),
                'date': log.created_at.strftime('%d %b, %Y'),
                'whatsapp_url': log.whatsapp_url,
            }
        })


# ==============================================================================
# SYSTEM SETTINGS & CONFIGURATION
# ==============================================================================

@login_required
@superadmin_required
def system_settings_view(request):
    """
    Superadmin console for platform-wide common settings, branding,
    defaults, SMTP configuration, and security policies.
    """
    setting = SystemSetting.get_settings()

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        # 1. AJAX Test Email Dispatch
        if action == 'send_test_email':
            test_recipient = request.POST.get('test_recipient', '').strip() or request.user.email
            if not test_recipient:
                return JsonResponse({'success': False, 'message': 'Please provide a valid recipient email address.'})

            host = request.POST.get('smtp_host') or setting.smtp_host
            port = int(request.POST.get('smtp_port') or setting.smtp_port or 587)
            user = request.POST.get('smtp_user') or setting.smtp_user
            pwd = request.POST.get('smtp_password') or setting.smtp_password
            from_email = request.POST.get('smtp_from_email') or setting.smtp_from_email or user
            use_tls = request.POST.get('smtp_use_tls') == 'on' if 'smtp_use_tls' in request.POST else setting.smtp_use_tls
            use_ssl = request.POST.get('smtp_use_ssl') == 'on' if 'smtp_use_ssl' in request.POST else setting.smtp_use_ssl

            if not host:
                return JsonResponse({'success': False, 'message': 'SMTP Host server is required to send a test email.'})

            try:
                from django.core.mail import EmailMultiAlternatives
                connection = get_connection(
                    backend='django.core.mail.backends.smtp.EmailBackend',
                    host=host,
                    port=port,
                    username=user,
                    password=pwd,
                    use_tls=use_tls,
                    use_ssl=use_ssl,
                    timeout=12,
                )
                platform_name = setting.platform_name or 'ONEX BOOST'
                timestamp_str = timezone.now().strftime('%d %b %Y, %I:%M:%S %p')
                subject = f"[{platform_name}] SMTP Gateway Test Verification"
                text_body = f"Hello,\n\nThis is a verification test from {platform_name}.\nYour Outbound Email & SMTP Gateway has been successfully configured and connected.\n\nDispatched at: {timestamp_str}\nHost: {host}:{port}\nSender: {from_email}\n\nONEX BOOST SaaS Platform"

                html_body = f"""
                <div style="max-width:600px;margin:20px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);border:1px solid #e2e8f0;font-family:sans-serif;">
                    <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:28px 24px;text-align:center;color:#fff;">
                        <h2 style="margin:0;font-size:22px;text-transform:uppercase;letter-spacing:0.5px;">{platform_name}</h2>
                        <p style="margin:4px 0 0;font-size:13px;opacity:0.9;">Outbound Email &amp; SMTP Gateway Verification</p>
                    </div>
                    <div style="padding:30px 24px;color:#334155;">
                        <div style="font-size:16px;font-weight:700;margin-bottom:12px;color:#0f172a;">SMTP Test Succeeded! 🎉</div>
                        <p style="font-size:14px;line-height:1.6;color:#475569;margin-bottom:20px;">
                            Congratulations! Your platform mail gateway is fully operational. Outbound transactional emails (such as gym onboarding, admin credentials, and password resets) will now be safely dispatched through this server.
                        </p>
                        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #10b981;border-radius:8px;padding:16px;margin:20px 0;font-size:13px;">
                            <div><strong>SMTP Server:</strong> {host}:{port}</div>
                            <div style="margin-top:4px;"><strong>Authenticated User:</strong> {user}</div>
                            <div style="margin-top:4px;"><strong>From Header:</strong> {from_email}</div>
                            <div style="margin-top:4px;"><strong>Security:</strong> {'TLS Enabled' if use_tls else ('SSL Enabled' if use_ssl else 'Plain')}</div>
                            <div style="margin-top:4px;"><strong>Dispatched At:</strong> {timestamp_str}</div>
                        </div>
                    </div>
                    <div style="background:#f8fafc;padding:16px;text-align:center;font-size:12px;color:#94a3b8;border-top:1px solid #e2e8f0;">
                        &copy; {timezone.now().year} {platform_name}. All rights reserved.
                    </div>
                </div>
                """

                email = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=f"{platform_name} <{from_email}>",
                    to=[test_recipient],
                    connection=connection,
                )
                email.attach_alternative(html_body, "text/html")
                email.send(fail_silently=False)
                return JsonResponse({'success': True, 'message': f'Test email successfully dispatched to {test_recipient}!'})
            except Exception as e:
                return JsonResponse({'success': False, 'message': f'SMTP Error: {str(e)}'})

        # 2. Update General Settings
        setting.platform_name = request.POST.get('platform_name', setting.platform_name).strip()
        setting.tagline = request.POST.get('tagline', setting.tagline).strip()
        setting.company_name = request.POST.get('company_name', setting.company_name).strip()
        setting.support_email = request.POST.get('support_email', setting.support_email).strip()
        setting.support_phone = request.POST.get('support_phone', setting.support_phone).strip()
        setting.website_url = request.POST.get('website_url', setting.website_url).strip()
        setting.currency_symbol = request.POST.get('currency_symbol', setting.currency_symbol).strip()
        setting.currency_code = request.POST.get('currency_code', setting.currency_code).strip()
        setting.timezone = request.POST.get('timezone', setting.timezone).strip()

        # Defaults
        setting.default_trial_days = int(request.POST.get('default_trial_days', setting.default_trial_days) or 14)
        setting.grace_period_days = int(request.POST.get('grace_period_days', setting.grace_period_days) or 7)
        setting.default_member_prefix = request.POST.get('default_member_prefix', setting.default_member_prefix).strip()
        setting.allow_public_registration = request.POST.get('allow_public_registration') == 'on'
        setting.global_whatsapp_master = request.POST.get('global_whatsapp_master') == 'on'
        setting.maintenance_mode = request.POST.get('maintenance_mode') == 'on'
        setting.maintenance_message = request.POST.get('maintenance_message', setting.maintenance_message).strip()

        # SMTP
        setting.smtp_host = request.POST.get('smtp_host', '').strip()
        setting.smtp_port = int(request.POST.get('smtp_port') or 587)
        setting.smtp_user = request.POST.get('smtp_user', '').strip()
        if request.POST.get('smtp_password'):
            setting.smtp_password = request.POST.get('smtp_password')
        setting.smtp_from_email = request.POST.get('smtp_from_email', '').strip()
        setting.smtp_use_tls = request.POST.get('smtp_use_tls') == 'on'
        setting.smtp_use_ssl = request.POST.get('smtp_use_ssl') == 'on'

        # Backup & Security
        setting.auto_backup_enabled = request.POST.get('auto_backup_enabled') == 'on'
        setting.backup_frequency = request.POST.get('backup_frequency', setting.backup_frequency)
        setting.backup_retention_days = int(request.POST.get('backup_retention_days', setting.backup_retention_days) or 30)
        setting.include_media_in_auto_backup = request.POST.get('include_media_in_auto_backup') == 'on'
        setting.session_timeout_minutes = int(request.POST.get('session_timeout_minutes', setting.session_timeout_minutes) or 120)
        setting.max_login_attempts = int(request.POST.get('max_login_attempts', setting.max_login_attempts) or 5)

        # Uploads
        if 'platform_logo' in request.FILES:
            setting.platform_logo = request.FILES['platform_logo']
        if 'platform_favicon' in request.FILES:
            setting.platform_favicon = request.FILES['platform_favicon']

        setting.save()
        messages.success(request, "Platform settings have been updated successfully.")
        return redirect('superadmin:system_settings')

    context = {
        'setting': setting,
        'title': 'System Settings',
    }
    return render(request, 'superadmin/settings.html', context)


# ==============================================================================
# BACKUP & DISASTER RECOVERY MANAGEMENT
# ==============================================================================

@login_required
@superadmin_required
def backup_manager_view(request):
    """
    Main Disaster Recovery & Backup dashboard. Allows full platform backups,
    single gym backups, media exports, upload inspection, and one-click restores.
    """
    # 1. Sync disk files with logs
    backup_service.sync_backups_with_disk()

    # 2. Gather system storage metrics
    storage_stats = backup_service.get_system_storage_stats()

    # 3. Gyms directory for selective backup
    gyms = Gym.objects.annotate(
        member_total=Count('member', filter=Q(member__is_deleted=False), distinct=True)
    ).order_by('name')

    # 4. Filterable Backups Registry
    backups_qs = BackupLog.objects.select_related('gym', 'created_by').order_by('-created_at')

    q = request.GET.get('q', '').strip()
    if q:
        backups_qs = backups_qs.filter(Q(filename__icontains=q) | Q(gym_name__icontains=q) | Q(notes__icontains=q))

    b_type = request.GET.get('type', '').strip()
    if b_type in ['full', 'gym', 'media']:
        backups_qs = backups_qs.filter(backup_type=b_type)

    paginator = Paginator(backups_qs, 15)
    page_number = request.GET.get('page')
    backups = paginator.get_page(page_number)

    setting = SystemSetting.get_settings()

    context = {
        'storage_stats': storage_stats,
        'gyms': gyms,
        'backups': backups,
        'setting': setting,
        'search_query': q,
        'type_filter': b_type,
        'title': 'Backup & Restore Center',
    }
    return render(request, 'superadmin/backup_manager.html', context)


@login_required
@superadmin_required
@require_POST
def create_backup_action(request):
    """
    Handles generation of Full, Selected Gym, or Media backups.
    """
    scope = request.POST.get('backup_scope', 'full')  # 'full', 'gym', 'media'
    gym_id = request.POST.get('gym_id')
    include_db = request.POST.get('include_db') == '1' or request.POST.get('include_db') == 'on'
    include_media = request.POST.get('include_media') == '1' or request.POST.get('include_media') == 'on'
    notes = request.POST.get('notes', '').strip()
    download_now = request.POST.get('download_now') == '1' or request.POST.get('download_now') == 'true'

    try:
        if scope == 'gym':
            if not gym_id:
                messages.error(request, "Please select a specific gym to backup.")
                return redirect('superadmin:backup_manager')
            gym = get_object_or_404(Gym, id=gym_id)
            log, filepath = backup_service.create_gym_backup(
                gym=gym,
                include_media=include_media,
                user=request.user,
                notes=notes
            )
            msg = f"Backup for gym '{gym.name}' created successfully ({log.file_size_display})."

        elif scope == 'media':
            gym = Gym.objects.filter(id=gym_id).first() if gym_id else None
            log, filepath = backup_service.create_media_only_backup(
                gym=gym,
                user=request.user,
                notes=notes
            )
            msg = f"Media archive created successfully ({log.file_size_display})."

        else:
            # Full Project
            log, filepath = backup_service.create_full_backup(
                include_db=include_db if ('include_db' in request.POST) else True,
                include_media=include_media,
                user=request.user,
                notes=notes
            )
            msg = f"Full system backup created successfully ({log.file_size_display})."

        if download_now and os.path.exists(filepath):
            return FileResponse(open(filepath, 'rb'), as_attachment=True, filename=log.filename)

        messages.success(request, msg)

    except Exception as e:
        messages.error(request, f"Failed to generate backup: {str(e)}")

    return redirect('superadmin:backup_manager')


@login_required
@superadmin_required
def download_backup_action(request, backup_id):
    """
    Direct attachment download for a stored backup file.
    """
    log = get_object_or_404(BackupLog, id=backup_id)
    if not os.path.exists(log.file_path):
        messages.error(request, f"Backup file '{log.filename}' could not be found on server disk.")
        return redirect('superadmin:backup_manager')

    return FileResponse(open(log.file_path, 'rb'), as_attachment=True, filename=log.filename)


@login_required
@superadmin_required
@require_POST
def delete_backup_action(request, backup_id):
    """
    Permanently deletes a backup file from disk and removes its log entry.
    """
    log = get_object_or_404(BackupLog, id=backup_id)
    filename = log.filename
    if os.path.exists(log.file_path):
        try:
            os.remove(log.file_path)
        except OSError as e:
            pass

    log.delete()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f"Backup '{filename}' deleted successfully."})

    messages.success(request, f"Backup archive '{filename}' deleted permanently.")
    return redirect('superadmin:backup_manager')


@login_required
@superadmin_required
def inspect_backup_api(request):
    """
    API endpoint to inspect an archive file (.zip, .json, .sqlite3)
    and return structural metadata before performing restore.
    """
    backup_id = request.GET.get('backup_id') or request.POST.get('backup_id')

    # Case 1: Inspect existing backup on server
    if backup_id:
        log = get_object_or_404(BackupLog, id=backup_id)
        if not os.path.exists(log.file_path):
            return JsonResponse({'is_valid': False, 'error': 'Backup file not found on disk.'})
        report = backup_service.inspect_backup_file(log.file_path)
        report['filename'] = log.filename
        report['backup_id'] = log.id
        return JsonResponse(report)

    # Case 2: Inspect newly uploaded file
    if request.method == 'POST' and 'backup_file' in request.FILES:
        uploaded = request.FILES['backup_file']
        temp_dir = os.path.join(backup_service.BACKUP_DIR, 'temp_inspect')
        os.makedirs(temp_dir, exist_ok=True)
        temp_path = os.path.join(temp_dir, f"inspect_{uploaded.name}")

        with open(temp_path, 'wb+') as dest:
            for chunk in uploaded.chunks():
                dest.write(chunk)

        try:
            report = backup_service.inspect_backup_file(temp_path)
            report['filename'] = uploaded.name
            return JsonResponse(report)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    return JsonResponse({'is_valid': False, 'error': 'No backup file or ID provided for inspection.'})


@login_required
@superadmin_required
@require_POST
def restore_backup_action(request):
    """
    Executes restore from an existing backup ID or uploaded backup archive.
    """
    confirm_text = request.POST.get('confirm_text', '').strip().upper()
    if confirm_text != 'RESTORE':
        messages.error(request, "Restoration aborted: Confirmation word must be exactly 'RESTORE'.")
        return redirect('superadmin:backup_manager')

    backup_id = request.POST.get('backup_id')
    filepath = None
    is_uploaded = False

    if backup_id:
        log = get_object_or_404(BackupLog, id=backup_id)
        if not os.path.exists(log.file_path):
            messages.error(request, "Backup file not found on server disk.")
            return redirect('superadmin:backup_manager')
        filepath = log.file_path

    elif 'backup_file' in request.FILES:
        uploaded = request.FILES['backup_file']
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        save_name = f"uploaded_{timestamp}_{uploaded.name}"
        filepath = os.path.join(backup_service.BACKUP_DIR, save_name)

        with open(filepath, 'wb+') as dest:
            for chunk in uploaded.chunks():
                dest.write(chunk)
        is_uploaded = True

    if not filepath or not os.path.exists(filepath):
        messages.error(request, "No valid backup file was provided for restoration.")
        return redirect('superadmin:backup_manager')

    current_user_id = request.user.id if request.user.is_authenticated else None

    # Execute restore
    success, message = backup_service.restore_backup(filepath, user=request.user)

    if success:
        # Crucial Session Fix:
        # When a full database is restored, the `django_session` table is replaced.
        # The user's active session key does not exist in the newly restored database,
        # which causes Django's SessionMiddleware to raise SessionInterrupted on response.
        # By calling request.session.save(must_create=True), we ensure the session is
        # safely inserted into the restored database table.
        if current_user_id:
            try:
                from django.contrib.auth.models import User
                if User.objects.filter(id=current_user_id).exists():
                    request.session.save(must_create=True)
                else:
                    request.session.cycle_key()
            except Exception:
                try:
                    request.session.cycle_key()
                except Exception:
                    pass

        messages.success(request, f"Restore Successful: {message}")
    else:
        messages.error(request, f"Restore Failed: {message}")

    return redirect('superadmin:backup_manager')


