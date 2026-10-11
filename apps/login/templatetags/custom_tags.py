from django import template
from apps.login.models import SubAdmin, SubAdminPermission

register = template.Library()

@register.filter(name='has_permission')
def has_permission(user, perm_name):
    """
    Usage in template:
    {% if request.user|has_permission:'delete_member' %}
        ...
    {% endif %}
    """
    if user.is_superuser:
        return True
        
    if hasattr(user, 'gymadmin'):
        return True
        
    if hasattr(user, 'subadmin'):
        return SubAdminPermission.objects.filter(
            sub_admin=user.subadmin, 
            permission_name=perm_name
        ).exists()
        
    return False

APP_MODULE_MAP = {
    'member': 'members',
    'members': 'members',
    'trainer': 'trainers',
    'trainers': 'trainers',
    'expense': 'expenses',
    'expenses': 'expenses',
    'event': 'events',
    'events': 'events',
    'setting': 'settings',
    'settings': 'settings',
    'management': 'management',
    'billing': 'billing',
    'inventory': 'inventory',
    'attendance': 'attendance',
    'enquiry': 'enquiry',
}

@register.filter(name='has_module_permission')
def has_module_permission(user, app_label):
    """
    Usage:
    {% if request.user|has_module_permission:'management' %}
        ...
    {% endif %}
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True
        
    if hasattr(user, 'gymadmin'):
        return True
        
    if hasattr(user, 'subadmin'):
        from django.contrib.auth.models import Permission
        
        norm_key = str(app_label).strip().lower()
        real_app = APP_MODULE_MAP.get(norm_key, norm_key)
        
        user_perms = list(SubAdminPermission.objects.filter(
            sub_admin=user.subadmin
        ).values_list('permission_name', flat=True))
        
        if not user_perms:
            return False

        # 1. Match by Django content_type app_label (e.g. 'management', 'events', 'billing', 'inventory')
        if Permission.objects.filter(
            content_type__app_label=real_app,
            codename__in=user_perms
        ).exists():
            return True

        # 2. Match by model name (e.g. 'dietplan', 'workoutplan', 'membershipplan', 'event', 'invoice')
        if Permission.objects.filter(
            content_type__model=norm_key,
            codename__in=user_perms
        ).exists():
            return True

        # 3. Fallback substring match
        return SubAdminPermission.objects.filter(
            sub_admin=user.subadmin,
            permission_name__icontains=norm_key
        ).exists()
        
    return False


# ---------------------------------------------------------------------------
# WhatsApp URL & Industry-Ready Messaging Filters
# ---------------------------------------------------------------------------
try:
    from apps.whatsapp.templatetags.whatsapp_tags import (
        whatsapp_expired_url,
        whatsapp_expiring_soon_url,
        whatsapp_due_url,
        whatsapp_profile_url,
        whatsapp_birthday_url,
        whatsapp_enquiry_url,
    )
    register.filter('whatsapp_expired_url', whatsapp_expired_url)
    register.filter('whatsapp_expiring_soon_url', whatsapp_expiring_soon_url)
    register.filter('whatsapp_due_url', whatsapp_due_url)
    register.filter('whatsapp_profile_url', whatsapp_profile_url)
    register.filter('whatsapp_birthday_url', whatsapp_birthday_url)
    register.filter('whatsapp_enquiry_url', whatsapp_enquiry_url)
except Exception:
    pass

