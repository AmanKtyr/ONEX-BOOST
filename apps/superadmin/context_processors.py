from .models import Gym
from .notifications import get_unread_notifications_count, get_recent_notifications

def gym_details(request):
    """
    Global context processor providing gym details, notification counts,
    and user role metadata (Member, Trainer, Gym Admin, Subadmin, Super Admin).
    """
    gym = getattr(request, 'gym', None)
    user_info = {
        'user_role_code': 'anonymous',
        'user_role_label': 'Guest',
        'user_role_icon': 'mdi-account-outline',
        'user_role_badge_class': 'role-badge-guest',
        'user_display_name': 'Guest',
        'user_full_name': 'Guest',
        'user_avatar_url': None,
        'user_subtitle': '',
        'user_email_or_phone': '',
        'is_gym_admin': False,
        'is_subadmin': False,
        'is_trainer': False,
        'is_member': False,
        'is_superadmin': False,
    }

    unread_count = 0
    recent_notifs = []

    if hasattr(request, 'user') and request.user.is_authenticated:
        user = request.user
        session_role = request.session.get('role', '') if hasattr(request, 'session') else ''

        # Resolve gym if missing from request
        if not gym:
            if hasattr(user, 'gymadmin') and user.gymadmin.gym:
                gym = user.gymadmin.gym
            elif hasattr(user, 'subadmin') and user.subadmin.gym:
                gym = user.subadmin.gym
            elif hasattr(user, 'trainer_profile') and user.trainer_profile.gym:
                gym = user.trainer_profile.gym
            elif hasattr(user, 'member_profile') and user.member_profile.gym:
                gym = user.member_profile.gym
            elif hasattr(request, 'session') and request.session.get('gym_id'):
                gym = Gym.objects.filter(id=request.session.get('gym_id')).first()

        # 1. Super Admin
        if user.is_superuser or session_role == 'superadmin':
            user_info.update({
                'user_role_code': 'superadmin',
                'user_role_label': 'Super Admin',
                'user_role_icon': 'mdi-shield-crown',
                'user_role_badge_class': 'badge badge-pill badge-danger',
                'user_display_name': user.first_name or user.username,
                'user_full_name': user.get_full_name() or user.username,
                'user_subtitle': 'Platform Administrator',
                'user_email_or_phone': user.email or user.username,
                'is_superadmin': True,
            })

        # 2. Member
        elif session_role == 'member' or hasattr(user, 'member_profile'):
            member = getattr(user, 'member_profile', None)
            display_name = (member.first_name if member else None) or user.first_name or user.username
            full_name = (member.name if member else None) or user.get_full_name() or user.username
            avatar = None
            if member and member.profile_picture:
                try:
                    avatar = member.profile_picture.url
                except Exception:
                    avatar = None
            phone = member.mobile_number if member else (user.email or user.username)
            mid = member.member_id if member else ''
            subtitle = f"ID: {mid}" if mid else "Gym Member"

            user_info.update({
                'user_role_code': 'member',
                'user_role_label': 'Member',
                'user_role_icon': 'mdi-account-check',
                'user_role_badge_class': 'badge badge-pill badge-success',
                'user_display_name': display_name,
                'user_full_name': full_name,
                'user_avatar_url': avatar,
                'user_subtitle': subtitle,
                'user_email_or_phone': phone,
                'is_member': True,
            })

        # 3. Trainer
        elif session_role == 'trainer' or hasattr(user, 'trainer_profile'):
            trainer = getattr(user, 'trainer_profile', None)
            display_name = (trainer.name.split()[0] if (trainer and trainer.name) else None) or user.first_name or user.username
            full_name = (trainer.name if trainer else None) or user.get_full_name() or user.username
            avatar = None
            if trainer and trainer.photo:
                try:
                    avatar = trainer.photo.url
                except Exception:
                    avatar = None
            phone = trainer.phone if trainer else (user.email or user.username)
            subtitle = f"Coach • {trainer.specialization}" if (trainer and trainer.specialization) else "Fitness Trainer"

            user_info.update({
                'user_role_code': 'trainer',
                'user_role_label': 'Trainer',
                'user_role_icon': 'mdi-dumbbell',
                'user_role_badge_class': 'badge badge-pill badge-warning text-dark',
                'user_display_name': display_name,
                'user_full_name': full_name,
                'user_avatar_url': avatar,
                'user_subtitle': subtitle,
                'user_email_or_phone': phone,
                'is_trainer': True,
            })

        # 4. Sub-Admin / Staff
        elif session_role in ('subadmin', 'front_desk', 'manager', 'accounts', 'inventory', 'marketing') or hasattr(user, 'subadmin'):
            subadmin = getattr(user, 'subadmin', None)
            raw_role = getattr(subadmin, 'role', session_role or 'subadmin')
            choices_dict = dict(subadmin._meta.get_field('role').choices) if subadmin else {}
            specific_role = choices_dict.get(raw_role, raw_role.title())
            if raw_role in ('subadmin', 'admin'):
                role_label = 'Sub-Admin'
            else:
                role_label = f"Sub-Admin ({specific_role})"
            display_name = user.first_name or user.username
            full_name = user.get_full_name() or user.username
            avatar = None
            if subadmin and subadmin.photo:
                try:
                    avatar = subadmin.photo.url
                except Exception:
                    avatar = None
            phone = getattr(subadmin, 'phone_number', None) or user.email or user.username
            gym_name = subadmin.gym.name if (subadmin and subadmin.gym) else ''
            subtitle = f"{role_label} • {gym_name}" if gym_name else role_label

            user_info.update({
                'user_role_code': 'subadmin',
                'user_role_label': role_label,
                'user_role_icon': 'mdi-badge-account-horizontal',
                'user_role_badge_class': 'badge badge-pill badge-info',
                'user_display_name': display_name,
                'user_full_name': full_name,
                'user_avatar_url': avatar,
                'user_subtitle': subtitle,
                'user_email_or_phone': phone,
                'is_subadmin': True,
            })

        # 5. Gym Admin
        elif session_role == 'gym_admin' or hasattr(user, 'gymadmin'):
            gymadmin = getattr(user, 'gymadmin', None)
            display_name = (gymadmin.name.split()[0] if (gymadmin and gymadmin.name) else None) or user.first_name or user.username
            full_name = (gymadmin.name if gymadmin else None) or user.get_full_name() or user.username
            avatar = None
            if gymadmin and gymadmin.photo:
                try:
                    avatar = gymadmin.photo.url
                except Exception:
                    avatar = None
            phone = getattr(gymadmin, 'Phone_number', None) or user.email or user.username
            gym_name = gymadmin.gym.name if (gymadmin and gymadmin.gym) else ''
            subtitle = f"Admin • {gym_name}" if gym_name else "Gym Administrator"

            user_info.update({
                'user_role_code': 'gym_admin',
                'user_role_label': 'Gym Admin',
                'user_role_icon': 'mdi-shield-check',
                'user_role_badge_class': 'badge badge-pill badge-primary',
                'user_display_name': display_name,
                'user_full_name': full_name,
                'user_avatar_url': avatar,
                'user_subtitle': subtitle,
                'user_email_or_phone': phone,
                'is_gym_admin': True,
            })

        # 6. Fallback Authenticated User
        else:
            user_info.update({
                'user_role_code': 'user',
                'user_role_label': 'Staff',
                'user_role_icon': 'mdi-account',
                'user_role_badge_class': 'badge badge-pill badge-secondary',
                'user_display_name': user.first_name or user.username,
                'user_full_name': user.get_full_name() or user.username,
                'user_subtitle': 'Staff Member',
                'user_email_or_phone': user.email or user.username,
            })

        # Notifications
        try:
            unread_count = get_unread_notifications_count(user)
            recent_notifs = get_recent_notifications(user, limit=5)
        except Exception:
            unread_count = 0
            recent_notifs = []

    gym_quota = None
    if gym and (user_info.get('is_gym_admin') or user_info.get('is_subadmin')):
        try:
            from .subscription_utils import get_gym_quota_status
            gym_quota = get_gym_quota_status(gym)
        except Exception:
            gym_quota = None

    system_setting = None
    try:
        from .models import SystemSetting
        system_setting = SystemSetting.get_settings()
    except Exception:
        system_setting = None

    current_member = None
    current_trainer = None
    topbar_qr_data_uri = None
    topbar_verify_url = None

    if hasattr(request, 'user') and request.user.is_authenticated:
        if user_info.get('is_member'):
            current_member = getattr(request.user, 'member_profile', None)
            if current_member and current_member.member_id:
                try:
                    from django.urls import reverse
                    import qrcode, io, base64
                    topbar_verify_url = request.build_absolute_uri(reverse('member_portal:verify_pass', args=[current_member.member_id]))
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=1)
                    qr.add_data(topbar_verify_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="#0a192f", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    topbar_qr_data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
                except Exception:
                    pass
        elif user_info.get('is_trainer'):
            current_trainer = getattr(request.user, 'trainer_profile', None)
            if current_trainer and current_trainer.trainer_id:
                try:
                    from django.urls import reverse
                    import qrcode, io, base64
                    topbar_verify_url = request.build_absolute_uri(reverse('trainer_portal:verify_pass', args=[current_trainer.trainer_id]))
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=1)
                    qr.add_data(topbar_verify_url)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="#0a192f", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    topbar_qr_data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"
                except Exception:
                    pass

    context = {
        'gym': gym,
        'gym_quota': gym_quota,
        'system_setting': system_setting,
        'unread_notifications_count': unread_count,
        'recent_notifications': recent_notifs,
        'current_member': current_member,
        'current_trainer': current_trainer,
        'topbar_qr_data_uri': topbar_qr_data_uri,
        'topbar_verify_url': topbar_verify_url,
        **user_info,
    }
    return context