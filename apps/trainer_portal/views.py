import calendar
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Sum, F, Q
from functools import wraps

from apps.trainers.models import Trainer, TrainerSalary
from apps.trainers.views import compute_trainer_salary, amount_to_words_inr, generate_payslip_pdf_response
from apps.members.models import Member, PersonalTrainer, AssignDietPlan, AssignWorkoutPlan
from apps.attendance.models import TrainerAttendance, MemberAttendance, TrainerLeave
from apps.management.models import DietPlan, WorkoutPlan


def trainer_required(view_func):
    """
    Decorator ensuring only authenticated gym trainers can access the trainer portal.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if hasattr(request.user, 'trainer_profile') and request.user.trainer_profile.gym:
            request.trainer = request.user.trainer_profile
            request.gym = request.trainer.gym
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Access restricted to Gym Trainers only.')
        return redirect('login')
    return _wrapped


@never_cache
@trainer_required
def trainer_dashboard(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    # 1. Assigned Clients (Personal Training)
    pt_clients = PersonalTrainer.objects.filter(
        trainer=trainer, status='active', is_deleted=False
    ).select_related('member').order_by('-id')

    total_clients_count = pt_clients.count()

    # 2. Shift & Attendance Tracking
    active_attendance = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    today_records = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_in_time__date=today
    ).order_by('-check_in_time')

    latest_today_attendance = today_records.first()

    # Calculate cumulative time worked today
    today_seconds = 0
    for rec in today_records:
        if rec.check_out_time:
            today_seconds += int((rec.check_out_time - rec.check_in_time).total_seconds())
        else:
            today_seconds += int((timezone.now() - rec.check_in_time).total_seconds())

    today_hours = today_seconds // 3600
    today_minutes = (today_seconds % 3600) // 60
    today_duration_str = f"{today_hours}h {today_minutes}m" if today_seconds > 0 else "0m"

    this_month_sessions = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_in_time__year=today.year,
        check_in_time__month=today.month
    ).count()

    recent_logs = TrainerAttendance.objects.filter(
        trainer=trainer
    ).order_by('-check_in_time')[:5]

    # 3. Client Activity / Attendance Today
    client_ids = [pt.member_id for pt in pt_clients]
    clients_attended_today = MemberAttendance.objects.filter(
        member_id__in=client_ids,
        check_in_time__date=today
    ).select_related('member')

    # Compute expiring client packages (<= 5 days)
    expiring_clients = []
    for pt in pt_clients:
        end_date = pt.get_end_date()
        if end_date:
            days_left = (end_date - today).days
            if 0 <= days_left <= 5:
                pt.days_left = days_left
                expiring_clients.append(pt)

    this_month_salary = TrainerSalary.objects.filter(
        trainer=trainer, gym=gym, year=today.year, month=today.month
    ).first()

    context = {
        'trainer': trainer,
        'gym': gym,
        'pt_clients': pt_clients[:6],
        'clients': pt_clients[:6],
        'total_clients_count': total_clients_count,
        'expiring_clients': expiring_clients,
        'today_attendance': latest_today_attendance,
        'active_attendance': active_attendance,
        'is_checked_in': active_attendance is not None,
        'today_records': today_records,
        'today_duration_str': today_duration_str,
        'this_month_sessions': this_month_sessions,
        'recent_logs': recent_logs,
        'clients_attended_today': clients_attended_today,
        'this_month_salary': this_month_salary,
    }
    return render(request, 'portal/trainer/dashboard.html', context)


@never_cache
@trainer_required
def trainer_attendance_action(request):
    """
    Dedicated action view for trainer self-attendance (Clock In & Clock Out).
    Supports standard POST and AJAX JSON calls.
    """
    if request.method != 'POST':
        return redirect('trainer_portal:dashboard')

    trainer = request.trainer
    gym = request.gym
    action = request.POST.get('action', '').strip().lower()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('format') == 'json'
    today = timezone.localdate()

    # Automatically close any dangling unclosed check-ins from previous days
    stale_records = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_out_time__isnull=True,
        check_in_time__date__lt=today
    )
    for stale in stale_records:
        stale.check_out_time = stale.check_in_time + timezone.timedelta(hours=8)
        stale.status = 'outside'
        stale.save()

    active_record = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    if action == 'checkin':
        if active_record:
            time_str = timezone.localtime(active_record.check_in_time).strftime('%I:%M %p')
            msg = f"You are already clocked in since {time_str}."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.warning(request, msg)
            return redirect('trainer_portal:dashboard')

        record = TrainerAttendance.objects.create(
            trainer=trainer,
            gym=gym,
            check_in_time=timezone.now(),
            status='inside'
        )
        time_str = timezone.localtime(record.check_in_time).strftime('%I:%M %p')
        msg = f"Clocked in successfully at {time_str}! Shift has started."
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': msg,
                'check_in_time': time_str,
                'is_checked_in': True
            })
        messages.success(request, msg)
        return redirect('trainer_portal:dashboard')

    elif action == 'checkout':
        if not active_record:
            msg = "No active check-in found to clock out from."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.warning(request, msg)
            return redirect('trainer_portal:dashboard')

        active_record.check_out_time = timezone.now()
        active_record.status = 'outside'
        active_record.save()

        duration_str = active_record.duration or '0m'
        time_str = timezone.localtime(active_record.check_out_time).strftime('%I:%M %p')
        msg = f"Clocked out successfully at {time_str}. Total shift time: {duration_str}."
        if is_ajax:
            return JsonResponse({
                'status': 'success',
                'message': msg,
                'check_out_time': time_str,
                'duration': duration_str,
                'is_checked_in': False
            })
        messages.success(request, msg)
        return redirect('trainer_portal:dashboard')

    else:
        msg = "Invalid attendance action requested."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('trainer_portal:dashboard')


@never_cache
@trainer_required
def trainer_clients_view(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    pt_clients_raw = PersonalTrainer.objects.filter(
        trainer=trainer, is_deleted=False
    ).select_related('member').order_by('-id')

    clients_list = []
    for pt in pt_clients_raw:
        end_date = pt.get_end_date()
        days_left = (end_date - today).days if end_date >= today else 0
        is_active_pkg = (pt.status == 'active' and end_date >= today)
        clients_list.append({
            'record': pt,
            'member': pt.member,
            'end_date': end_date,
            'days_left': days_left,
            'is_active': is_active_pkg,
            'due_amount': pt.due_amount,
        })

    context = {
        'trainer': trainer,
        'gym': gym,
        'pt_clients': clients_list,
        'clients': clients_list,
    }
    return render(request, 'portal/trainer/clients.html', context)


@never_cache
@trainer_required
def trainer_pt_view(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    all_pt = PersonalTrainer.objects.filter(
        trainer=trainer, is_deleted=False
    ).select_related('member').order_by('-pt_start_date')

    active_pt_records = []
    expired_pt_records = []
    all_records = []

    total_trainer_fees = 0
    total_active_clients = 0
    total_due_amount = 0
    total_months_coached = 0

    for pt in all_pt:
        end_date = pt.get_end_date()
        is_current = (pt.status == 'active' and end_date >= today)
        days_left = (end_date - today).days if end_date >= today else 0
        total_days = (end_date - pt.pt_start_date).days or 1
        elapsed_days = (today - pt.pt_start_date).days if today >= pt.pt_start_date else 0
        progress_pct = min(100, max(0, int((elapsed_days / total_days) * 100)))

        item = {
            'record': pt,
            'member': pt.member,
            'end_date': end_date,
            'is_current': is_current,
            'days_left': days_left,
            'progress_pct': progress_pct,
            'due_amount': pt.due_amount,
        }
        all_records.append(item)

        total_trainer_fees += (pt.trainer_fee or 0)
        total_months_coached += (pt.months or 0)

        if is_current:
            active_pt_records.append(item)
            total_active_clients += 1
            if pt.due_amount > 0:
                total_due_amount += pt.due_amount
        else:
            expired_pt_records.append(item)

    context = {
        'trainer': trainer,
        'gym': gym,
        'all_records': all_records,
        'active_pt_records': active_pt_records,
        'expired_pt_records': expired_pt_records,
        'total_active_clients': total_active_clients,
        'total_records_count': len(all_records),
        'total_trainer_fees': total_trainer_fees,
        'total_due_amount': total_due_amount,
        'total_months_coached': total_months_coached,
    }
    return render(request, 'portal/trainer/personal_training.html', context)


@never_cache
@trainer_required
def trainer_client_detail_view(request, member_id):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    member = Member.objects.filter(id=member_id, gym=gym).first()
    if not member:
        messages.error(request, 'Member not found or you do not have access to this member.')
        return redirect('trainer_portal:dashboard')

    # Personal Training History with this trainer
    pt_records_raw = PersonalTrainer.objects.filter(
        trainer=trainer, member=member, is_deleted=False
    ).order_by('-pt_start_date')

    pt_history = []
    active_pt = None
    for pt in pt_records_raw:
        end_date = pt.get_end_date()
        is_current = (pt.status == 'active' and end_date >= today)
        days_left = (end_date - today).days if end_date >= today else 0
        total_days = (end_date - pt.pt_start_date).days or 1
        elapsed_days = (today - pt.pt_start_date).days if today >= pt.pt_start_date else 0
        progress_pct = min(100, max(0, int((elapsed_days / total_days) * 100)))

        item = {
            'record': pt,
            'end_date': end_date,
            'is_current': is_current,
            'days_left': days_left,
            'progress_pct': progress_pct,
            'due_amount': pt.due_amount,
        }
        pt_history.append(item)
        if is_current and not active_pt:
            active_pt = item

    assigned_workout = AssignWorkoutPlan.objects.filter(
        member=member
    ).select_related('workout_plan').order_by('-id').first()

    assigned_diet = AssignDietPlan.objects.filter(
        member=member
    ).select_related('diet_plan').order_by('-id').first()

    recent_attendance = MemberAttendance.objects.filter(
        member=member
    ).order_by('-check_in_time')[:10]

    context = {
        'trainer': trainer,
        'gym': gym,
        'member': member,
        'pt_history': pt_history,
        'active_pt': active_pt,
        'assigned_workout': assigned_workout,
        'assigned_diet': assigned_diet,
        'recent_attendance': recent_attendance,
    }
    return render(request, 'portal/trainer/client_detail.html', context)


@never_cache
@trainer_required
def trainer_attendance_view(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    all_attendance = TrainerAttendance.objects.filter(
        trainer=trainer
    ).order_by('-check_in_time')

    total_days = all_attendance.count()
    this_month_count = all_attendance.filter(
        check_in_time__year=today.year,
        check_in_time__month=today.month
    ).count()

    active_attendance = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_out_time__isnull=True
    ).order_by('-check_in_time').first()

    my_leaves = TrainerLeave.objects.filter(
        trainer=trainer
    ).order_by('-created_at')[:30]

    context = {
        'trainer': trainer,
        'gym': gym,
        'all_attendance': all_attendance,
        'attendance_logs': all_attendance,
        'active_attendance': active_attendance,
        'is_checked_in': active_attendance is not None,
        'total_days': total_days,
        'this_month_count': this_month_count,
        'my_leaves': my_leaves,
    }
    return render(request, 'portal/trainer/attendance.html', context)


@never_cache
@trainer_required
def trainer_apply_leave(request):
    """
    Handles leave submission by trainers (full-day or half-day).
    """
    if request.method != 'POST':
        return redirect('trainer_portal:attendance')

    trainer = request.trainer
    gym = request.gym
    leave_type = request.POST.get('leave_type', 'casual').strip()
    start_date_str = request.POST.get('start_date', '').strip()
    end_date_str = request.POST.get('end_date', '').strip()
    is_half_day = request.POST.get('is_half_day') in ['true', 'True', '1', 'on']
    half_day_period = request.POST.get('half_day_period', 'first_half').strip()
    reason = request.POST.get('reason', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.POST.get('format') == 'json'

    if not start_date_str:
        msg = "Start date is required to request leave."
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('trainer_portal:attendance')

    try:
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        if is_half_day or not end_date_str:
            end_date = start_date
        else:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        if end_date < start_date:
            msg = "End date cannot be earlier than start date."
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': msg})
            messages.error(request, msg)
            return redirect('trainer_portal:attendance')

        leave = TrainerLeave.objects.create(
            gym=gym,
            trainer=trainer,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            is_half_day=is_half_day,
            half_day_period=half_day_period if is_half_day else None,
            reason=reason,
            status='pending',
            is_paid=True
        )

        msg = f"Leave application for {leave.duration_days} day(s) submitted successfully. Waiting for admin approval."
        if is_ajax:
            return JsonResponse({'status': 'success', 'message': msg})
        messages.success(request, msg)
        return redirect('trainer_portal:attendance')

    except Exception as e:
        msg = f"Failed to submit leave request: {str(e)}"
        if is_ajax:
            return JsonResponse({'status': 'error', 'message': msg})
        messages.error(request, msg)
        return redirect('trainer_portal:attendance')


@never_cache
@trainer_required
def trainer_profile_view(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    if request.method == 'POST':
        if 'change_password' in request.POST:
            new_pwd = request.POST.get('new_password', '').strip()
            confirm_pwd = request.POST.get('confirm_password', '').strip()
            if len(new_pwd) < 6:
                messages.error(request, 'Password must be at least 6 characters long.')
            elif new_pwd != confirm_pwd:
                messages.error(request, 'Passwords do not match.')
            else:
                request.user.set_password(new_pwd)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Password updated successfully!')
                return redirect('trainer_portal:profile')
        elif 'update_profile' in request.POST:
            phone = request.POST.get('phone', '').strip()
            email = request.POST.get('email', '').strip()
            address = request.POST.get('address', '').strip()
            if phone:
                trainer.phone = phone
            if email:
                trainer.email = email
            if address:
                trainer.address = address
            if 'photo' in request.FILES:
                trainer.photo = request.FILES['photo']
            trainer.save()
            messages.success(request, 'Profile details updated successfully!')
            return redirect('trainer_portal:profile')

    # Quick Snapshot Counts
    active_clients_count = PersonalTrainer.objects.filter(
        trainer=trainer, status='active', is_deleted=False
    ).count()

    total_attendance_count = TrainerAttendance.objects.filter(
        trainer=trainer
    ).count()

    # Profile completeness score
    profile_fields = [trainer.name, trainer.phone, trainer.email, trainer.photo, trainer.specialization, trainer.address]
    filled_fields = sum(1 for f in profile_fields if f)
    profile_pct = int((filled_fields / len(profile_fields)) * 100)

    # Verification URL & QR Code
    from django.urls import reverse
    verify_url = request.build_absolute_uri(reverse('trainer_portal:verify_pass', args=[trainer.trainer_id]))
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
    except Exception:
        qr_data_uri = None

    # Base64 Data URIs for trainer photo and gym logo (0 CORS issues with html2canvas download)
    profile_pic_data_uri = None
    if trainer.photo:
        try:
            import mimetypes
            import base64
            with trainer.photo.open('rb') as f:
                content = f.read()
                mime, _ = mimetypes.guess_type(trainer.photo.name)
                mime = mime or 'image/jpeg'
                profile_pic_data_uri = f"data:{mime};base64,{base64.b64encode(content).decode('utf-8')}"
        except Exception:
            profile_pic_data_uri = None

    if not profile_pic_data_uri:
        try:
            import os
            import base64
            from django.conf import settings
            default_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'trainer_dp.png')
            if os.path.exists(default_path):
                with open(default_path, 'rb') as f:
                    content = f.read()
                profile_pic_data_uri = f"data:image/png;base64,{base64.b64encode(content).decode('utf-8')}"
        except Exception:
            pass

    gym_logo_data_uri = None
    if gym and gym.logo:
        try:
            import mimetypes
            import base64
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
        import os, base64
        bg_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'id_card_bg.png')
        if os.path.exists(bg_path):
            with open(bg_path, 'rb') as f:
                id_card_bg_data_uri = f"data:image/png;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    except Exception:
        id_card_bg_data_uri = None

    context = {
        'trainer': trainer,
        'gym': gym,
        'today': today,
        'active_clients_count': active_clients_count,
        'total_attendance_count': total_attendance_count,
        'profile_pct': profile_pct,
        'qr_data_uri': qr_data_uri,
        'profile_pic_data_uri': profile_pic_data_uri,
        'gym_logo_data_uri': gym_logo_data_uri,
        'id_card_bg_data_uri': id_card_bg_data_uri,
        'verify_url': verify_url,
    }
    return render(request, 'portal/trainer/profile.html', context)


def trainer_verify_pass_view(request, trainer_id):
    """
    Public verification endpoint to verify authenticity of digital coach pass via QR code scan.
    Accessible on mobile devices without requiring trainer login.
    """
    trainer = Trainer.objects.filter(trainer_id=trainer_id).select_related('gym').first()

    if not trainer:
        return render(request, 'portal/trainer/verify_pass.html', {
            'found': False,
            'trainer_id': trainer_id,
        })

    active_clients_count = PersonalTrainer.objects.filter(
        trainer=trainer, status='active', is_deleted=False
    ).count()

    context = {
        'found': True,
        'trainer': trainer,
        'gym': trainer.gym,
        'active_clients_count': active_clients_count,
        'today': timezone.localdate(),
    }
    return render(request, 'portal/trainer/verify_pass.html', context)


@never_cache
@trainer_required
def trainer_salary_view(request):
    trainer = request.trainer
    gym = request.gym
    today = timezone.localdate()

    try:
        selected_month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        selected_month = today.month

    try:
        selected_year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        selected_year = today.year

    # Check if salary record exists or compute if not yet marked as paid
    salary_record = TrainerSalary.objects.filter(
        trainer=trainer,
        gym=gym,
        month=selected_month,
        year=selected_year
    ).first()

    if not salary_record or salary_record.status != 'paid':
        salary_record = compute_trainer_salary(gym, trainer, selected_year, selected_month)

    # History of all salary records for this trainer
    salary_history = TrainerSalary.objects.filter(
        trainer=trainer,
        gym=gym
    ).order_by('-year', '-month')

    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    current_year = today.year
    years_list = list(range(current_year - 2, current_year + 2))
    month_name = calendar.month_name[selected_month]

    context = {
        'trainer': trainer,
        'gym': gym,
        'salary': salary_record,
        'salary_history': salary_history,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_month_name': month_name,
        'months': months_list,
        'years': years_list,
    }
    return render(request, 'portal/trainer/salary.html', context)


@never_cache
@trainer_required
def trainer_payslip_view(request, salary_id):
    trainer = request.trainer
    gym = request.gym
    salary = get_object_or_404(TrainerSalary, id=salary_id, trainer=trainer, gym=gym)

    month_name = calendar.month_name[salary.month]
    net_in_words = amount_to_words_inr(salary.net_salary)

    context = {
        'salary': salary,
        'trainer': trainer,
        'gym': gym,
        'month_name': month_name,
        'year': salary.year,
        'net_in_words': net_in_words,
        'is_trainer_portal': True,
    }

    if request.GET.get('download') == 'pdf':
        safe_name = trainer.name.replace(' ', '_')
        return generate_payslip_pdf_response(request, context, f"Payslip_{safe_name}_{month_name}_{salary.year}.pdf")

    return render(request, 'trainers/payslip.html', context)

