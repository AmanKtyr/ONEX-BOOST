from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.models import User
from .models import PlatformNotification, NotificationUserStatus, Gym, GymAdmin
from apps.login.models import SubAdmin
from apps.members.models import Member
from apps.trainers.models import Trainer


def get_user_context(user):
    """
    Resolves the gym and role for any user in the system.
    Returns dict: {'role': str, 'gym': Gym or None}
    """
    if not user or not user.is_authenticated:
        return {'role': 'anonymous', 'gym': None}

    if user.is_superuser:
        return {'role': 'superadmin', 'gym': None}

    # 1. Gym Admin
    ga = GymAdmin.objects.filter(user=user).select_related('gym').first()
    if ga:
        return {'role': 'gym_admin', 'gym': ga.gym}

    # 2. Sub Admin / Staff
    sa = SubAdmin.objects.filter(user=user).select_related('gym').first()
    if sa:
        return {'role': 'staff', 'gym': sa.gym}

    # 3. Trainer
    trainer = getattr(user, 'trainer_profile', None)
    if trainer and trainer.gym:
        return {'role': 'trainer', 'gym': trainer.gym}

    # 4. Member
    member = getattr(user, 'member_profile', None)
    if member and member.gym:
        return {'role': 'member', 'gym': member.gym}

    return {'role': 'user', 'gym': None}


def get_user_applicable_notifications_qs(user):
    """
    Returns the QuerySet of active, unexpired notifications targeted to the given user.
    """
    if not user or not user.is_authenticated:
        return PlatformNotification.objects.none()

    now = timezone.now()
    base_qs = PlatformNotification.objects.filter(
        is_active=True
    ).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )

    # Superadmin should only receive system-wide announcements or notifications specifically addressed to them
    if user.is_superuser:
        return base_qs.filter(
            Q(target_type='all') | Q(target_type='specific_user', target_user=user)
        ).distinct()

    ctx = get_user_context(user)
    role = ctx['role']
    gym = ctx['gym']

    # Build Q filters based on audience matching
    q_filter = Q(target_type='all') | Q(target_type='specific_user', target_user=user)

    is_gym_staff = role in ('gym_admin', 'staff')
    is_member = role == 'member'

    # Broad categories
    if is_gym_staff:
        q_filter |= Q(target_type='all_gyms')
    if is_member:
        q_filter |= Q(target_type='all_members')

    # Gym-specific categories
    if gym:
        q_filter |= Q(target_type='specific_gym', target_gym=gym)
        if is_gym_staff:
            q_filter |= Q(target_type='specific_gym_staff', target_gym=gym)
        if is_member:
            q_filter |= Q(target_type='specific_gym_members', target_gym=gym)

    return base_qs.filter(q_filter).distinct()


def get_unread_notifications_count(user):
    """
    Returns the number of unread notifications for the user.
    """
    if not user or not user.is_authenticated:
        return 0

    qs = get_user_applicable_notifications_qs(user)
    # Exclude those marked read
    read_ids = NotificationUserStatus.objects.filter(
        user=user,
        is_read=True
    ).values_list('notification_id', flat=True)

    return qs.exclude(id__in=read_ids).count()


def get_recent_notifications(user, limit=5):
    """
    Returns list of recent notifications annotated with user read state.
    """
    if not user or not user.is_authenticated:
        return []

    qs = list(get_user_applicable_notifications_qs(user)[:limit])
    if not qs:
        return []

    statuses = {
        s.notification_id: s
        for s in NotificationUserStatus.objects.filter(user=user, notification__in=qs)
    }

    result = []
    for n in qs:
        status = statuses.get(n.id)
        is_read = status.is_read if status else False
        result.append({
            'id': n.id,
            'title': n.title,
            'message': n.message,
            'notification_type': n.notification_type,
            'image_url': n.image.url if n.image else None,
            'action_label': n.action_label,
            'action_url': n.action_url,
            'show_popup': n.show_popup,
            'created_at': n.created_at,
            'is_read': is_read,
        })
    return result


def get_active_popup_for_user(user, session=None):
    """
    Returns the active popup announcement that the user is eligible to see based on frequency settings:
    - 'once': Shown once until dismissed.
    - 'every_login': Shown once per login/session until expired.
    - 'fixed_count': Shown up to max_popup_views times until expired.
    - 'until_expired': Shown on every login session until expired.
    """
    if not user or not user.is_authenticated:
        return None

    qs = get_user_applicable_notifications_qs(user).filter(show_popup=True)
    if not qs.exists():
        return None

    seen_session_ids = set()
    if session is not None:
        seen_session_ids = set(session.get('seen_popup_ids', []))

    user_statuses = {
        s.notification_id: s
        for s in NotificationUserStatus.objects.filter(user=user, notification__in=qs)
    }

    eligible_popup = None
    for popup in qs:
        status = user_statuses.get(popup.id)
        view_count = status.popup_view_count if status else 0
        acknowledged = status.popup_acknowledged if status else False

        # Session check to avoid annoying user on every second page reload in same session
        if popup.id in seen_session_ids:
            continue

        freq = popup.popup_frequency or 'once'

        if freq == 'once':
            if not acknowledged:
                eligible_popup = popup
                break

        elif freq == 'every_login' or freq == 'until_expired':
            # Display once per login session until expired (qs already checks not expired)
            eligible_popup = popup
            break

        elif freq == 'fixed_count':
            max_views = popup.max_popup_views or 1
            if view_count < max_views:
                eligible_popup = popup
                break

    if not eligible_popup:
        return None

    # Track in session so it doesn't pop up again on immediate page refresh in the same session
    if session is not None:
        current_seen = list(session.get('seen_popup_ids', []))
        if eligible_popup.id not in current_seen:
            current_seen.append(eligible_popup.id)
            session['seen_popup_ids'] = current_seen
            if hasattr(session, 'modified'):
                session.modified = True

    return {
        'id': eligible_popup.id,
        'title': eligible_popup.title,
        'message': eligible_popup.message,
        'notification_type': eligible_popup.notification_type,
        'image_url': eligible_popup.image.url if eligible_popup.image else None,
        'popup_frequency': eligible_popup.popup_frequency,
        'is_dismissible': eligible_popup.is_dismissible,
        'action_label': eligible_popup.action_label,
        'action_url': eligible_popup.action_url,
        'created_at': eligible_popup.created_at.strftime('%d %b %Y, %I:%M %p'),
    }


def acknowledge_popup(user, notification_id, session=None):
    """
    Records popup view / dismissal and updates frequency counters.
    """
    if not user or not user.is_authenticated:
        return False

    now = timezone.now()
    notification = PlatformNotification.objects.filter(id=notification_id).first()
    if not notification:
        return False

    status, created = NotificationUserStatus.objects.get_or_create(
        user=user,
        notification=notification,
        defaults={
            'popup_acknowledged': False,
            'popup_view_count': 1,
            'popup_last_shown_at': now,
            'is_read': True,
            'read_at': now,
        }
    )

    if not created:
        status.popup_view_count = (status.popup_view_count or 0) + 1
        status.popup_last_shown_at = now
        status.is_read = True
        if not status.read_at:
            status.read_at = now

    freq = notification.popup_frequency or 'once'
    if freq == 'once':
        status.popup_acknowledged = True
        status.popup_acknowledged_at = now
    elif freq == 'fixed_count':
        max_views = notification.max_popup_views or 1
        if status.popup_view_count >= max_views:
            status.popup_acknowledged = True
            status.popup_acknowledged_at = now

    status.save()

    if session is not None:
        current_seen = list(session.get('seen_popup_ids', []))
        if notification_id not in current_seen:
            current_seen.append(notification_id)
            session['seen_popup_ids'] = current_seen
            if hasattr(session, 'modified'):
                session.modified = True

    return True


def mark_notification_as_read(user, notification_id):
    """
    Marks a notification as read by the user.
    """
    if not user or not user.is_authenticated:
        return False

    now = timezone.now()
    status, created = NotificationUserStatus.objects.get_or_create(
        user=user,
        notification_id=notification_id,
        defaults={'is_read': True, 'read_at': now}
    )
    if not created and not status.is_read:
        status.is_read = True
        status.read_at = now
        status.save(update_fields=['is_read', 'read_at', 'updated_at'])

    return True


def mark_all_notifications_as_read(user):
    """
    Marks all currently applicable notifications as read.
    """
    if not user or not user.is_authenticated:
        return 0

    qs = get_user_applicable_notifications_qs(user)
    now = timezone.now()
    updated_count = 0

    for n in qs:
        status, created = NotificationUserStatus.objects.get_or_create(
            user=user,
            notification=n,
            defaults={'is_read': True, 'read_at': now}
        )
        if not created and not status.is_read:
            status.is_read = True
            status.read_at = now
            status.save(update_fields=['is_read', 'read_at', 'updated_at'])
            updated_count += 1
        elif created:
            updated_count += 1

    return updated_count


def estimate_audience(target_type, target_gym_id=None, target_user_id=None):
    """
    Computes an estimated recipient count breakdown for previewing in the compose UI.
    """
    result = {
        'total': 0,
        'admins': 0,
        'staff': 0,
        'members': 0,
        'trainers': 0,
        'description': '',
    }

    if target_type == 'specific_user':
        if target_user_id:
            try:
                u = User.objects.get(id=target_user_id)
                result['total'] = 1
                result['description'] = f"1 individual user ({u.username})"
            except User.DoesNotExist:
                result['description'] = "User not found"
        else:
            result['description'] = "Select an individual recipient"
        return result

    gym = None
    if target_gym_id:
        gym = Gym.objects.filter(id=target_gym_id).first()

    if target_type == 'all':
        admin_count = GymAdmin.objects.count()
        staff_count = SubAdmin.objects.count()
        member_count = Member.objects.filter(is_deleted=False).count()
        trainer_count = Trainer.objects.filter(is_active=True).count()
        total = admin_count + staff_count + member_count + trainer_count
        result.update({
            'total': total,
            'admins': admin_count,
            'staff': staff_count,
            'members': member_count,
            'trainers': trainer_count,
            'description': f"All platform users across all gyms (~{total} recipients)",
        })

    elif target_type == 'all_gyms':
        admin_count = GymAdmin.objects.count()
        staff_count = SubAdmin.objects.count()
        total = admin_count + staff_count
        result.update({
            'total': total,
            'admins': admin_count,
            'staff': staff_count,
            'description': f"All gym owners, administrators and staff (~{total} recipients)",
        })

    elif target_type == 'all_members':
        member_count = Member.objects.filter(is_deleted=False).count()
        result.update({
            'total': member_count,
            'members': member_count,
            'description': f"All gym members across the entire platform (~{member_count} recipients)",
        })

    elif target_type in ('specific_gym', 'specific_gym_staff', 'specific_gym_members'):
        if not gym:
            result['description'] = "Select a specific gym"
            return result

        admin_count = GymAdmin.objects.filter(gym=gym).count()
        staff_count = SubAdmin.objects.filter(gym=gym).count()
        member_count = Member.objects.filter(gym=gym, is_deleted=False).count()
        trainer_count = Trainer.objects.filter(gym=gym, is_active=True).count()

        if target_type == 'specific_gym':
            total = admin_count + staff_count + member_count + trainer_count
            result.update({
                'total': total,
                'admins': admin_count,
                'staff': staff_count,
                'members': member_count,
                'trainers': trainer_count,
                'description': f"Everyone at {gym.name} (~{total} recipients)",
            })
        elif target_type == 'specific_gym_staff':
            total = admin_count + staff_count
            result.update({
                'total': total,
                'admins': admin_count,
                'staff': staff_count,
                'description': f"Admins and staff of {gym.name} (~{total} recipients)",
            })
        elif target_type == 'specific_gym_members':
            result.update({
                'total': member_count,
                'members': member_count,
                'description': f"Members of {gym.name} (~{member_count} recipients)",
            })

    return result


def send_system_notification(
    title,
    message,
    notification_type='info',
    target_type='specific_user',
    target_gym=None,
    target_user=None,
    show_popup=False,
    popup_frequency='once',
    action_label=None,
    action_url=None,
    image=None,
    created_by=None,
    expires_at=None,
):
    """
    Creates and dispatches a platform notification to a specific user, gym, or group.
    """
    try:
        notification = PlatformNotification.objects.create(
            title=title,
            message=message,
            notification_type=notification_type,
            target_type=target_type,
            target_gym=target_gym,
            target_user=target_user,
            show_popup=show_popup,
            popup_frequency=popup_frequency,
            action_label=action_label,
            action_url=action_url,
            image=image,
            created_by=created_by,
            expires_at=expires_at,
            is_active=True
        )
        return notification
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating notification: {e}")
        return None


def get_or_create_member_user(member):
    """
    Ensures a member has a linked auth.User account so they can receive notifications.
    """
    if not member:
        return None
    if member.user:
        return member.user
    try:
        user, _ = member.create_or_update_user_account()
        return user
    except Exception:
        return None


def notify_membership_activated(member, history, is_upgrade=False):
    """
    Dispatches notifications when a member's membership plan is assigned, renewed, or upgraded.
    """
    if not member or not history:
        return None

    gym = member.gym
    plan_title = history.plan.title if history.plan else "Membership Plan"
    start_date_str = history.membership_start_date.strftime('%d %b %Y') if history.membership_start_date else 'Today'
    end_date = history.get_end_date()
    end_date_str = end_date.strftime('%d %b %Y') if end_date else 'N/A'
    due_amount = history.total_amount - history.paid_amount

    # 1. Member Notification
    user = get_or_create_member_user(member)
    member_notif = None
    if user:
        action_verb = "upgraded" if is_upgrade else "activated"
        msg = (
            f"Your membership plan '{plan_title}' has been successfully {action_verb}. "
            f"Valid from {start_date_str} to {end_date_str}. "
            f"Amount Paid: ₹{history.paid_amount:,.2f}"
        )
        if due_amount > 0:
            msg += f", Balance Due: ₹{due_amount:,.2f}."
        else:
            msg += ". All plan fees are fully cleared."

        member_notif = send_system_notification(
            title=f"Membership Plan {action_verb.title()}: {plan_title}",
            message=msg,
            notification_type='success',
            target_type='specific_user',
            target_user=user,
            target_gym=gym,
            show_popup=True,
            popup_frequency='once',
            action_label='View Billing & Receipt',
            action_url='/portal/member/billing/'
        )

    # 2. Gym Staff Notification
    send_system_notification(
        title=f"Plan Enrollment: {member.name}",
        message=(
            f"Member {member.name} ({member.member_id}) enrolled in '{plan_title}'. "
            f"Paid: ₹{history.paid_amount:,.2f}, Due: ₹{due_amount:,.2f}."
        ),
        notification_type='info',
        target_type='specific_gym_staff',
        target_gym=gym,
        show_popup=False,
        action_label='View Member Profile',
        action_url=f'/members/profile/{member.id}/'
    )

    return member_notif


def notify_pt_assigned(member, pt_assignment):
    """
    Dispatches notifications when a Personal Trainer is assigned.
    Targets both the Member and the assigned Trainer.
    """
    if not member or not pt_assignment:
        return None

    gym = member.gym
    trainer = pt_assignment.trainer
    start_date_str = pt_assignment.pt_start_date.strftime('%d %b %Y') if pt_assignment.pt_start_date else 'Today'
    end_date = pt_assignment.get_end_date()
    end_date_str = end_date.strftime('%d %b %Y') if end_date else 'N/A'

    # 1. Member Notification
    user = get_or_create_member_user(member)
    member_notif = None
    if user:
        member_notif = send_system_notification(
            title=f"Personal Trainer Assigned: {trainer.name}",
            message=(
                f"Coach {trainer.name} has been assigned as your Personal Trainer for {pt_assignment.months} month(s). "
                f"Schedule: {start_date_str} to {end_date_str}. Let's reach your fitness goals together!"
            ),
            notification_type='info',
            target_type='specific_user',
            target_user=user,
            target_gym=gym,
            show_popup=True,
            popup_frequency='once',
            action_label='View Trainer Details',
            action_url='/portal/member/personal-training/'
        )

    # 2. Trainer Notification
    if trainer and trainer.user:
        send_system_notification(
            title=f"New PT Client Assigned: {member.name}",
            message=(
                f"Member {member.name} (Phone: {member.mobile_number}) has been assigned to you for Personal Training "
                f"for {pt_assignment.months} month(s). Active until {end_date_str}."
            ),
            notification_type='info',
            target_type='specific_user',
            target_user=trainer.user,
            target_gym=gym,
            show_popup=True,
            popup_frequency='once',
            action_label='View Client Profile',
            action_url=f'/portal/trainer/client/{member.id}/'
        )

    # 3. Gym Staff Notification
    send_system_notification(
        title=f"PT Assignment: {member.name} &rarr; {trainer.name}",
        message=f"{member.name} ({member.member_id}) was assigned to trainer {trainer.name} ({pt_assignment.months} mo).",
        notification_type='info',
        target_type='specific_gym_staff',
        target_gym=gym,
        show_popup=False,
        action_label='View Client',
        action_url=f'/members/profile/{member.id}/'
    )

    return member_notif


def notify_payment_submitted(payment, member, invoice=None, invoice_type='membership'):
    """
    Dispatches payment confirmation notifications to the member and receipt alerts to gym staff.
    """
    if not payment or not member:
        return None

    gym = member.gym or payment.gym
    amount = payment.amount
    mode = (payment.payment_mode or 'Cash').upper()
    payment_date_str = payment.payment_date.strftime('%d %b %Y') if hasattr(payment.payment_date, 'strftime') else str(payment.payment_date)

    # Plan name
    if invoice_type == 'membership' and invoice and hasattr(invoice, 'plan'):
        plan_desc = f"Membership ({invoice.plan.title})"
        remaining_due = (invoice.total_amount - invoice.paid_amount) if hasattr(invoice, 'total_amount') else 0
    elif invoice_type == 'pt' and invoice and hasattr(invoice, 'trainer'):
        plan_desc = f"Personal Training ({invoice.trainer.name})"
        remaining_due = (invoice.total_amount - invoice.paid_amount) if hasattr(invoice, 'total_amount') else 0
    else:
        plan_desc = "Gym Fee / Subscription"
        remaining_due = 0

    # 1. Member Notification
    user = get_or_create_member_user(member)
    if user:
        msg = (
            f"Payment of ₹{amount:,.2f} for {plan_desc} has been successfully recorded via {mode} on {payment_date_str}."
        )
        if remaining_due > 0:
            msg += f" Remaining balance due: ₹{remaining_due:,.2f}."
        else:
            msg += " All dues for this invoice are fully cleared. Thank you!"

        member_notif = send_system_notification(
            title=f"Payment Received: ₹{amount:,.2f}",
            message=msg,
            notification_type='success',
            target_type='specific_user',
            target_user=user,
            target_gym=gym,
            show_popup=True,
            popup_frequency='once',
            action_label='View Payment History',
            action_url='/portal/member/billing/'
        )
    else:
        member_notif = None

    # 2. Gym Staff Notification
    send_system_notification(
        title=f"Payment Recorded: ₹{amount:,.2f} from {member.name}",
        message=f"Received ₹{amount:,.2f} from {member.name} ({member.member_id}) via {mode} for {plan_desc}.",
        notification_type='success',
        target_type='specific_gym_staff',
        target_gym=gym,
        show_popup=False,
        action_label='View Invoices',
        action_url='/billing/invoices/'
    )

    return member_notif


def notify_membership_expiring(member, history, days_left):
    """
    Dispatches expiry warnings (4-day, 2-day) with popups to the member and notice to gym staff.
    Includes deduplication within 24 hours.
    """
    if not member or not history:
        return None

    user = get_or_create_member_user(member)
    gym = member.gym
    plan_title = history.plan.title if history.plan else "Membership Plan"
    end_date = history.get_end_date()
    end_date_str = end_date.strftime('%d %b %Y') if end_date else 'Soon'

    # Deduplication check: avoid spamming multiple identical warnings in the same day
    if user:
        today = timezone.localdate()
        recent_exists = PlatformNotification.objects.filter(
            target_user=user,
            title__icontains="Expiring",
            created_at__date=today
        ).exists()
        if not recent_exists:
            is_urgent = days_left <= 2
            title = f"Urgent: Membership Expiring in {days_left} Day{'s' if days_left != 1 else ''}" if is_urgent else f"Membership Expiring Soon ({days_left} Days Left)"
            msg = (
                f"Your '{plan_title}' membership expires on {end_date_str}. "
                f"Please renew your membership promptly to maintain uninterrupted access to gym facilities and classes."
            )
            send_system_notification(
                title=title,
                message=msg,
                notification_type='danger' if is_urgent else 'warning',
                target_type='specific_user',
                target_user=user,
                target_gym=gym,
                show_popup=True,
                popup_frequency='every_login',
                action_label='Check Membership Details',
                action_url='/portal/member/'
            )

    # Gym Staff reminder
    send_system_notification(
        title=f"Member Expiring Soon: {member.name} ({days_left}d left)",
        message=f"{member.name}'s ({member.member_id}) '{plan_title}' expires on {end_date_str}. Contact for renewal.",
        notification_type='warning',
        target_type='specific_gym_staff',
        target_gym=gym,
        show_popup=False,
        action_label='Member Profile',
        action_url=f'/members/profile/{member.id}/'
    )


def notify_membership_expired(member, history):
    """
    Dispatches plan expired notifications to the member and alerts to gym staff.
    """
    if not member or not history:
        return None

    user = get_or_create_member_user(member)
    gym = member.gym
    plan_title = history.plan.title if history.plan else "Membership Plan"
    end_date = history.get_end_date()
    end_date_str = end_date.strftime('%d %b %Y') if end_date else 'Recently'

    if user:
        today = timezone.localdate()
        recent_exists = PlatformNotification.objects.filter(
            target_user=user,
            title__icontains="Membership Expired",
            created_at__date=today
        ).exists()
        if not recent_exists:
            send_system_notification(
                title=f"Membership Expired: {plan_title}",
                message=(
                    f"Your '{plan_title}' membership expired on {end_date_str}. "
                    f"Please contact the front desk or renew your plan to restore full gym access."
                ),
                notification_type='danger',
                target_type='specific_user',
                target_user=user,
                target_gym=gym,
                show_popup=True,
                popup_frequency='every_login',
                action_label='Renew Membership',
                action_url='/portal/member/billing/'
            )

    send_system_notification(
        title=f"Membership Expired: {member.name}",
        message=f"{member.name}'s ({member.member_id}) '{plan_title}' expired on {end_date_str}. Follow up for renewal.",
        notification_type='danger',
        target_type='specific_gym_staff',
        target_gym=gym,
        show_popup=False,
        action_label='Member Profile',
        action_url=f'/members/profile/{member.id}/'
    )


def notify_pt_expiring(member, pt_assignment, days_left):
    """
    Dispatches Personal Training expiration notices to member and trainer.
    """
    if not member or not pt_assignment:
        return None

    trainer = pt_assignment.trainer
    gym = member.gym
    end_date = pt_assignment.get_end_date()
    end_date_str = end_date.strftime('%d %b %Y') if end_date else 'Soon'

    # 1. Member
    user = get_or_create_member_user(member)
    if user:
        send_system_notification(
            title=f"Personal Training Expiring ({days_left} Days Left)",
            message=(
                f"Your training package with Coach {trainer.name} expires on {end_date_str}. "
                f"Speak with your trainer or visit the reception to extend your package."
            ),
            notification_type='warning',
            target_type='specific_user',
            target_user=user,
            target_gym=gym,
            show_popup=True,
            popup_frequency='once',
            action_label='View PT Details',
            action_url='/portal/member/personal-training/'
        )

    # 2. Trainer
    if trainer and trainer.user:
        send_system_notification(
            title=f"Client PT Expiring: {member.name} ({days_left}d left)",
            message=(
                f"Your client {member.name}'s PT package expires on {end_date_str}. "
                f"Discuss renewal options before their sessions conclude."
            ),
            notification_type='warning',
            target_type='specific_user',
            target_user=trainer.user,
            target_gym=gym,
            show_popup=False,
            action_label='View Client',
            action_url=f'/portal/trainer/client/{member.id}/'
        )

