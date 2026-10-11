from datetime import date
from django.utils import timezone
from apps.superadmin.models import Gym, GymAdmin, SubscriptionPlan, GymSubscription, SystemSetting
from apps.members.models import Member
from apps.trainers.models import Trainer
from apps.login.models import SubAdmin


def get_gym_active_subscription(gym):
    """
    Returns the active GymSubscription and associated SubscriptionPlan for the given gym.
    If no active subscription is found, falls back to the latest subscription.
    Returns (subscription, plan) or (None, None).
    """
    if not gym:
        return None, None

    today = timezone.now().date()
    # Try active subscription within valid date range
    active_sub = GymSubscription.objects.filter(
        gym=gym,
        start_date__lte=today,
        end_date__gte=today,
        is_deleted=False
    ).select_related('subscription').order_by('-end_date').first()

    if active_sub:
        return active_sub, active_sub.subscription

    # Otherwise fetch latest subscription
    latest_sub = GymSubscription.objects.filter(
        gym=gym,
        is_deleted=False
    ).select_related('subscription').order_by('-end_date').first()

    if latest_sub:
        return latest_sub, latest_sub.subscription

    return None, None


def get_gym_quota_status(gym):
    """
    Computes a complete, structured dictionary with current resource usage,
    assigned plan limitations, capacity percentages, warnings, and feature entitlements.
    """
    if not gym:
        return None

    today = timezone.now().date()
    subscription, plan = get_gym_active_subscription(gym)

    is_active = False
    is_expired = False
    days_remaining = 0
    end_date = None

    if subscription:
        end_date = subscription.end_date
        if end_date:
            if end_date >= today:
                is_active = True
                days_remaining = (end_date - today).days
            else:
                is_expired = True
                days_remaining = 0

    # Resource counts
    total_members = Member.objects.filter(gym=gym, is_deleted=False).count()
    active_members = Member.objects.filter(
        gym=gym,
        is_deleted=False,
        membership_history__status='active',
        membership_history__is_deleted=False
    ).distinct().count()

    total_trainers = Trainer.objects.filter(gym=gym).count()
    
    # Admins: 1 primary GymAdmin + SubAdmins
    subadmins_count = SubAdmin.objects.filter(gym=gym).count()
    has_primary_admin = GymAdmin.objects.filter(gym=gym).exists()
    total_admins = subadmins_count + (1 if has_primary_admin else 0)

    # Quotas from plan (0 = Unlimited)
    max_members = plan.max_members if plan else 0
    max_trainers = plan.max_trainers if plan else 0
    max_admins = plan.max_admins if plan else 0

    # Percentages and limit checks
    def calc_stat(current, max_val):
        if max_val == 0:
            return {
                'current': current,
                'max': 0,
                'display_max': 'Unlimited',
                'percent': 0,
                'is_unlimited': True,
                'is_limit_reached': False,
                'is_warning': False,
                'available': '∞'
            }
        percent = min(100, round((current / max_val) * 100))
        is_reached = current >= max_val
        is_warning = percent >= 80 and not is_reached
        available = max(0, max_val - current)
        return {
            'current': current,
            'max': max_val,
            'display_max': str(max_val),
            'percent': percent,
            'is_unlimited': False,
            'is_limit_reached': is_reached,
            'is_warning': is_warning,
            'available': available
        }

    members_stat = calc_stat(total_members, max_members)
    members_stat['active_members'] = active_members
    trainers_stat = calc_stat(total_trainers, max_trainers)
    admins_stat = calc_stat(total_admins, max_admins)

    # Feature entitlements
    features = {
        'whatsapp_support': plan.has_whatsapp_support if plan else True,
        'biometric_attendance': plan.has_biometric_attendance if plan else True,
        'diet_workout': plan.has_diet_workout if plan else True,
        'billing_invoicing': plan.has_billing_invoicing if plan else True,
        'expense_management': plan.has_expense_management if plan else True,
        'inventory_management': plan.has_inventory_management if plan else True,
        'reports_analytics': plan.has_reports_analytics if plan else True,
        'crm_leads': plan.has_crm_leads if plan else True,
        'staff_salary': plan.has_staff_salary if plan else True,
    }

    # Overall system health / warning flag
    has_any_warning = members_stat['is_warning'] or trainers_stat['is_warning'] or admins_stat['is_warning']
    has_any_limit_reached = members_stat['is_limit_reached'] or trainers_stat['is_limit_reached'] or admins_stat['is_limit_reached']

    setting = SystemSetting.get_settings()
    support_phone = setting.support_phone or "+91 88875 58415"

    return {
        'has_subscription': subscription is not None,
        'subscription': subscription,
        'plan': plan,
        'plan_name': plan.name if plan else 'Starter Standard',
        'plan_tier': plan.get_plan_tier_display() if plan else 'Growth',
        'price': plan.price if plan else 0,
        'color_theme': plan.color_theme if plan else 'blue',
        'is_active': is_active,
        'is_expired': is_expired,
        'end_date': end_date,
        'days_remaining': days_remaining,
        'members': members_stat,
        'trainers': trainers_stat,
        'admins': admins_stat,
        'features': features,
        'has_warning': has_any_warning,
        'has_limit_reached': has_any_limit_reached,
        'support_phone': support_phone,
    }


def check_resource_quota(gym, resource_type):
    """
    Validates whether the gym can add another entity of resource_type ('member', 'trainer', 'admin').
    Returns: (is_allowed: bool, message: str, quota_data: dict)
    """
    if not gym:
        return True, "", {}

    quota = get_gym_quota_status(gym)
    if not quota:
        return True, "", {}

    plan_name = quota.get('plan_name', 'Subscription Plan')
    setting = SystemSetting.get_settings()
    support_phone = setting.support_phone or "+91 88875 58415"

    if resource_type == 'member':
        stat = quota['members']
        if not stat['is_unlimited'] and stat['is_limit_reached']:
            msg = (
                f"Member Quota Full ({stat['current']}/{stat['max']} Members)! "
                f"Your gym '{gym.name}' has reached the maximum capacity allowed on the '{plan_name}'. "
                f"Please upgrade your SaaS subscription or archive inactive members to add new members."
            )
            return False, msg, quota

    elif resource_type == 'trainer':
        stat = quota['trainers']
        if not stat['is_unlimited'] and stat['is_limit_reached']:
            msg = (
                f"Trainer Quota Full ({stat['current']}/{stat['max']} Trainers)! "
                f"Your gym has reached the maximum trainer limit for the '{plan_name}'. "
                f"Please upgrade your plan to register more trainers."
            )
            return False, msg, quota

    elif resource_type == 'admin':
        stat = quota['admins']
        if not stat['is_unlimited'] and stat['is_limit_reached']:
            msg = (
                f"Admin Account Quota Full ({stat['current']}/{stat['max']} Accounts)! "
                f"Your gym has reached the limit for administrator/staff accounts on the '{plan_name}'. "
                f"Please upgrade your plan to create more sub-admin logins."
            )
            return False, msg, quota

    return True, "", quota
