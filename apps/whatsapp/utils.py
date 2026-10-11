import re
import urllib.parse
from datetime import date, datetime
from django.utils import timezone


def clean_whatsapp_phone(phone):
    """
    Cleans and formats a phone number for wa.me URL.
    Wa.me format requires numbers without '+', dashes, or spaces.
    If 10 digits (standard Indian mobile), prepends '91'.
    """
    if not phone:
        return ""
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def build_whatsapp_url(phone, message):
    """
    Constructs a wa.me URL with properly URL-encoded message text.
    """
    cleaned_phone = clean_whatsapp_phone(phone)
    if not cleaned_phone:
        return "#"
    encoded_text = urllib.parse.quote(message)
    return f"https://wa.me/{cleaned_phone}?text={encoded_text}"


def _get_gym_name(gym=None, obj=None):
    """
    Helper to extract a friendly gym name with graceful fallbacks.
    """
    if gym and getattr(gym, 'name', None):
        return gym.name.strip()
    if obj and hasattr(obj, 'gym') and obj.gym and getattr(obj.gym, 'name', None):
        return obj.gym.name.strip()
    return "our gym"


def _format_date(d):
    """
    Helper to format a date into a clean string like '01 Oct 2026'.
    """
    if not d:
        return "recently"
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(d, date):
        return d.strftime("%d %b %Y")
    return str(d)


def get_expired_membership_message(member, gym=None):
    """
    Industry-ready WhatsApp message for expired memberships.
    """
    gym_name = _get_gym_name(gym, member)
    member_name = getattr(member, 'name', None) or f"{getattr(member, 'first_name', '')} {getattr(member, 'last_name', '')}".strip() or "Valued Member"
    
    plan_title = "Gym Membership"
    expiry_date_str = "recently"
    
    latest_membership = getattr(member, 'latest_membership', None)
    if latest_membership:
        if getattr(latest_membership, 'plan', None) and getattr(latest_membership.plan, 'title', None):
            plan_title = latest_membership.plan.title
        end_date = latest_membership.get_end_date() if hasattr(latest_membership, 'get_end_date') else None
        if end_date:
            expiry_date_str = _format_date(end_date)
            
    message = (
        f"Hello *{member_name}*,\n\n"
        f"Greetings from *{gym_name}*! 🏋️\n\n"
        f"We noticed that your gym membership (*{plan_title}*) expired on *{expiry_date_str}*.\n\n"
        f"Consistency is key to achieving your fitness and health goals, and we would love to see you back on track!\n\n"
        f"👉 Please visit our front desk or reply directly to this message to renew your membership and continue your workouts.\n\n"
        f"Stay fit, stay strong! 💪\n"
        f"— *Team {gym_name}*"
    )
    return message


def get_expiring_soon_message(member, gym=None):
    """
    Industry-ready WhatsApp message for memberships expiring soon.
    """
    gym_name = _get_gym_name(gym, member)
    member_name = getattr(member, 'name', None) or f"{getattr(member, 'first_name', '')} {getattr(member, 'last_name', '')}".strip() or "Valued Member"
    
    plan_title = "Gym Membership"
    expiry_date_str = "soon"
    
    latest_membership = getattr(member, 'latest_membership', None)
    if latest_membership:
        if getattr(latest_membership, 'plan', None) and getattr(latest_membership.plan, 'title', None):
            plan_title = latest_membership.plan.title
        end_date = latest_membership.get_end_date() if hasattr(latest_membership, 'get_end_date') else None
        if end_date:
            expiry_date_str = _format_date(end_date)
            
    message = (
        f"Hello *{member_name}*,\n\n"
        f"Greetings from *{gym_name}*! 🏋️\n\n"
        f"This is a friendly reminder that your gym membership (*{plan_title}*) is scheduled to expire on *{expiry_date_str}*.\n\n"
        f"Renewing early ensures uninterrupted access to the gym, equipment, and your personal fitness routine.\n\n"
        f"👉 Please visit the front desk or reply to this message to renew your plan today.\n\n"
        f"Keep up the great progress! 🌟\n"
        f"— *Team {gym_name}*"
    )
    return message


def get_pending_due_message(member, due_amount, gym=None, plan_name=None):
    """
    Industry-ready WhatsApp message for pending fee dues.
    """
    gym_name = _get_gym_name(gym, member)
    member_name = getattr(member, 'name', None) or f"{getattr(member, 'first_name', '')} {getattr(member, 'last_name', '')}".strip() or "Valued Member"
    
    plan_context = f" for *{plan_name}*" if plan_name else ""
    
    message = (
        f"Hello *{member_name}*,\n\n"
        f"Greetings from *{gym_name}*! 🏋️\n\n"
        f"This is a polite reminder regarding your pending fee balance of *₹{due_amount}*{plan_context}.\n\n"
        f"Kindly arrange to clear the balance at your earliest convenience to keep your account up to date. You can settle this at our front desk.\n\n"
        f"If you have already completed this payment, please disregard this message.\n\n"
        f"Thank you for your cooperation! 🙏\n"
        f"— *Team {gym_name}*"
    )
    return message


def get_member_profile_message(member, gym=None, due_amount=0):
    """
    Context-aware message for member profile or general member list.
    Prioritizes:
    1. Expired membership
    2. Expiring soon membership (within next 7 days)
    3. Pending dues
    4. General member support & check-in
    """
    status = getattr(member, 'current_status', None)
    latest_membership = getattr(member, 'latest_membership', None)
    
    if status == 'Expired':
        return get_expired_membership_message(member, gym)
        
    if latest_membership and hasattr(latest_membership, 'get_end_date'):
        end_date = latest_membership.get_end_date()
        today = timezone.localdate()
        if end_date and today <= end_date <= today + timezone.timedelta(days=7):
            return get_expiring_soon_message(member, gym)
            
    if due_amount and float(due_amount) > 0:
        return get_pending_due_message(member, due_amount, gym)
        
    gym_name = _get_gym_name(gym, member)
    member_name = getattr(member, 'name', None) or f"{getattr(member, 'first_name', '')} {getattr(member, 'last_name', '')}".strip() or "Valued Member"
    
    message = (
        f"Hello *{member_name}*,\n\n"
        f"Greetings from *{gym_name}*! 🏋️\n\n"
        f"We hope you are enjoying your workouts and fitness journey with us.\n\n"
        f"If you have any questions, need workout guidance, or require assistance with your membership, our team is always happy to help.\n\n"
        f"Have a powerful workout session! 💪\n"
        f"— *Team {gym_name}*"
    )
    return message


def get_birthday_message(member, is_today=True, gym=None):
    """
    Warm, professional birthday greeting for gym members.
    """
    gym_name = _get_gym_name(gym, member)
    member_name = getattr(member, 'name', None) or f"{getattr(member, 'first_name', '')} {getattr(member, 'last_name', '')}".strip() or "Member"
    
    if is_today:
        return (
            f"Happy Birthday *{member_name}*! 🎂🎉\n\n"
            f"Wishing you a fantastic day filled with joy, great health, and continued strength from all of us at *{gym_name}*! "
            f"Keep crushing your fitness goals! 💪✨\n\n"
            f"— *Team {gym_name}*"
        )
    return (
        f"Advance Happy Birthday *{member_name}*! 🎂🎉\n\n"
        f"Wishing you continued health, strength, and happiness in the upcoming year from the entire team at *{gym_name}*! 💪\n\n"
        f"— *Team {gym_name}*"
    )


def get_enquiry_followup_message(enquiry, gym=None):
    """
    Professional follow-up message for prospective gym leads/enquiries.
    """
    gym_name = _get_gym_name(gym, enquiry)
    enquiry_name = getattr(enquiry, 'name', None) or "there"
    
    return (
        f"Hello *{enquiry_name}*,\n\n"
        f"Greetings from *{gym_name}*! 🏋️\n\n"
        f"Thank you for your interest in our gym and fitness programs. "
        f"We would love to welcome you for a complimentary facility tour and trial session.\n\n"
        f"When would be a convenient time for you to drop by? Feel free to reply directly to this message!\n\n"
        f"Best regards,\n"
        f"— *Team {gym_name}*"
    )
