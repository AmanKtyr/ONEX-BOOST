from django import template
from apps.whatsapp.utils import (
    build_whatsapp_url,
    get_expired_membership_message,
    get_expiring_soon_message,
    get_pending_due_message,
    get_member_profile_message,
    get_birthday_message,
    get_enquiry_followup_message,
)

register = template.Library()


@register.filter(name='whatsapp_expired_url')
def whatsapp_expired_url(member, gym=None):
    """
    Returns a wa.me URL with a pre-filled professional expired membership message.
    Usage: {{ member|whatsapp_expired_url:gym }}
    """
    if not member:
        return "#"
    msg = get_expired_membership_message(member, gym=gym)
    return build_whatsapp_url(getattr(member, 'mobile_number', ''), msg)


@register.filter(name='whatsapp_expiring_soon_url')
def whatsapp_expiring_soon_url(member, gym=None):
    """
    Returns a wa.me URL with a pre-filled professional expiring soon membership message.
    Usage: {{ member|whatsapp_expiring_soon_url:gym }}
    """
    if not member:
        return "#"
    msg = get_expiring_soon_message(member, gym=gym)
    return build_whatsapp_url(getattr(member, 'mobile_number', ''), msg)


@register.filter(name='whatsapp_due_url')
def whatsapp_due_url(due_or_member, gym=None, amount=None):
    """
    Returns a wa.me URL for pending fee reminders.
    Accepts either:
    - a due object (MembershipHistory or PersonalTrainer instance with .member)
    - a Member instance (with amount provided)
    Usage: {{ due|whatsapp_due_url:gym }}
    """
    if not due_or_member:
        return "#"

    member = None
    due_amt = 0
    plan_name = None

    if hasattr(due_or_member, 'member'):
        member = due_or_member.member
        if hasattr(due_or_member, 'due_amount'):
            due_amt = due_or_member.due_amount() if callable(due_or_member.due_amount) else due_or_member.due_amount
        elif hasattr(due_or_member, 'total_amount') and hasattr(due_or_member, 'paid_amount'):
            due_amt = due_or_member.total_amount - due_or_member.paid_amount

        if hasattr(due_or_member, 'plan') and due_or_member.plan:
            plan_name = getattr(due_or_member.plan, 'title', str(due_or_member.plan))
        elif hasattr(due_or_member, 'trainer') and due_or_member.trainer:
            plan_name = f"Personal Training ({due_or_member.trainer.name})"
    else:
        member = due_or_member
        due_amt = amount or getattr(member, 'total_due', 0)

    if not member:
        return "#"

    msg = get_pending_due_message(member, due_amt, gym=gym, plan_name=plan_name)
    return build_whatsapp_url(getattr(member, 'mobile_number', ''), msg)


@register.filter(name='whatsapp_profile_url')
def whatsapp_profile_url(member, due_amount=0, gym=None):
    """
    Returns a context-aware wa.me URL for a member.
    Prioritizes Expired > Expiring Soon > Due > Active Support.
    Usage: {{ member|whatsapp_profile_url:due_amount }}
    """
    if not member:
        return "#"
    msg = get_member_profile_message(member, gym=gym, due_amount=due_amount)
    return build_whatsapp_url(getattr(member, 'mobile_number', ''), msg)


@register.filter(name='whatsapp_birthday_url')
def whatsapp_birthday_url(member, timing='today', gym=None):
    """
    Returns a birthday wish wa.me URL for a member.
    timing: 'today' or 'upcoming'
    Usage: {{ member|whatsapp_birthday_url:'today' }}
    """
    if not member:
        return "#"
    is_today = (str(timing).strip().lower() == 'today')
    msg = get_birthday_message(member, is_today=is_today, gym=gym)
    return build_whatsapp_url(getattr(member, 'mobile_number', ''), msg)


@register.filter(name='whatsapp_enquiry_url')
def whatsapp_enquiry_url(enquiry, gym=None):
    """
    Returns an enquiry follow-up wa.me URL.
    Usage: {{ enquiry|whatsapp_enquiry_url:gym }}
    """
    if not enquiry:
        return "#"
    msg = get_enquiry_followup_message(enquiry, gym=gym)
    return build_whatsapp_url(getattr(enquiry, 'mobile_number', ''), msg)
