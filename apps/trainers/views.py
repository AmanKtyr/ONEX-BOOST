import calendar
from datetime import date, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Trainer, TrainerSalary
from .forms import TrainerForm
from apps.members.models import PersonalTrainer
from apps.attendance.models import TrainerAttendance, TrainerLeave

from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.views.decorators.cache import never_cache
from django.db import IntegrityError
from apps.superadmin.subscription_utils import check_resource_quota, get_gym_quota_status



@never_cache
@login_required(login_url='login')
@custom_permission_required('view_trainer')
def trainer_list(request):
    gym = getattr(request, 'gym', None)
    trainers_list = Trainer.objects.filter(gym=gym).order_by('-id')

    query = request.GET.get('q')
    if query:
        trainers_list = trainers_list.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query) |
            Q(specialization__icontains=query)
        ).distinct()

    trainers_list = trainers_list.order_by('-id')
    paginator = Paginator(trainers_list, 10)  # Show 10 trainers per page
    page = request.GET.get('page')

    try:
        trainers = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer, deliver first page.
        trainers = paginator.page(1)
    except EmptyPage:
        # If page is out of range (e.g. 9999), deliver last page of results.
        trainers = paginator.page(paginator.num_pages)

    return render(request, 'trainers/trainer_list.html', {'trainers': trainers})
    
@never_cache
@login_required(login_url='login')
@custom_permission_required('add_trainer')
def add_trainer(request):
    gym = getattr(request, 'gym', None)
    can_add, quota_error, quota_status = check_resource_quota(gym, 'trainer')

    if request.method == 'POST':
        if not can_add:
            messages.error(request, quota_error)
            return redirect('trainer_list')

        form = TrainerForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                trainer = form.save(commit=False)
                trainer.gym = gym
                trainer.save()

                # Provision Trainer User Account
                user, raw_password = trainer.create_or_update_user_account()
                request.session['registration_credentials'] = {
                    'account_type': 'Trainer',
                    'title': 'Trainer Registered Successfully!',
                    'name': trainer.name.strip(),
                    'id': trainer.trainer_id,
                    'username': trainer.trainer_id,
                    'mobile': trainer.phone or '',
                    'email': trainer.email or '',
                    'password': raw_password,
                    'gym_name': gym.name if gym else 'ONEX BOOST Gym',
                    'login_url': request.build_absolute_uri('/login/'),
                }

                messages.success(request, 'Trainer added successfully!')
                return redirect('trainer_list')
            except IntegrityError:
                form.add_error('email', 'A trainer with this email already exists.')
    else:
        form = TrainerForm()
    return render(request, 'trainers/add_trainer.html', {
        'form': form,
        'quota_status': quota_status,
        'quota_limit_reached': not can_add,
        'quota_error': quota_error,
    })

@never_cache
@login_required(login_url='login')
@custom_permission_required('view_trainer')
def trainer_profile(request, trainer_id):
    gym = getattr(request, 'gym', None)
    trainer = Trainer.objects.filter(id=trainer_id, gym=gym).first()
    if not trainer:
        messages.error(request, 'Trainer not found or has been removed.')
        return redirect('trainer_list')

    # Personal Training (PT) Clients
    pt_clients = PersonalTrainer.objects.select_related('member').filter(
        trainer=trainer, gym=gym, is_deleted=False
    ).order_by('-id')

    active_pt_clients = pt_clients.filter(status='active')
    expired_pt_clients = pt_clients.exclude(status='active')

    total_clients_count = pt_clients.count()
    active_clients_count = active_pt_clients.count()

    # Financial aggregations on PT clients
    total_pt_revenue = pt_clients.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_pt_paid = pt_clients.aggregate(paid=Sum('paid_amount'))['paid'] or Decimal('0.00')
    total_pt_due = total_pt_revenue - total_pt_paid

    # Monthly active PT client revenue estimate
    active_pt_monthly_earnings = sum(
        (client.trainer_fee / client.months) if client.months and client.trainer_fee else Decimal('0.00')
        for client in active_pt_clients
    )
    total_estimated_monthly_income = (trainer.salary or Decimal('0.00')) + active_pt_monthly_earnings

    # Attendance Records & Analytics
    attendance_records = TrainerAttendance.objects.filter(
        trainer=trainer, gym=gym
    ).order_by('-check_in_time')[:30]

    now = timezone.now()
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_attendance = TrainerAttendance.objects.filter(
        trainer=trainer, gym=gym, check_in_time__gte=current_month_start
    )
    month_present_days = month_attendance.values('check_in_time__date').distinct().count()

    total_seconds = 0
    for rec in month_attendance:
        if rec.check_in_time and rec.check_out_time:
            total_seconds += int((rec.check_out_time - rec.check_in_time).total_seconds())
    month_total_hours = round(total_seconds / 3600, 1)

    latest_attendance = attendance_records.first()

    # Leave Records
    leave_records = TrainerLeave.objects.filter(
        trainer=trainer, gym=gym
    ).order_by('-start_date')
    approved_leaves = leave_records.filter(status='approved').count()
    pending_leaves = leave_records.filter(status='pending').count()
    rejected_leaves = leave_records.filter(status='rejected').count()

    # Tenure Calculation
    tenure_str = "Recently Joined"
    if trainer.joining_date:
        days_joined = (timezone.localdate() - trainer.joining_date).days
        years = days_joined // 365
        months = (days_joined % 365) // 30
        if years > 0 and months > 0:
            tenure_str = f"{years} yr {months} mos"
        elif years > 0:
            tenure_str = f"{years} yr{'s' if years > 1 else ''}"
        elif months > 0:
            tenure_str = f"{months} mo{'s' if months > 1 else ''}"
        elif days_joined > 0:
            tenure_str = f"{days_joined} days"
        else:
            tenure_str = "Joined Today"

    context = {
        'trainer': trainer,
        'pt_clients': pt_clients,
        'active_pt_clients': active_pt_clients,
        'expired_pt_clients': expired_pt_clients,
        'total_clients_count': total_clients_count,
        'active_clients_count': active_clients_count,
        'total_pt_revenue': total_pt_revenue,
        'total_pt_paid': total_pt_paid,
        'total_pt_due': total_pt_due,
        'active_pt_monthly_earnings': active_pt_monthly_earnings,
        'total_estimated_monthly_income': total_estimated_monthly_income,
        'attendance_records': attendance_records,
        'month_present_days': month_present_days,
        'month_total_hours': month_total_hours,
        'latest_attendance': latest_attendance,
        'leave_records': leave_records,
        'approved_leaves': approved_leaves,
        'pending_leaves': pending_leaves,
        'rejected_leaves': rejected_leaves,
        'tenure_str': tenure_str,
    }
    return render(request, 'trainers/trainer_profile.html', context)


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
def edit_trainer(request, trainer_id):
    gym = getattr(request, 'gym', None)
    trainer = Trainer.objects.filter(id=trainer_id, gym=gym).first()
    if not trainer:
        messages.error(request, 'Trainer not found.')
        return redirect('trainer_list')
    if request.method == 'POST':
        form = TrainerForm(request.POST, request.FILES, instance=trainer)
        if form.is_valid():
            form.save()
            if trainer.user:
                names = (trainer.name or '').strip().split(' ', 1)
                trainer.user.first_name = names[0]
                trainer.user.last_name = names[1] if len(names) > 1 else ''
                if trainer.email:
                    trainer.user.email = trainer.email
                trainer.user.save()
            messages.success(request, 'Trainer updated successfully!')
            return redirect('trainer_profile', trainer_id=trainer.id)
    else:
        form = TrainerForm(instance=trainer)
    return render(request, 'trainers/edit_trainer.html', {'form': form, 'trainer': trainer})

@never_cache
@login_required(login_url='login')
@require_POST
@custom_permission_required('delete_trainer')
def delete_trainer(request, trainer_id):
    gym = getattr(request, 'gym', None)
    trainer = Trainer.objects.filter(id=trainer_id, gym=gym).first()
    if not trainer:
        return JsonResponse({'status': 'error', 'message': 'Trainer not found.'}, status=404)
    try:
        trainer.delete()
        messages.success(request, 'Trainer has been deleted successfully.')
        return JsonResponse({'status': 'success', 'message': 'Trainer deleted successfully.'})
    except Exception as e:
        messages.error(request, f'An error occurred: {e}')
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
def toggle_trainer_status(request, trainer_id):
    gym = getattr(request, 'gym', None)
    trainer = Trainer.objects.filter(id=trainer_id, gym=gym).first()
    if not trainer:
        messages.error(request, 'Trainer not found.')
        return redirect('trainer_list')
    trainer.is_active = not trainer.is_active
    trainer.save()
    messages.success(request, f"Trainer {trainer.name} has been marked as {'Active' if trainer.is_active else 'Inactive'}.")
    referer = request.META.get('HTTP_REFERER', '')
    if 'profile' in referer:
        return redirect('trainer_profile', trainer_id=trainer.id)
    return redirect('trainer_list')


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
@require_POST
def reset_trainer_password(request, trainer_id):
    gym = getattr(request, 'gym', None)
    trainer = Trainer.objects.filter(id=trainer_id, gym=gym).first()
    if not trainer:
        return JsonResponse({'status': 'error', 'message': 'Trainer not found.'}, status=404)
    
    custom_pwd = request.POST.get('new_password', '').strip()
    if not custom_pwd:
        import random
        phone_suffix = trainer.phone[-4:] if trainer.phone and len(trainer.phone) >= 4 else str(random.randint(1000, 9999))
        custom_pwd = f"Fit@{phone_suffix}"
        
    user, raw_pwd = trainer.create_or_update_user_account(raw_password=custom_pwd)
    
    login_url = request.build_absolute_uri('/login/')
    share_text = f"*ONEX BOOST Gym Password Reset*\n\nHi {trainer.name},\nYour trainer account password has been reset successfully.\n\n• *Username / ID:* {trainer.trainer_id}\n• *Mobile:* {trainer.phone or 'N/A'}\n• *New Password:* {raw_pwd}\n• *Login URL:* {login_url}\n\nYou can log in using your Mobile Number or Username."
    
    return JsonResponse({
        'status': 'success',
        'message': f'Password for {trainer.name} has been reset successfully!',
        'name': trainer.name,
        'trainer_id': trainer.trainer_id,
        'username': user.username,
        'mobile': trainer.phone,
        'new_password': raw_pwd,
        'share_text': share_text,
    })


def compute_trainer_salary(gym, trainer, year, month):
    """
    Computes/updates the monthly salary for a trainer based on:
    - Present days (clocked in >= 4 hours or active)
    - Half days (clocked in < 4 hours or half-day approved leave)
    - Paid leave days (approved leaves marked as paid)
    - Unpaid leave days (approved leaves marked as unpaid)
    - Absent days (elapsed working days without attendance or approved leave)
    - Payable days = present_days + paid_leave_days + (0.5 * half_days)
    - Base salary earned = (base_salary / total_days) * payable_days
    - PT commission = active PT clients * trainer.pt_monthly_rate
    - Net salary = base_salary_earned + pt_commission + bonus - deductions
    """
    days_in_month = calendar.monthrange(year, month)[1]
    today = timezone.localdate()

    if year < today.year or (year == today.year and month < today.month):
        eval_days = days_in_month
    elif year == today.year and month == today.month:
        eval_days = today.day
    else:
        eval_days = 0

    first_day = date(year, month, 1)
    last_day = date(year, month, days_in_month)

    # 1. Fetch attendance records for this month
    attendances = TrainerAttendance.objects.filter(
        trainer=trainer,
        check_in_time__date__gte=first_day,
        check_in_time__date__lte=last_day
    )
    att_by_date = {}
    for att in attendances:
        att_date = timezone.localtime(att.check_in_time).date()
        if att.check_out_time:
            dur = (att.check_out_time - att.check_in_time).total_seconds()
        else:
            dur = max(0, (timezone.now() - att.check_in_time).total_seconds())
        att_by_date[att_date] = att_by_date.get(att_date, 0.0) + dur

    # 2. Fetch approved leaves overlapping with this month
    approved_leaves = TrainerLeave.objects.filter(
        trainer=trainer,
        status='approved',
        start_date__lte=last_day,
        end_date__gte=first_day
    )

    leaves_by_date = {}
    for leave in approved_leaves:
        cur = max(first_day, leave.start_date)
        end_cur = min(last_day, leave.end_date)
        while cur <= end_cur:
            leaves_by_date[cur] = leave
            cur += timedelta(days=1)

    # 3. Categorize each day up to eval_days
    present_days = Decimal('0.0')
    half_days = 0
    paid_leave_days = Decimal('0.0')
    unpaid_leave_days = Decimal('0.0')
    absent_days = Decimal('0.0')

    for day_num in range(1, eval_days + 1):
        d = date(year, month, day_num)
        has_att = d in att_by_date
        has_leave = d in leaves_by_date

        if has_att:
            dur_seconds = att_by_date[d]
            if dur_seconds >= 14400:  # 4 hours
                present_days += Decimal('1.0')
            else:
                half_days += 1
        elif has_leave:
            leave = leaves_by_date[d]
            if leave.is_half_day:
                half_days += 1
            elif leave.is_paid:
                paid_leave_days += Decimal('1.0')
            else:
                unpaid_leave_days += Decimal('1.0')
        else:
            absent_days += Decimal('1.0')

    payable_days = present_days + paid_leave_days + (Decimal('0.5') * Decimal(half_days))
    base_salary = trainer.salary or Decimal('0.00')

    if days_in_month > 0:
        base_salary_earned = (base_salary / Decimal(days_in_month)) * payable_days
    else:
        base_salary_earned = Decimal('0.00')
    base_salary_earned = base_salary_earned.quantize(Decimal('0.01'))

    pt_clients_count = PersonalTrainer.objects.filter(
        trainer=trainer,
        status='active',
        is_deleted=False
    ).count()
    pt_monthly_rate = getattr(trainer, 'personal_training_monthly_amount', None) or Decimal('0.00')
    pt_commission = (Decimal(pt_clients_count) * pt_monthly_rate).quantize(Decimal('0.01'))

    salary_record = TrainerSalary.objects.filter(
        trainer=trainer,
        year=year,
        month=month
    ).first()

    bonus = Decimal('0.00')
    deductions = Decimal('0.00')
    status = 'draft'
    remarks = ''
    payment_date = None
    payment_mode = None
    transaction_id = None

    if salary_record:
        bonus = salary_record.bonus
        deductions = salary_record.deductions
        status = salary_record.status
        remarks = salary_record.remarks
        payment_date = salary_record.payment_date
        payment_mode = salary_record.payment_mode
        transaction_id = salary_record.transaction_id

    net_salary = max(Decimal('0.00'), base_salary_earned + pt_commission + bonus - deductions).quantize(Decimal('0.01'))

    salary_obj, _ = TrainerSalary.objects.update_or_create(
        trainer=trainer,
        year=year,
        month=month,
        defaults={
            'gym': gym,
            'base_salary': base_salary,
            'total_days': days_in_month,
            'present_days': present_days,
            'half_days': half_days,
            'paid_leave_days': paid_leave_days,
            'unpaid_leave_days': unpaid_leave_days,
            'absent_days': absent_days,
            'payable_days': payable_days,
            'base_salary_earned': base_salary_earned,
            'pt_clients_count': pt_clients_count,
            'pt_commission': pt_commission,
            'bonus': bonus,
            'deductions': deductions,
            'net_salary': net_salary,
            'status': status,
            'remarks': remarks,
            'payment_date': payment_date,
            'payment_mode': payment_mode,
            'transaction_id': transaction_id,
        }
    )
    return salary_obj


def amount_to_words_inr(num):
    """Converts a Decimal/numeric value to Indian Currency Words."""
    try:
        n = int(num)
        if n <= 0:
            return "Zero Rupees Only"

        ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
                "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

        def two_digits(val):
            if val < 20:
                return ones[val]
            return tens[val // 10] + (" " + ones[val % 10] if val % 10 != 0 else "")

        def three_digits(val):
            h = val // 100
            rem = val % 100
            res = ""
            if h > 0:
                res += two_digits(h) + " Hundred"
            if rem > 0:
                res += (" " if res else "") + two_digits(rem)
            return res

        parts = []
        crore = n // 10000000
        n %= 10000000
        lakh = n // 100000
        n %= 100000
        thousand = n // 1000
        rem = n % 1000

        if crore > 0:
            parts.append(two_digits(crore) + " Crore")
        if lakh > 0:
            parts.append(two_digits(lakh) + " Lakh")
        if thousand > 0:
            parts.append(two_digits(thousand) + " Thousand")
        if rem > 0:
            parts.append(three_digits(rem))

        return " ".join([p for p in parts if p]).strip() + " Rupees Only"
    except Exception:
        return f"Rupees {num} Only"


@never_cache
@login_required(login_url='login')
@custom_permission_required('view_trainer')
def trainer_salary_list(request):
    gym = getattr(request, 'gym', None)
    today = timezone.localdate()

    try:
        selected_month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        selected_month = today.month

    try:
        selected_year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        selected_year = today.year

    active_trainers = Trainer.objects.filter(gym=gym, is_active=True).order_by('name')
    for trainer in active_trainers:
        compute_trainer_salary(gym, trainer, selected_year, selected_month)

    salaries_qs = TrainerSalary.objects.filter(
        gym=gym,
        year=selected_year,
        month=selected_month
    ).select_related('trainer').order_by('trainer__name')

    status_filter = request.GET.get('status', 'all').strip()
    if status_filter and status_filter != 'all':
        salaries_qs = salaries_qs.filter(status=status_filter)

    query = request.GET.get('q', '').strip()
    if query:
        salaries_qs = salaries_qs.filter(
            Q(trainer__name__icontains=query) |
            Q(trainer__trainer_id__icontains=query) |
            Q(trainer__phone__icontains=query)
        )

    all_month_salaries = TrainerSalary.objects.filter(gym=gym, year=selected_year, month=selected_month)
    total_payroll = all_month_salaries.aggregate(total=Sum('net_salary'))['total'] or Decimal('0.00')
    total_paid = all_month_salaries.filter(status='paid').aggregate(total=Sum('net_salary'))['total'] or Decimal('0.00')
    total_pending = all_month_salaries.exclude(status='paid').aggregate(total=Sum('net_salary'))['total'] or Decimal('0.00')
    total_trainers_count = all_month_salaries.count()

    months_list = [(i, calendar.month_name[i]) for i in range(1, 13)]
    current_year = today.year
    years_list = list(range(current_year - 2, current_year + 3))

    context = {
        'salaries': salaries_qs,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'selected_month_name': calendar.month_name[selected_month],
        'months': months_list,
        'years': years_list,
        'status_filter': status_filter,
        'search_query': query,
        'total_payroll': total_payroll,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'total_trainers_count': total_trainers_count,
        'payment_modes': TrainerSalary.PAYMENT_MODE_CHOICES,
    }
    return render(request, 'trainers/salary_list.html', context)


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
def recalculate_trainer_salaries(request):
    gym = getattr(request, 'gym', None)
    today = timezone.localdate()

    try:
        month = int(request.GET.get('month', today.month))
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        month, year = today.month, today.year

    active_trainers = Trainer.objects.filter(gym=gym, is_active=True)
    count = 0
    for trainer in active_trainers:
        compute_trainer_salary(gym, trainer, year, month)
        count += 1

    messages.success(request, f"Successfully recalculated salaries for {count} trainer(s) for {calendar.month_name[month]} {year}.")
    return redirect(f"{redirect('trainer_salary_list').url}?month={month}&year={year}")


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
@require_POST
def update_trainer_salary_adjustment(request, salary_id):
    gym = getattr(request, 'gym', None)
    salary = get_object_or_404(TrainerSalary, id=salary_id, gym=gym)

    try:
        bonus_val = Decimal(request.POST.get('bonus', '0') or '0')
        deductions_val = Decimal(request.POST.get('deductions', '0') or '0')
        remarks_val = request.POST.get('remarks', '').strip()

        salary.bonus = max(Decimal('0.00'), bonus_val)
        salary.deductions = max(Decimal('0.00'), deductions_val)
        salary.remarks = remarks_val
        salary.net_salary = max(Decimal('0.00'), salary.base_salary_earned + salary.pt_commission + salary.bonus - salary.deductions).quantize(Decimal('0.01'))
        salary.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'success',
                'message': f'Salary adjustments updated for {salary.trainer.name}.',
                'bonus': str(salary.bonus),
                'deductions': str(salary.deductions),
                'net_salary': str(salary.net_salary)
            })

        messages.success(request, f"Salary adjustments saved for {salary.trainer.name}. Net: ₹{salary.net_salary}")
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        messages.error(request, f"Error updating salary adjustments: {e}")

    return redirect(f"{redirect('trainer_salary_list').url}?month={salary.month}&year={salary.year}")


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
def approve_trainer_salary(request, salary_id):
    gym = getattr(request, 'gym', None)
    salary = get_object_or_404(TrainerSalary, id=salary_id, gym=gym)

    if salary.status != 'paid':
        salary.status = 'approved'
        salary.save(update_fields=['status', 'updated_at'])
        messages.success(request, f"Salary for {salary.trainer.name} ({calendar.month_name[salary.month]} {salary.year}) has been approved!")
    else:
        messages.info(request, "Salary is already marked as paid.")

    return redirect(f"{redirect('trainer_salary_list').url}?month={salary.month}&year={salary.year}")


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_trainer')
@require_POST
def pay_trainer_salary(request, salary_id):
    gym = getattr(request, 'gym', None)
    salary = get_object_or_404(TrainerSalary, id=salary_id, gym=gym)

    payment_mode = request.POST.get('payment_mode', 'cash').strip()
    payment_date_str = request.POST.get('payment_date', '').strip()
    transaction_id = request.POST.get('transaction_id', '').strip()
    remarks = request.POST.get('remarks', '').strip()

    if payment_date_str:
        try:
            from datetime import datetime
            payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        except ValueError:
            payment_date = timezone.localdate()
    else:
        payment_date = timezone.localdate()

    salary.status = 'paid'
    salary.payment_mode = payment_mode
    salary.payment_date = payment_date
    salary.transaction_id = transaction_id
    if remarks:
        salary.remarks = remarks
    salary.save()

    messages.success(request, f"Salary of ₹{salary.net_salary} for {salary.trainer.name} marked as PAID via {salary.get_payment_mode_display()}.")
    return redirect(f"{redirect('trainer_salary_list').url}?month={salary.month}&year={salary.year}")


def generate_payslip_pdf_response(request, context, filename):
    import os
    from io import BytesIO
    from django.http import HttpResponse
    from django.template.loader import render_to_string
    from django.conf import settings
    from xhtml2pdf import pisa

    def link_callback(uri, rel):
        if uri.startswith(settings.MEDIA_URL):
            path = os.path.join(settings.MEDIA_ROOT, uri[len(settings.MEDIA_URL):])
        elif uri.startswith(settings.STATIC_URL):
            path = os.path.join(settings.STATIC_ROOT or settings.BASE_DIR, uri[len(settings.STATIC_URL):])
        else:
            return uri
        return path if os.path.isfile(path) else uri

    html = render_to_string('trainers/payslip_pdf.html', context, request=request)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode('utf-8')), result, link_callback=link_callback)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    return HttpResponse("Error generating PDF", status=500)


@never_cache
@login_required(login_url='login')
@custom_permission_required('view_trainer')
def trainer_payslip(request, salary_id):
    gym = getattr(request, 'gym', None)
    salary = get_object_or_404(TrainerSalary, id=salary_id, gym=gym)
    trainer = salary.trainer

    month_name = calendar.month_name[salary.month]
    net_in_words = amount_to_words_inr(salary.net_salary)

    context = {
        'salary': salary,
        'trainer': trainer,
        'gym': gym,
        'month_name': month_name,
        'year': salary.year,
        'net_in_words': net_in_words,
        'is_trainer_portal': False,
    }

    if request.GET.get('download') == 'pdf':
        safe_name = trainer.name.replace(' ', '_')
        return generate_payslip_pdf_response(request, context, f"Payslip_{safe_name}_{month_name}_{salary.year}.pdf")

    return render(request, 'trainers/payslip.html', context)
