import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta
from functools import wraps
from django.db.models import Sum, F

from apps.members.models import (
    Member, MembershipHistory, PersonalTrainer, 
    AssignDietPlan, AssignWorkoutPlan,
    MemberWorkoutLog, MemberExerciseLog, MemberBodyMetric,
    MemberFitnessGoal
)
from apps.attendance.models import MemberAttendance, MemberLeave
from apps.billing.models import Payment
from apps.management.models import DietPlan, WorkoutPlan


def member_required(view_func):
    """
    Decorator ensuring only authenticated gym members can access the member portal.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if hasattr(request.user, 'member_profile') and request.user.member_profile.gym:
            request.member = request.user.member_profile
            request.gym = request.member.gym
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Access restricted to Gym Members only.')
        return redirect('login')
    return _wrapped


@never_cache
@member_required
def member_dashboard(request):
    member = request.member
    gym = request.gym
    today = timezone.localdate()

    # 1. Membership Plan details
    latest_membership = member.latest_membership
    end_date = latest_membership.get_end_date() if latest_membership else None
    days_left = (end_date - today).days if end_date and end_date >= today else 0
    is_active = member.current_status == 'Active'

    # Auto-dispatch real-time in-app notification if plan is expiring or expired (with 24h deduplication)
    if latest_membership:
        if end_date and end_date < today:
            try:
                from apps.superadmin.notifications import notify_membership_expired
                notify_membership_expired(member=member, history=latest_membership)
            except Exception:
                pass
        elif 0 <= days_left <= 4:
            try:
                from apps.superadmin.notifications import notify_membership_expiring
                notify_membership_expiring(member=member, history=latest_membership, days_left=days_left)
            except Exception:
                pass

    # 2. Attendance & Workout Session Tracking
    active_attendance = MemberAttendance.objects.filter(
        member=member,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    today_records = MemberAttendance.objects.filter(
        member=member,
        check_in_time__date=today
    ).order_by('-check_in_time')

    latest_today_attendance = today_records.first()

    # Calculate cumulative workout time today
    today_seconds = 0
    for rec in today_records:
        if rec.check_out_time:
            today_seconds += int((rec.check_out_time - rec.check_in_time).total_seconds())
        else:
            today_seconds += int((timezone.now() - rec.check_in_time).total_seconds())

    today_hours = today_seconds // 3600
    today_minutes = (today_seconds % 3600) // 60
    today_duration_str = f"{today_hours}h {today_minutes}m" if today_seconds > 0 else "0m"

    current_month_checkins = MemberAttendance.objects.filter(
        member=member,
        check_in_time__year=today.year,
        check_in_time__month=today.month
    ).count()

    recent_checkins = MemberAttendance.objects.filter(
        member=member
    ).order_by('-check_in_time')[:5]

    # 3. Assigned Plans
    assigned_workout = AssignWorkoutPlan.objects.filter(
        member=member
    ).select_related('workout_plan').order_by('-id').first()

    assigned_diet = AssignDietPlan.objects.filter(
        member=member
    ).select_related('diet_plan').order_by('-id').first()

    # 4. Personal Trainer
    pt_assignment = PersonalTrainer.objects.filter(
        member=member, status='active', is_deleted=False
    ).select_related('trainer').first()

    pt_end_date = pt_assignment.get_end_date() if pt_assignment else None
    pt_days_left = (pt_end_date - today).days if pt_end_date and pt_end_date >= today else 0

    # 5. Financial Dues & Latest Payments
    due_amount = MembershipHistory.objects.filter(
        member=member, status='active', is_deleted=False
    ).aggregate(total_due=Sum(F('total_amount') - F('paid_amount')))['total_due'] or 0

    recent_payments = Payment.objects.filter(
        member=member,
        is_deleted=False
    ).exclude(
        membership_history__is_deleted=True
    ).exclude(
        personal_trainer__is_deleted=True
    ).order_by('-payment_date')[:5]

    context = {
        'member': member,
        'gym': gym,
        'latest_membership': latest_membership,
        'end_date': end_date,
        'days_left': days_left,
        'is_active': is_active,
        'active_attendance': active_attendance,
        'is_checked_in': active_attendance is not None,
        'today_records': today_records,
        'today_duration_str': today_duration_str,
        'current_month_checkins': current_month_checkins,
        'today_attendance': latest_today_attendance,
        'recent_checkins': recent_checkins,
        'assigned_workout': assigned_workout,
        'assigned_diet': assigned_diet,
        'pt_assignment': pt_assignment,
        'pt_end_date': pt_end_date,
        'pt_days_left': pt_days_left,
        'due_amount': due_amount,
        'recent_payments': recent_payments,
    }
    return render(request, 'portal/member/dashboard.html', context)


@never_cache
@member_required
def member_attendance_action(request):
    """
    Dedicated action view for member self-attendance (Gym Check In & Check Out).
    Supports standard POST and AJAX JSON calls.
    """
    if request.method != 'POST':
        return redirect('member_portal:dashboard')

    member = request.member
    gym = request.gym
    action = request.POST.get('action', '').strip().lower()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('format') == 'json'
    today = timezone.localdate()

    # Automatically close any dangling unclosed check-ins from previous days
    stale_records = MemberAttendance.objects.filter(
        member=member,
        check_out_time__isnull=True,
        check_in_time__date__lt=today
    )
    for stale in stale_records:
        stale.check_out_time = stale.check_in_time + timedelta(hours=2)
        stale.status = 'outside'
        stale.save()

    active_record = MemberAttendance.objects.filter(
        member=member,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    if action == 'checkin':
        # Verify active membership
        if member.current_status != 'Active':
            msg = f"Cannot check in: Your membership is currently {member.current_status}. Please visit the front desk to renew."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('member_portal:dashboard')

        if active_record:
            time_str = timezone.localtime(active_record.check_in_time).strftime('%I:%M %p')
            msg = f"You are already checked in since {time_str}."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.warning(request, msg)
            return redirect('member_portal:dashboard')

        record = MemberAttendance.objects.create(
            member=member,
            gym=gym,
            check_in_time=timezone.now(),
            status='inside'
        )
        time_str = timezone.localtime(record.check_in_time).strftime('%I:%M %p')
        msg = f"Gym check-in successful at {time_str}! Have a great workout."
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': msg,
                'check_in_time': time_str,
                'is_checked_in': True
            })
        messages.success(request, msg)
        return redirect('member_portal:dashboard')

    elif action == 'checkout':
        if not active_record:
            msg = "No active check-in found to check out from."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.warning(request, msg)
            return redirect('member_portal:dashboard')

        active_record.check_out_time = timezone.now()
        active_record.status = 'outside'
        active_record.save()

        duration_str = active_record.duration or '0m'
        time_str = timezone.localtime(active_record.check_out_time).strftime('%I:%M %p')
        msg = f"Checked out successfully at {time_str}. Workout completed: {duration_str}."
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': msg,
                'check_out_time': time_str,
                'duration': duration_str,
                'is_checked_in': False
            })
        messages.success(request, msg)
        return redirect('member_portal:dashboard')

    else:
        msg = "Invalid attendance action requested."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('member_portal:dashboard')


@never_cache
@member_required
def member_attendance_view(request):
    member = request.member
    gym = request.gym
    today = timezone.localdate()

    all_attendance = MemberAttendance.objects.filter(
        member=member
    ).order_by('-check_in_time')

    total_days = all_attendance.count()
    this_month_count = all_attendance.filter(
        check_in_time__year=today.year,
        check_in_time__month=today.month
    ).count()

    active_attendance = MemberAttendance.objects.filter(
        member=member,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    my_leaves = MemberLeave.objects.filter(
        member=member
    ).order_by('-created_at')[:30]

    context = {
        'member': member,
        'gym': gym,
        'all_attendance': all_attendance,
        'attendance_logs': all_attendance,
        'active_attendance': active_attendance,
        'is_checked_in': active_attendance is not None,
        'total_days': total_days,
        'this_month_count': this_month_count,
        'my_leaves': my_leaves,
    }
    return render(request, 'portal/member/attendance.html', context)


@never_cache
@member_required
def member_apply_leave(request):
    """
    Handles leave submission by gym members.
    """
    if request.method != 'POST':
        return redirect('member_portal:attendance')

    member = request.member
    gym = request.gym
    leave_type = request.POST.get('leave_type', 'personal').strip()
    start_date_str = request.POST.get('start_date', '').strip()
    end_date_str = request.POST.get('end_date', '').strip()
    reason = request.POST.get('reason', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('format') == 'json'

    if not start_date_str or not end_date_str:
        msg = "Start date and End date are both required."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('member_portal:attendance')

    try:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        if end_date < start_date:
            msg = "End date cannot be earlier than start date."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('member_portal:attendance')

        leave = MemberLeave.objects.create(
            gym=gym,
            member=member,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            status='pending'
        )

        msg = f"Leave application for {leave.duration_days} day(s) submitted successfully. Waiting for gym approval."
        if is_ajax:
            return JsonResponse({'status': 'success', 'message': msg})
        messages.success(request, msg)
        return redirect('member_portal:attendance')

    except Exception as e:
        msg = f"Failed to submit leave request: {str(e)}"
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('member_portal:attendance')


@never_cache
@member_required
def member_workout_view(request):
    member = request.member
    gym = request.gym

    assigned_workout = AssignWorkoutPlan.objects.filter(
        member=member
    ).select_related('workout_plan').order_by('-id').first()

    workout_plan = assigned_workout.workout_plan if assigned_workout else None

    context = {
        'member': member,
        'gym': gym,
        'assigned_workout': assigned_workout,
        'workout_plan': workout_plan,
    }
    return render(request, 'portal/member/workout.html', context)


@never_cache
@member_required
def member_diet_view(request):
    member = request.member
    gym = request.gym

    assigned_diet = AssignDietPlan.objects.filter(
        member=member
    ).select_related('diet_plan').order_by('-id').first()

    diet_plan = assigned_diet.diet_plan if assigned_diet else None

    context = {
        'member': member,
        'gym': gym,
        'assigned_diet': assigned_diet,
        'diet_plan': diet_plan,
    }
    return render(request, 'portal/member/diet.html', context)


@never_cache
@member_required
def member_billing_view(request):
    member = request.member
    gym = request.gym

    payments = Payment.objects.filter(
        member=member,
        is_deleted=False
    ).exclude(
        membership_history__is_deleted=True
    ).exclude(
        personal_trainer__is_deleted=True
    ).order_by('-payment_date')

    histories = MembershipHistory.objects.filter(
        member=member,
        is_deleted=False
    ).select_related('plan').order_by('-membership_start_date')

    due_amount = histories.filter(status='active').aggregate(
        total_due=Sum(F('total_amount') - F('paid_amount'))
    )['total_due'] or 0

    context = {
        'member': member,
        'gym': gym,
        'payments': payments,
        'histories': histories,
        'due_amount': due_amount,
    }
    return render(request, 'portal/member/billing.html', context)


@never_cache
@member_required
def member_profile_view(request):
    member = request.member
    gym = request.gym
    today = timezone.localdate()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            profession = request.POST.get('profession', '').strip()
            address = request.POST.get('address', '').strip()
            city = request.POST.get('city', '').strip()
            state = request.POST.get('state', '').strip()
            pincode = request.POST.get('pincode', '').strip()

            if not first_name:
                messages.error(request, 'First name cannot be empty.')
                return redirect('member_portal:profile')

            # Ensure email uniqueness within gym if provided and changed
            if email and email.lower() != (member.email or '').lower():
                existing = Member.objects.filter(gym=gym, email__iexact=email).exclude(id=member.id).first()
                if existing:
                    messages.error(request, 'This email address is already in use by another member in your gym.')
                    return redirect('member_portal:profile')

            member.first_name = first_name
            member.last_name = last_name
            member.email = email or None
            member.profession = profession
            member.address = address
            member.city = city
            member.state = state
            member.pincode = pincode

            if 'profile_picture' in request.FILES:
                pic = request.FILES['profile_picture']
                if pic.size > 5 * 1024 * 1024:
                    messages.error(request, 'Profile photo file size must be less than 5MB.')
                    return redirect('member_portal:profile')
                member.profile_picture = pic

            member.save()

            # Keep Django User synchronized
            if member.user:
                member.user.first_name = first_name
                member.user.last_name = last_name
                member.user.email = email
                member.user.save()

            messages.success(request, 'Profile details updated successfully!')
            return redirect('member_portal:profile')

        elif action == 'change_password' or 'change_password' in request.POST:
            current_pwd = request.POST.get('current_password', '').strip()
            new_pwd = request.POST.get('new_password', '').strip()
            confirm_pwd = request.POST.get('confirm_password', '').strip()

            if current_pwd and not request.user.check_password(current_pwd):
                messages.error(request, 'Current password verification failed.')
                return redirect('member_portal:profile')

            if len(new_pwd) < 6:
                messages.error(request, 'New password must be at least 6 characters long.')
            elif new_pwd != confirm_pwd:
                messages.error(request, 'New passwords do not match. Please try again.')
            else:
                request.user.set_password(new_pwd)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password updated successfully! Keep your credentials safe.')
                return redirect('member_portal:profile')

    # Rich contextual profile metrics
    latest_membership = MembershipHistory.objects.filter(
        member=member, is_deleted=False
    ).select_related('plan').order_by('-membership_start_date').first()

    end_date = latest_membership.get_end_date() if latest_membership else None
    days_left = (end_date - today).days if end_date and end_date >= today else 0
    is_active = (member.current_status == 'Active') or (latest_membership and latest_membership.status == 'active' and (end_date is None or end_date >= today))

    total_checkins = MemberAttendance.objects.filter(member=member).count()
    pt_assignment = PersonalTrainer.objects.filter(
        member=member, status='active', is_deleted=False
    ).select_related('trainer').first()

    fitness_goal = MemberFitnessGoal.objects.filter(member=member, gym=gym).first()
    latest_metric = MemberBodyMetric.objects.filter(member=member, gym=gym).order_by('-date', '-created_at').first()

    # Calculate Profile Completeness
    completeness_fields = [
        bool(member.first_name and member.last_name),
        bool(member.mobile_number),
        bool(member.email),
        bool(member.profile_picture),
        bool(member.address),
        bool(member.city),
        bool(member.profession),
        bool(member.gender),
    ]
    profile_pct = int((sum(1 for f in completeness_fields if f) / len(completeness_fields)) * 100)

    # Generate Live Scannable QR Code for Digital ID Pass
    qr_data_uri = None
    from django.urls import reverse
    verify_url = request.build_absolute_uri(reverse('member_portal:verify_pass', args=[member.member_id]))
    try:
        import qrcode
        import io
        import base64
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=5,
            border=1,
        )
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0a192f", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        qr_data_uri = f"data:image/png;base64,{qr_b64}"
    except Exception as e:
        qr_data_uri = None

    # Generate base64 Data URIs for profile photo and gym logo so card download/canvas has 0 CORS issues
    profile_pic_data_uri = None
    if member.profile_picture:
        try:
            import mimetypes
            with member.profile_picture.open('rb') as f:
                content = f.read()
                mime, _ = mimetypes.guess_type(member.profile_picture.name)
                mime = mime or 'image/jpeg'
                profile_pic_data_uri = f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"
        except Exception:
            profile_pic_data_uri = None

    gym_logo_data_uri = None
    if gym and gym.logo:
        try:
            import mimetypes
            with gym.logo.open('rb') as f:
                content = f.read()
                mime, _ = mimetypes.guess_type(gym.logo.name)
                mime = mime or 'image/png'
                gym_logo_data_uri = f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"
        except Exception:
            gym_logo_data_uri = None

    id_card_bg_data_uri = None
    try:
        from django.conf import settings
        import os
        bg_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'id_card_bg.png')
        if os.path.exists(bg_path):
            with open(bg_path, 'rb') as f:
                id_card_bg_data_uri = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except Exception:
        id_card_bg_data_uri = None

    context = {
        'member': member,
        'gym': gym,
        'latest_membership': latest_membership,
        'end_date': end_date,
        'days_left': days_left,
        'is_active': is_active,
        'total_checkins': total_checkins,
        'pt_assignment': pt_assignment,
        'fitness_goal': fitness_goal,
        'latest_metric': latest_metric,
        'profile_pct': profile_pct,
        'qr_data_uri': qr_data_uri,
        'profile_pic_data_uri': profile_pic_data_uri,
        'gym_logo_data_uri': gym_logo_data_uri,
        'id_card_bg_data_uri': id_card_bg_data_uri,
        'verify_url': verify_url,
    }
    return render(request, 'portal/member/profile.html', context)


def member_verify_pass_view(request, member_id):
    """
    Public verification endpoint to verify authenticity of digital pass via QR code scan.
    Accessible on mobile devices without requiring member login.
    """
    from apps.members.models import Member, MembershipHistory
    today = timezone.localdate()
    member = Member.objects.filter(member_id=member_id, is_deleted=False).select_related('gym').first()

    if not member:
        return render(request, 'portal/member/verify_pass.html', {
            'found': False,
            'member_id': member_id,
        })

    latest_membership = MembershipHistory.objects.filter(
        member=member, is_deleted=False
    ).select_related('plan').order_by('-membership_start_date').first()

    end_date = latest_membership.get_end_date() if latest_membership else None
    days_left = (end_date - today).days if end_date and end_date >= today else 0
    is_active = (getattr(member, 'current_status', None) == 'Active') or bool(
        latest_membership and latest_membership.status == 'active' and (end_date is None or end_date >= today)
    )

    context = {
        'found': True,
        'member': member,
        'gym': member.gym,
        'latest_membership': latest_membership,
        'end_date': end_date,
        'days_left': days_left,
        'is_active': is_active,
        'today': today,
    }
    return render(request, 'portal/member/verify_pass.html', context)


@never_cache
@member_required
def member_pt_view(request):
    member = request.member
    gym = request.gym
    today = timezone.localdate()

    # All PT history
    all_pt = PersonalTrainer.objects.filter(
        member=member, is_deleted=False
    ).select_related('trainer').order_by('-pt_start_date')

    active_pt = None
    pt_records = []
    for pt in all_pt:
        end_date = pt.get_end_date()
        is_current = (pt.status == 'active' and end_date >= today)
        days_left = (end_date - today).days if end_date >= today else 0
        total_days = (end_date - pt.pt_start_date).days or 1
        elapsed_days = (today - pt.pt_start_date).days if today >= pt.pt_start_date else 0
        progress_pct = min(100, max(0, int((elapsed_days / total_days) * 100)))

        item = {
            'record': pt,
            'trainer': pt.trainer,
            'end_date': end_date,
            'is_current': is_current,
            'days_left': days_left,
            'progress_pct': progress_pct,
            'due_amount': pt.due_amount,
        }
        pt_records.append(item)
        if is_current and not active_pt:
            active_pt = item

    total_pt_spent = all_pt.aggregate(total=Sum('paid_amount'))['total'] or 0
    total_pt_due = all_pt.filter(status='active').aggregate(total=Sum(F('total_amount') - F('paid_amount')))['total'] or 0
    total_pt_months = all_pt.aggregate(total=Sum('months'))['total'] or 0

    context = {
        'member': member,
        'gym': gym,
        'active_pt': active_pt,
        'pt_records': pt_records,
        'total_pt_spent': total_pt_spent,
        'total_pt_due': total_pt_due,
        'total_pt_months': total_pt_months,
    }
    return render(request, 'portal/member/personal_training.html', context)


@never_cache
@member_required
def member_progress_view(request):
    member = request.member
    gym = request.gym
    today = timezone.localdate()

    # Aggregate Core Stats
    workout_logs = MemberWorkoutLog.objects.filter(member=member, gym=gym).prefetch_related('exercises')
    total_workouts = workout_logs.count()
    total_minutes = workout_logs.aggregate(s=Sum('duration_minutes'))['s'] or 0
    total_hours = round(total_minutes / 60, 1)

    # Weekly streak: Workouts this current week (from Monday)
    start_of_week = today - timedelta(days=today.weekday())
    workouts_this_week = workout_logs.filter(date__gte=start_of_week).values('date').distinct().count()

    # Body metrics
    body_metrics = MemberBodyMetric.objects.filter(member=member, gym=gym).order_by('-date', '-created_at')
    latest_metric = body_metrics.first()
    first_metric = MemberBodyMetric.objects.filter(member=member, gym=gym).order_by('date', 'created_at').first()

    weight_delta = None
    if latest_metric and first_metric and latest_metric.id != first_metric.id:
        weight_delta = round(latest_metric.weight_kg - first_metric.weight_kg, 1)

    # Chart Data Preparation (Ascending by date for timeline)
    metrics_for_chart = list(MemberBodyMetric.objects.filter(member=member, gym=gym).order_by('date', 'created_at')[:20])
    chart_dates = [m.date.strftime('%d %b') for m in metrics_for_chart]
    chart_weights = [float(m.weight_kg) for m in metrics_for_chart]

    # Assigned workout routine
    assigned_workout = AssignWorkoutPlan.objects.filter(
        member=member
    ).select_related('workout_plan').order_by('-id').first()

    # Member Fitness Goal & Cricket-Style Chase Metrics
    fitness_goal = MemberFitnessGoal.objects.filter(member=member, gym=gym).first()
    goal_stats = None
    target_weights_json = json.dumps([])

    if fitness_goal:
        start_w = float(fitness_goal.starting_weight_kg)
        target_w = float(fitness_goal.target_weight_kg)
        current_w = float(latest_metric.weight_kg) if latest_metric else start_w

        total_target_delta = round(target_w - start_w, 1)
        current_growth_delta = round(current_w - start_w, 1)
        needed_growth_delta = round(target_w - current_w, 1)

        # Percentage progress
        if abs(total_target_delta) > 0:
            if total_target_delta < 0:
                pct = ((start_w - current_w) / (start_w - target_w)) * 100
            else:
                pct = ((current_w - start_w) / (target_w - start_w)) * 100
            progress_pct = max(0.0, min(100.0, round(pct, 1)))
        else:
            progress_pct = 100.0

        remaining_pct = round(100.0 - progress_pct, 1)

        # Days & Weeks Left
        days_left = None
        weeks_left = None
        if fitness_goal.target_date:
            diff_days = (fitness_goal.target_date - today).days
            days_left = diff_days
            weeks_left = max(0.5, diff_days / 7.0) if diff_days > 0 else 0.5

        # Required Run Rate (RRR - kg needed per week)
        required_pace = None
        if weeks_left and abs(needed_growth_delta) > 0 and (days_left and days_left > 0):
            required_pace = round(abs(needed_growth_delta) / weeks_left, 2)

        # Current Run Rate (CRR - actual kg changed per week)
        elapsed_days = max(1, (today - fitness_goal.created_at.date()).days)
        elapsed_weeks = max(0.5, elapsed_days / 7.0)
        current_pace = round(abs(current_growth_delta) / elapsed_weeks, 2)

        # Growth direction and badges
        if current_growth_delta < 0:
            growth_verb = "lost"
            growth_badge_class = "badge-soft-success"
            growth_badge_style = "background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;"
        elif current_growth_delta > 0:
            growth_verb = "gained"
            if total_target_delta > 0:
                growth_badge_class = "badge-soft-success"
                growth_badge_style = "background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0;"
            else:
                growth_badge_class = "badge-soft-danger"
                growth_badge_style = "background: #fff1f2; color: #be123c; border: 1px solid #fecdd3;"
        else:
            growth_verb = "maintained"
            growth_badge_class = "badge-soft-secondary"
            growth_badge_style = "background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;"

        if needed_growth_delta < 0:
            needed_verb = "to lose"
        elif needed_growth_delta > 0:
            needed_verb = "to gain"
        else:
            needed_verb = "reached"

        # Status Check (Match Result / Chase Analysis)
        is_goal_met = (
            (total_target_delta < 0 and current_w <= target_w) or
            (total_target_delta > 0 and current_w >= target_w)
        )
        moving_towards_target = (total_target_delta < 0 and current_growth_delta < 0) or (total_target_delta > 0 and current_growth_delta > 0)

        if is_goal_met:
            status_label = "Target Achieved"
            status_badge_class = "badge-soft-success"
            pace_analysis = "Match Won! You have successfully reached your fitness target!"
            pace_icon = "fa-trophy text-warning"
        elif days_left is not None and days_left <= 0:
            status_label = "Target Date Concluded"
            status_badge_class = "badge-soft-secondary"
            pace_analysis = "Target deadline concluded. Review your milestones and set your next challenge!"
            pace_icon = "fa-flag-checkered text-primary"
        elif moving_towards_target and required_pace and current_pace >= required_pace:
            status_label = "Ahead of Required Rate"
            status_badge_class = "badge-soft-success"
            pace_analysis = f"Cruising! Current rate ({current_pace} kg/wk) is matching required rate ({required_pace} kg/wk)."
            pace_icon = "fa-bolt text-success"
        elif moving_towards_target and required_pace:
            status_label = "Acceleration Required"
            status_badge_class = "badge-soft-warning"
            pace_analysis = f"Need to accelerate! Target requires {required_pace} kg/wk vs current {current_pace} kg/wk."
            pace_icon = "fa-chart-line text-warning"
        elif moving_towards_target:
            status_label = "Chasing Target"
            status_badge_class = "badge-soft-primary"
            pace_analysis = f"Steady progress towards your {target_w} kg target."
            pace_icon = "fa-crosshairs text-primary"
        else:
            status_label = "Recalibration Needed"
            status_badge_class = "badge-soft-danger"
            pace_analysis = f"Currently +{abs(current_growth_delta)} kg above baseline. Adjust diet & workouts to chase down the {abs(needed_growth_delta)} kg gap!"
            pace_icon = "fa-compass text-danger"

        goal_stats = {
            'goal_type_display': fitness_goal.get_goal_type_display(),
            'start_weight': start_w,
            'current_weight': current_w,
            'target_weight': target_w,
            'total_target_delta': abs(total_target_delta),
            'current_growth': abs(current_growth_delta),
            'growth_verb': growth_verb,
            'growth_badge_class': growth_badge_class,
            'growth_badge_style': growth_badge_style,
            'needed_growth': abs(needed_growth_delta),
            'needed_verb': needed_verb,
            'progress_pct': progress_pct,
            'remaining_pct': remaining_pct,
            'days_left': days_left,
            'required_pace': required_pace,
            'current_pace': current_pace,
            'status_label': status_label,
            'status_badge_class': status_badge_class,
            'pace_analysis': pace_analysis,
            'pace_icon': pace_icon,
            'is_achieved': is_goal_met,
            'target_weekly_workouts': fitness_goal.target_weekly_workouts,
            'target_body_fat': fitness_goal.target_body_fat,
            'motivation': fitness_goal.motivation_notes,
            'target_date': fitness_goal.target_date,
        }

        # Target reference line across the chart
        if chart_dates:
            target_weights_json = json.dumps([target_w] * len(chart_dates))

    context = {
        'member': member,
        'gym': gym,
        'total_workouts': total_workouts,
        'total_hours': total_hours,
        'workouts_this_week': workouts_this_week,
        'latest_metric': latest_metric,
        'weight_delta': weight_delta,
        'workout_logs': workout_logs[:20],
        'body_metrics': body_metrics[:15],
        'chart_dates_json': json.dumps(chart_dates),
        'chart_weights_json': json.dumps(chart_weights),
        'target_weights_json': target_weights_json,
        'fitness_goal': fitness_goal,
        'goal_stats': goal_stats,
        'assigned_workout': assigned_workout,
        'today': today,
    }
    return render(request, 'portal/member/progress.html', context)


@never_cache
@member_required
def member_set_goal_action(request):
    if request.method != 'POST':
        return redirect('member_portal:progress')

    member = request.member
    gym = request.gym

    goal_type = request.POST.get('goal_type', 'weight_loss')
    
    try:
        start_w = Decimal(request.POST.get('starting_weight_kg', '70')).quantize(Decimal('0.01'))
    except Exception:
        start_w = Decimal('70.00')

    try:
        target_w = Decimal(request.POST.get('target_weight_kg', '65')).quantize(Decimal('0.01'))
    except Exception:
        target_w = Decimal('65.00')

    body_fat_raw = request.POST.get('target_body_fat', '').strip()
    target_body_fat = None
    if body_fat_raw:
        try:
            target_body_fat = Decimal(body_fat_raw).quantize(Decimal('0.01'))
        except Exception:
            target_body_fat = None

    try:
        target_weekly_workouts = int(request.POST.get('target_weekly_workouts', 4) or 4)
    except Exception:
        target_weekly_workouts = 4

    target_date_raw = request.POST.get('target_date', '').strip()
    target_date = target_date_raw if target_date_raw else None
    motivation = request.POST.get('motivation_notes', '').strip()

    MemberFitnessGoal.objects.update_or_create(
        gym=gym,
        member=member,
        defaults={
            'goal_type': goal_type,
            'starting_weight_kg': start_w,
            'target_weight_kg': target_w,
            'target_body_fat': target_body_fat,
            'target_weekly_workouts': target_weekly_workouts,
            'target_date': target_date,
            'motivation_notes': motivation,
        }
    )

    messages.success(request, f"Fitness Goal locked in! Target: {target_w} kg.")
    return redirect('member_portal:progress')


@never_cache
@member_required
def member_log_workout_action(request):
    if request.method != 'POST':
        return redirect('member_portal:progress')

    member = request.member
    gym = request.gym

    title = request.POST.get('title', '').strip() or 'Workout Session'
    date_val = request.POST.get('date') or timezone.localdate()
    workout_type = request.POST.get('workout_type', 'strength')
    duration_minutes = int(request.POST.get('duration_minutes', 45) or 45)
    calories_burned_raw = request.POST.get('calories_burned', '').strip()
    calories_burned = int(calories_burned_raw) if calories_burned_raw.isdigit() else None
    energy_rating = int(request.POST.get('energy_rating', 4) or 4)
    notes = request.POST.get('notes', '').strip()

    log = MemberWorkoutLog.objects.create(
        gym=gym,
        member=member,
        date=date_val,
        title=title,
        workout_type=workout_type,
        duration_minutes=duration_minutes,
        calories_burned=calories_burned,
        energy_rating=energy_rating,
        notes=notes,
    )

    # Process dynamic exercise rows
    exercise_names = request.POST.getlist('exercise_name[]')
    sets_list = request.POST.getlist('sets[]')
    reps_list = request.POST.getlist('reps[]')
    weight_list = request.POST.getlist('weight[]')
    notes_list = request.POST.getlist('exercise_notes[]')

    for i, name in enumerate(exercise_names):
        name_clean = name.strip()
        if not name_clean:
            continue
        try:
            sets_val = int(sets_list[i]) if i < len(sets_list) and sets_list[i] else 3
        except (ValueError, IndexError):
            sets_val = 3

        reps_val = reps_list[i].strip() if i < len(reps_list) and reps_list[i] else "10-12"
        
        try:
            raw_w = weight_list[i].strip() if i < len(weight_list) and weight_list[i] else "0"
            weight_val = Decimal(raw_w).quantize(Decimal('0.01'))
            if weight_val < Decimal('0'):
                weight_val = Decimal('0.00')
            elif weight_val > Decimal('9999.99'):
                weight_val = Decimal('9999.99')
        except (ValueError, IndexError, Exception):
            weight_val = Decimal('0.00')

        ex_notes = notes_list[i].strip() if i < len(notes_list) else ""

        MemberExerciseLog.objects.create(
            workout_log=log,
            exercise_name=name_clean,
            sets=sets_val,
            reps=reps_val,
            weight_kg=weight_val,
            notes=ex_notes,
            order=i,
        )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Workout logged successfully!'})

    messages.success(request, f"Workout '{title}' logged successfully.")
    return redirect('member_portal:progress')


@never_cache
@member_required
def member_log_metrics_action(request):
    if request.method != 'POST':
        return redirect('member_portal:progress')

    member = request.member
    gym = request.gym

    date_val = request.POST.get('date') or timezone.localdate()
    try:
        weight_kg = Decimal(request.POST.get('weight_kg', '0')).quantize(Decimal('0.01'))
        if weight_kg < Decimal('0') or weight_kg > Decimal('9999.99'):
            raise ValueError
    except Exception:
        messages.error(request, 'Please provide a valid body weight.')
        return redirect('member_portal:progress')

    def parse_dec(key, max_val=Decimal('9999.99')):
        val = request.POST.get(key, '').strip()
        if val:
            try:
                d = Decimal(val).quantize(Decimal('0.01'))
                if d < Decimal('0'):
                    return Decimal('0.00')
                if d > max_val:
                    return max_val
                return d
            except Exception:
                return None
        return None

    body_fat = parse_dec('body_fat_percentage', Decimal('100.00'))
    chest = parse_dec('chest_inches')
    waist = parse_dec('waist_inches')
    biceps = parse_dec('biceps_inches')
    thighs = parse_dec('thighs_inches')
    notes = request.POST.get('notes', '').strip()

    photo_file = None
    if 'photo' in request.FILES:
        uploaded_photo = request.FILES['photo']
        if uploaded_photo.size > 5 * 1024 * 1024:
            messages.error(request, 'Progress photo file size must be less than 5MB.')
            return redirect('member_portal:progress')
        photo_file = uploaded_photo

    MemberBodyMetric.objects.create(
        gym=gym,
        member=member,
        date=date_val,
        weight_kg=weight_kg,
        body_fat_percentage=body_fat,
        chest_inches=chest,
        waist_inches=waist,
        biceps_inches=biceps,
        thighs_inches=thighs,
        photo=photo_file,
        notes=notes,
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'message': 'Body metrics recorded successfully!'})

    messages.success(request, f"Body metrics for {date_val} recorded successfully!")
    return redirect('member_portal:progress')


@never_cache
@member_required
def member_delete_workout_log(request, log_id):
    if request.method != 'POST':
        return redirect('member_portal:progress')

    member = request.member
    gym = request.gym
    log = get_object_or_404(MemberWorkoutLog, id=log_id, member=member, gym=gym)
    log.delete()
    messages.success(request, 'Workout session log deleted.')
    return redirect('member_portal:progress')


@never_cache
@member_required
def member_delete_metric(request, metric_id):
    if request.method != 'POST':
        return redirect('member_portal:progress')

    member = request.member
    gym = request.gym
    metric = get_object_or_404(MemberBodyMetric, id=metric_id, member=member, gym=gym)
    metric.delete()
    messages.success(request, 'Body metric record deleted.')
    return redirect('member_portal:progress')

