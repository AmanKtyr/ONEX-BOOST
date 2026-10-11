from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from apps.superadmin.models import GymAdmin
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User, Permission
from functools import wraps
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Q
import secrets
import string
import logging
logger = logging.getLogger(__name__)
from .models import SubAdmin, ROLE_CHOICES
from .models import SubAdminPermission
from apps.superadmin.email_service import send_password_reset_email, send_password_changed_email
from apps.superadmin.subscription_utils import check_resource_quota, get_gym_quota_status


def gym_admin_required(view_func):
    """
    Ensures that only GymAdmins or Superusers can access sub-admin management.
    Sub-admins are forbidden from managing staff accounts.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_superuser or hasattr(request.user, 'gymadmin'):
            return view_func(request, *args, **kwargs)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'error',
                'code': 'permission_denied',
                'message': 'Access Restricted: Only Gym Administrators have permission to manage staff sub-admin accounts.'
            }, status=403)
        messages.warning(
            request,
            'Access Restricted: Only Gym Administrators have permission to manage staff sub-admin accounts.',
            extra_tags='permission_denied'
        )
        return redirect('dashboard')
    return _wrapped


@never_cache
def superadmin_login(request):
    try:
        from apps.superadmin.models import SystemSetting
        max_attempts = int(SystemSetting.get_settings().max_login_attempts or 5)
    except Exception:
        max_attempts = 5

    attempts_key = 'sa_failed_login_attempts'
    current_attempts = request.session.get(attempts_key, 0)

    if request.method == 'POST':
        if current_attempts >= max_attempts:
            messages.error(request, f'Too many failed login attempts ({current_attempts}/{max_attempts}). Login is temporarily locked for security.')
            return render(request, 'login/superadmin_login.html')

        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_superuser:
            login(request, user)
            request.session['role'] = 'superadmin'
            request.session[attempts_key] = 0
            return redirect('superadmin:dashboard')
        else:
            current_attempts += 1
            request.session[attempts_key] = current_attempts
            remaining = max(0, max_attempts - current_attempts)
            if remaining > 0:
                messages.error(request, f'Invalid username or password. {remaining} attempt(s) remaining before lockout.')
            else:
                messages.error(request, f'Maximum failed login attempts reached ({max_attempts}). Temporary lockout active.')
    return render(request, 'login/superadmin_login.html')

def get_login_candidates(identifier):
    """
    Finds matching user accounts for a given identifier (mobile number, email, or username).
    Returns list of dicts: [{'user': user, 'username': user.username, 'name': '...', 'account_type': '...', 'extra': '...'}, ...]
    """
    import re
    from apps.members.models import Member
    from apps.trainers.models import Trainer
    from apps.login.models import SubAdmin
    from apps.superadmin.models import GymAdmin
    from django.contrib.auth.models import User

    cleaned = (identifier or '').strip()
    digits_only = re.sub(r'\D', '', cleaned)
    candidates = []
    seen_user_ids = set()

    def add_candidate(user, account_type, name, extra=''):
        if user and user.id not in seen_user_ids and user.is_active:
            seen_user_ids.add(user.id)
            candidates.append({
                'user': user,
                'username': user.username,
                'account_type': account_type,
                'name': name or user.username,
                'extra': extra
            })

    # 1. Search by mobile number (10 or more digits)
    if len(digits_only) >= 10:
        phone_10 = digits_only[-10:]
        for m in Member.objects.filter(mobile_number=phone_10, is_deleted=False).select_related('user', 'gym'):
            if m.user:
                add_candidate(m.user, 'Member', m.name, f"Member ID: {m.member_id}")
        for t in Trainer.objects.filter(phone=phone_10, is_active=True).select_related('user', 'gym'):
            if t.user:
                add_candidate(t.user, 'Trainer', t.name, f"Trainer ID: {t.trainer_id}")
        for s in SubAdmin.objects.filter(phone_number=phone_10).select_related('user', 'gym'):
            if s.user:
                add_candidate(s.user, 'Staff', f"{s.user.first_name} {s.user.last_name}".strip() or s.user.username, f"Role: {s.role.title()}")
        for ga in GymAdmin.objects.filter(Phone_number=phone_10).select_related('user', 'gym'):
            if ga.user:
                add_candidate(ga.user, 'Gym Admin', f"{ga.user.first_name} {ga.user.last_name}".strip() or ga.user.username, f"Gym: {ga.gym.name if ga.gym else ''}")

    # 2. Search by email
    if '@' in cleaned and not candidates:
        for u in User.objects.filter(email__iexact=cleaned, is_active=True):
            acc_type = 'User'
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            if hasattr(u, 'member_profile'):
                acc_type = 'Member'
                name = u.member_profile.name
            elif hasattr(u, 'trainer_profile'):
                acc_type = 'Trainer'
                name = u.trainer_profile.name
            elif hasattr(u, 'subadmin'):
                acc_type = 'Staff'
            elif hasattr(u, 'gymadmin'):
                acc_type = 'Gym Admin'
            add_candidate(u, acc_type, name, u.email)

    # 3. Direct username search
    if not candidates:
        u = User.objects.filter(username__iexact=cleaned, is_active=True).first()
        if u:
            acc_type = 'User'
            name = f"{u.first_name} {u.last_name}".strip() or u.username
            if hasattr(u, 'member_profile'):
                acc_type = 'Member'
                name = u.member_profile.name
            elif hasattr(u, 'trainer_profile'):
                acc_type = 'Trainer'
                name = u.trainer_profile.name
            elif hasattr(u, 'subadmin'):
                acc_type = 'Staff'
            elif hasattr(u, 'gymadmin'):
                acc_type = 'Gym Admin'
            add_candidate(u, acc_type, name, f"Username: {u.username}")

    return candidates


#gym login view
@never_cache
def user_login(request):
    if request.user.is_authenticated:
        role = request.session.get('role')
        if role == 'member':
            return redirect('member_portal:dashboard')
        elif role == 'trainer':
            return redirect('trainer_portal:dashboard')
        elif role == 'superadmin':
            return redirect('superadmin:dashboard')
        else:
            return redirect('dashboard')

    if request.method == 'POST':
        try:
            from apps.superadmin.models import SystemSetting
            max_attempts = int(SystemSetting.get_settings().max_login_attempts or 5)
        except Exception:
            max_attempts = 5

        current_attempts = request.session.get('user_failed_attempts', 0)
        if current_attempts >= max_attempts:
            messages.error(request, f'Too many failed login attempts ({current_attempts}/{max_attempts}). For security, login is temporarily locked.')
            return render(request, 'login/login.html')

        identifier = (request.POST.get('identifier') or request.POST.get('username') or '').strip()
        password = request.POST.get('password', '')
        selected_username = (request.POST.get('selected_username') or '').strip()

        candidates = get_login_candidates(identifier)

        # Ambiguity resolution: If multiple accounts match this phone/identifier
        if len(candidates) > 1:
            if not selected_username:
                return render(request, 'login/login.html', {
                    'has_multiple_accounts': True,
                    'entered_identifier': identifier,
                    'multiple_candidates': candidates,
                })
            else:
                matched_candidate = next((c for c in candidates if c['username'].lower() == selected_username.lower()), None)
                target_username = matched_candidate['username'] if matched_candidate else selected_username
        elif len(candidates) == 1:
            target_username = candidates[0]['username']
        else:
            target_username = identifier

        user = authenticate(request, username=target_username, password=password)
        if user is not None:
            request.session['user_failed_attempts'] = 0
            login(request, user)

            if user.is_superuser:
                request.session['role'] = 'superadmin'
                return redirect('dashboard') 
            
            if hasattr(user, 'gymadmin'):
                gym_admin = user.gymadmin
                request.session['gym_id'] = gym_admin.gym.id
                request.session['gym_name'] = gym_admin.gym.name
                request.session['gym_logo'] = gym_admin.gym.logo.url if gym_admin.gym.logo else None
                request.session['gym_phone'] = gym_admin.gym.phone
                request.session['role'] = 'gym_admin'
                return redirect('dashboard')

            if hasattr(user, 'subadmin'):
                sub_admin = user.subadmin
                request.session['gym_id'] = sub_admin.gym.id
                request.session['gym_name'] = sub_admin.gym.name
                request.session['gym_logo'] = sub_admin.gym.logo.url if sub_admin.gym.logo else None
                request.session['gym_phone'] = sub_admin.gym.phone
                request.session['role'] = sub_admin.role
                request.session['subadmin_id'] = sub_admin.id
                return redirect('dashboard')

            if hasattr(user, 'trainer_profile'):
                trainer = user.trainer_profile
                request.session['gym_id'] = trainer.gym.id if trainer.gym else None
                request.session['gym_name'] = trainer.gym.name if trainer.gym else 'ONEXIVAym'
                request.session['gym_logo'] = trainer.gym.logo.url if trainer.gym and trainer.gym.logo else None
                request.session['role'] = 'trainer'
                request.session['trainer_id'] = trainer.id
                return redirect('trainer_portal:dashboard')

            if hasattr(user, 'member_profile'):
                member = user.member_profile
                request.session['gym_id'] = member.gym.id if member.gym else None
                request.session['gym_name'] = member.gym.name if member.gym else 'ONEXIVAym'
                request.session['gym_logo'] = member.gym.logo.url if member.gym and member.gym.logo else None
                request.session['role'] = 'member'
                request.session['member_id'] = member.id
                return redirect('member_portal:dashboard')

            messages.error(request, 'Invalid user role configuration.')
            return redirect('login')
        else:
            current_attempts += 1
            request.session['user_failed_attempts'] = current_attempts
            remaining = max(0, max_attempts - current_attempts)
            if remaining > 0:
                messages.error(request, f'Invalid login credentials. {remaining} attempt(s) remaining before lockout.')
            else:
                messages.error(request, f'Maximum failed login attempts reached ({max_attempts}). Temporary lockout active.')
    return render(request, 'login/login.html')


def user_logout(request):
    if 'gym_id' in request.session:
        del request.session['gym_id']
    if 'role' in request.session:
        del request.session['role']
    logout(request)
    request.session.flush()  # Clear all session data
    logger.debug("User logged out. Session flushed.")
    return redirect('index')


MODULE_DEFINITIONS = [
    {
        'app': 'enquiry',
        'title': 'Lead & Enquiry Management',
        'icon': 'mdi-help-circle-outline',
        'badge_class': 'badge-soft-primary',
        'desc': 'Capture walk-ins, schedule trials, and track prospect conversions',
    },
    {
        'app': 'members',
        'title': 'Members Management',
        'icon': 'mdi-account-group-outline',
        'badge_class': 'badge-soft-info',
        'desc': 'Member profiles, registrations, KYC, and membership freeze',
    },
    {
        'app': 'trainers',
        'title': 'Trainers & Instructors',
        'icon': 'mdi-account-tie-outline',
        'badge_class': 'badge-soft-success',
        'desc': 'Instructor profiles, work shifts, specialties, and client assignments',
    },
    {
        'app': 'attendance',
        'title': 'Attendance & Check-Ins',
        'icon': 'mdi-calendar-check-outline',
        'badge_class': 'badge-soft-warning',
        'desc': 'Daily check-in logs, QR scanner records, and staff leaves',
    },
    {
        'app': 'billing',
        'title': 'Billing, Payments & Invoices',
        'icon': 'mdi-cash-register',
        'badge_class': 'badge-soft-success',
        'desc': 'Fee collection, membership invoices, payment receipts & tax records',
    },
    {
        'app': 'expenses',
        'title': 'Expenses & Outflows',
        'icon': 'mdi-credit-card-outline',
        'badge_class': 'badge-soft-danger',
        'desc': 'Operational gym expenditures, utility bills, maintenance, & vendor payouts',
    },
    {
        'app': 'inventory',
        'title': 'Equipment & Inventory',
        'icon': 'mdi-package-variant-closed',
        'badge_class': 'badge-soft-primary',
        'desc': 'Gym machines maintenance logs, retail supplement stocks, and supplies',
    },
    {
        'app': 'events',
        'title': 'Events & Fitness Workshops',
        'icon': 'mdi-calendar-star',
        'badge_class': 'badge-soft-info',
        'desc': 'Special workout events, fitness bootcamps, and participant rosters',
    },
    {
        'app': 'management',
        'model': 'membershipplan',
        'title': 'Membership Packages & Plans',
        'icon': 'mdi-wallet-membership',
        'badge_class': 'badge-soft-warning',
        'desc': 'Gym membership subscription tiers, package validity, and pricing',
    },
    {
        'app': 'management',
        'model': 'dietplan',
        'title': 'Diet & Nutrition Plans',
        'icon': 'mdi-food-apple-outline',
        'badge_class': 'badge-soft-success',
        'desc': 'Dietary guidelines, daily calorie targets, and meal plans',
    },
    {
        'app': 'management',
        'model': 'workoutplan',
        'title': 'Workout & Exercise Plans',
        'icon': 'mdi-dumbbell',
        'badge_class': 'badge-soft-primary',
        'desc': 'Workout schedules, body splits, exercise sets, and fitness routines',
    },
    {
        'app': 'settings',
        'title': 'System & Payment Settings',
        'icon': 'mdi-cog-outline',
        'badge_class': 'badge-soft-secondary',
        'desc': 'Payment gateway configurations, alert preferences, and branch settings',
    },
]

def _build_permission_modules(assigned_ids=None):
    if assigned_ids is None:
        assigned_ids = []
    
    app_permissions = {}
    module_list = []
    
    for item in MODULE_DEFINITIONS:
        app = item['app']
        model = item.get('model')
        if model:
            content_type = ContentType.objects.filter(app_label=app, model=model).first()
        else:
            content_type = ContentType.objects.filter(app_label=app).first()
        if not content_type:
            continue
        perms = Permission.objects.filter(content_type=content_type)
        key = f"{app}_{model}" if model else app
        app_permissions[key] = perms
        
        view_perm = perms.filter(codename__startswith='view_').first()
        add_perm = perms.filter(codename__startswith='add_').first()
        change_perm = perms.filter(codename__startswith='change_').first()
        delete_perm = perms.filter(codename__startswith='delete_').first()
        
        module_list.append({
            'app': app,
            'model': model or '',
            'title': item['title'],
            'icon': item['icon'],
            'badge_class': item['badge_class'],
            'desc': item['desc'],
            'view_perm': view_perm,
            'add_perm': add_perm,
            'change_perm': change_perm,
            'delete_perm': delete_perm,
            'has_view': bool(view_perm and view_perm.id in assigned_ids),
            'has_add': bool(add_perm and add_perm.id in assigned_ids),
            'has_change': bool(change_perm and change_perm.id in assigned_ids),
            'has_delete': bool(delete_perm and delete_perm.id in assigned_ids),
        })
        
    return app_permissions, module_list


@never_cache
@login_required(login_url='login')
@gym_admin_required
def add_gym_subadmin(request):
    gym = getattr(request, 'gym', None)
    if not gym:
        gym_admin = GymAdmin.objects.filter(user=request.user).first()
        if gym_admin:
            gym = gym_admin.gym

    can_add, quota_error, quota_status = check_resource_quota(gym, 'admin')

    if request.method == 'POST':
        if not can_add:
            messages.error(request, quota_error)
            return redirect('view_subadmins')

        # Personal Information
        full_name = request.POST.get('full_name') or request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number') or request.POST.get('mobile', '').strip()
        address = request.POST.get('address', '').strip()
        photo = request.FILES.get('photo')
        role = request.POST.get('role', 'subadmin')

        # Login Credentials
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        # Permissions
        permissions = request.POST.getlist('permissions')

        if not username:
            messages.error(request, 'Username is required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already exists. Please choose a different username.')
        elif not password:
            messages.error(request, 'Password is required for new sub-admin.')
        elif not gym:
            messages.error(request, 'No active gym found for this account. Please verify gym setup.')
        else:
            try:
                # Create the user
                user = User.objects.create_user(username=username, email=email, password=password)
                if full_name:
                    parts = full_name.strip().split(' ', 1)
                    user.first_name = parts[0]
                    if len(parts) > 1:
                        user.last_name = parts[1]
                user.save()

                # Create the sub-admin profile
                sub_admin = SubAdmin.objects.create(
                    user=user,
                    gym=gym,
                    phone_number=phone_number,
                    address=address,
                    photo=photo,
                    role=role
                )

                # Assign permissions
                for perm_id in permissions:
                    try:
                        perm = Permission.objects.get(id=perm_id)
                        SubAdminPermission.objects.create(sub_admin=sub_admin, permission_name=perm.codename)
                    except Permission.DoesNotExist:
                        pass

                messages.success(request, f'Sub-admin "{user.get_full_name() or username}" created successfully!')
                return redirect('view_subadmins')

            except Exception as e:
                messages.error(request, f'Error creating sub-admin: {e}')

    app_permissions, module_list = _build_permission_modules([])

    context = {
        'app_permissions': app_permissions,
        'module_list': module_list,
        'ROLE_CHOICES': ROLE_CHOICES,
        'assigned_permissions': [],
        'quota_status': quota_status,
        'quota_limit_reached': not can_add,
        'quota_error': quota_error,
    }
    return render(request, 'login/add_gym_subadmin.html', context)


@login_required
def password_reset_page(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        user = request.user
        if not user.check_password(current_password):
            messages.error(request, 'Invalid current password.')
        elif new_password != confirm_password:
            messages.error(request, 'New passwords do not match.')
        elif ' ' in new_password:
            messages.error(request, 'Password cannot contain spaces.')
        else:
            user.set_password(new_password)
            user.save()
            
            if hasattr(user, 'gymadmin'):
                gym_admin = user.gymadmin
                if hasattr(gym_admin, 'gym'):
                    gym_admin.gym.password_reset_required = False
                    gym_admin.gym.save()

            # Dispatch password change confirmation email
            if user.email:
                send_password_changed_email(user, request=request)
            
            messages.success(request, 'Password updated successfully.')
            return redirect('dashboard')
            
    return render(request, 'login/password_reset.html')


@require_POST
def forgot_password_request_api(request):
    """
    Self-service password reset request API.
    Accepts identifier (email or username), generates a secure temporary password,
    enforces password reset upon next login, and dispatches an email via the SMTP gateway.
    """
    identifier = request.POST.get('identifier', '').strip()
    if not identifier:
        return JsonResponse({'success': False, 'message': 'Please provide your registered email address or username.'})

    user = User.objects.filter(Q(email__iexact=identifier) | Q(username__iexact=identifier)).first()
    if not user:
        return JsonResponse({'success': False, 'message': 'No registered account found matching that email or username.'})

    if not user.email:
        return JsonResponse({'success': False, 'message': 'This account does not have a registered email address. Please contact your platform administrator.'})

    # Generate a secure 8-character temporary password
    alphabet = string.ascii_letters + string.digits
    temp_password = "FS#" + ''.join(secrets.choice(alphabet) for _ in range(6))

    user.set_password(temp_password)
    user.save()

    gym_name = None
    if hasattr(user, 'gymadmin') and hasattr(user.gymadmin, 'gym'):
        user.gymadmin.gym.password_reset_required = True
        user.gymadmin.gym.save()
        gym_name = user.gymadmin.gym.name

    email_sent, err = send_password_reset_email(user, temp_password, gym_name=gym_name, request=request)

    if email_sent:
        parts = user.email.split('@')
        masked = f"{parts[0][:2]}***@{parts[1]}" if len(parts) == 2 else user.email
        return JsonResponse({
            'success': True,
            'message': f'Temporary password and reset instructions have been sent to {masked}. Please check your inbox.'
        })
    else:
        return JsonResponse({
            'success': False,
            'message': f'Could not send reset email: {err}. Please verify SMTP settings with your platform administrator.'
        })


@never_cache
@login_required(login_url='login')
@gym_admin_required
def view_subadmins(request):
    gym = getattr(request, 'gym', None)
    if not gym:
        gym_admin = GymAdmin.objects.filter(user=request.user).first()
        if gym_admin:
            gym = gym_admin.gym
    sub_admins = SubAdmin.objects.filter(gym=gym) if gym else SubAdmin.objects.none()
    context = {
        'sub_admins': sub_admins
    }
    return render(request, 'login/view_subadmins.html', context)


@never_cache
@login_required(login_url='login')
@gym_admin_required
def delete_subadmin(request, sub_admin_id):
    gym = getattr(request, 'gym', None)
    if not gym and hasattr(request.user, 'gymadmin'):
        gym = request.user.gymadmin.gym
    if not gym:
        messages.error(request, 'Gym not found.')
        return redirect('view_subadmins')

    try:
        sub_admin = SubAdmin.objects.get(id=sub_admin_id, gym=gym)
        user = sub_admin.user
        sub_admin.delete()
        user.delete()
        messages.success(request, 'Sub-admin deleted successfully.')
    except SubAdmin.DoesNotExist:
        messages.error(request, 'Sub-admin not found.')
    except Exception as e:
        messages.error(request, f'An error occurred: {e}')
    return redirect('view_subadmins')

@never_cache
@login_required(login_url='login')
@gym_admin_required
def edit_subadmin(request, sub_admin_id):
    gym = getattr(request, 'gym', None)
    if not gym and hasattr(request.user, 'gymadmin'):
        gym = request.user.gymadmin.gym
    if not gym:
        messages.error(request, 'Gym not found.')
        return redirect('view_subadmins')

    try:
        sub_admin = SubAdmin.objects.get(id=sub_admin_id, gym=gym)
        user = sub_admin.user
    except SubAdmin.DoesNotExist:
        messages.error(request, 'Sub-admin not found.')
        return redirect('view_subadmins')

    if request.method == 'POST':
        full_name = request.POST.get('full_name') or request.POST.get('name', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number') or request.POST.get('mobile', '').strip()
        address = request.POST.get('address', '').strip()
        photo = request.FILES.get('photo')
        permissions = request.POST.getlist('permissions')
        role = request.POST.get('role', sub_admin.role)
        new_password = request.POST.get('password', '').strip()

        if not username:
            messages.error(request, 'Username is required.')
        elif username != user.username and User.objects.filter(username=username).exclude(id=user.id).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            try:
                if full_name:
                    parts = full_name.split(' ', 1)
                    user.first_name = parts[0]
                    if len(parts) > 1:
                        user.last_name = parts[1]
                user.username = username
                user.email = email
                if new_password:
                    user.set_password(new_password)
                user.save()

                sub_admin.phone_number = phone_number
                sub_admin.address = address
                sub_admin.role = role
                if photo:
                    sub_admin.photo = photo
                sub_admin.save()
                
                SubAdminPermission.objects.filter(sub_admin=sub_admin).delete()
                for perm_id in permissions:
                    try:
                        perm = Permission.objects.get(id=perm_id)
                        SubAdminPermission.objects.create(sub_admin=sub_admin, permission_name=perm.codename)
                    except Permission.DoesNotExist:
                        pass

                messages.success(request, f'Sub-admin "{user.get_full_name() or username}" updated successfully.')
                return redirect('view_subadmins')
            except Exception as e:
                messages.error(request, f'Error updating sub-admin: {e}')

    assigned_permissions_qs = SubAdminPermission.objects.filter(sub_admin=sub_admin).values_list('permission_name', flat=True)
    assigned_permissions = list(Permission.objects.filter(codename__in=list(assigned_permissions_qs)).values_list('id', flat=True))
    app_permissions, module_list = _build_permission_modules(assigned_permissions)

    context = {
        'sub_admin': sub_admin,
        'app_permissions': app_permissions,
        'module_list': module_list,
        'assigned_permissions': assigned_permissions,
        'ROLE_CHOICES': ROLE_CHOICES
    }
    return render(request, 'login/add_gym_subadmin.html', context)