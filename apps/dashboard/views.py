from django.shortcuts import render, redirect
from django.utils import timezone
from datetime import timedelta
from apps.members.models import Member, MembershipHistory, PersonalTrainer
from django.http import JsonResponse
from django.db.models.functions import TruncMonth
from django.db.models import Count, Q, Prefetch
from django.db import models
from apps.trainers.models import Trainer
from apps.attendance.models import MemberAttendance, TrainerAttendance
from apps.enquiry.models import Enquiry
from apps.billing.models import Payment

from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from apps.login.decorators import custom_permission_required
from apps.superadmin.subscription_utils import get_gym_quota_status
from apps.superadmin.models import SubscriptionPlan


@never_cache
@login_required(login_url='login')
def dashboard(request):
    role = request.session.get('role')
    if role == 'member' or hasattr(request.user, 'member_profile'):
        return redirect('member_portal:dashboard')
    if role == 'trainer' or hasattr(request.user, 'trainer_profile'):
        return redirect('trainer_portal:dashboard')

    gym = getattr(request, 'gym', None)
    today = timezone.now().date()

    # Single optimized query with all related data prefetched
    members = Member.objects.filter(gym=gym, is_deleted=False).prefetch_related(
        Prefetch('membership_history',
                 queryset=MembershipHistory.objects.filter(is_deleted=False).select_related('plan').prefetch_related('freezes')),
    )
    total_members = members.count()

    # Single pass through members to compute active, upcoming, expired
    active_members = 0
    upcoming_expiries = []
    expired_members = []
    seven_days_from_now = today + timedelta(days=7)

    for member in members:
        latest_membership = member.latest_membership
        if latest_membership:
            end_date = latest_membership.get_end_date()
            if end_date:
                if end_date >= today:
                    active_members += 1
                if today <= end_date <= seven_days_from_now:
                    upcoming_expiries.append((member, end_date))
                elif end_date < today:
                    expired_members.append((member, end_date))

    inactive_members = total_members - active_members

    # Sort using cached end_date (no re-computation)
    upcoming_expiries = [m for m, _ in sorted(upcoming_expiries, key=lambda x: x[1])][:10]
    expired_members = [m for m, _ in sorted(expired_members, key=lambda x: x[1], reverse=True)][:10]

    # New members in last 30 days (single DB query)
    thirty_days_ago = today - timedelta(days=30)
    new_members_last_30_days = Member.objects.filter(
        gym=gym, is_deleted=False,
        membership_history__is_deleted=False,
        membership_history__membership_start_date__gte=thirty_days_ago
    ).distinct().count()

    # Member growth chart data (single DB query)
    six_months_ago = timezone.now() - timedelta(days=180)
    new_members_data = list(Member.objects.filter(
        gym=gym, is_deleted=False,
        membership_history__is_deleted=False,
        membership_history__membership_start_date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('membership_history__membership_start_date')
    ).values('month').annotate(
        count=Count('id', distinct=True)
    ).order_by('month'))

    month_labels = [item['month'].strftime("%b") for item in new_members_data]
    new_member_counts = [item['count'] for item in new_members_data]

    # Expired members per month — use already-fetched members (no extra queries)
    expired_member_counts = []
    for month_data in new_members_data:
        month_start = month_data['month'].date() if hasattr(month_data['month'], 'date') else month_data['month']
        next_month_year = month_start.year
        next_month_month = month_start.month + 1
        if next_month_month > 12:
            next_month_month = 1
            next_month_year += 1
        month_end = month_start.replace(year=next_month_year, month=next_month_month, day=1)

        expired_count = 0
        for member in members:
            latest_membership = member.latest_membership
            if latest_membership:
                end_date = latest_membership.get_end_date()
                if end_date and month_start <= end_date < month_end:
                    expired_count += 1
        expired_member_counts.append(expired_count)

    # Attendance data (2 queries with select_related)
    today_min = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_max = timezone.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    member_attendance = MemberAttendance.objects.filter(
        gym=gym, check_in_time__range=(today_min, today_max)
    ).select_related('member')
    trainer_attendance = TrainerAttendance.objects.filter(
        gym=gym, check_in_time__range=(today_min, today_max)
    ).select_related('trainer')

    present_members_count = member_attendance.count()
    present_trainers_count = trainer_attendance.count()
    today_attendance_count = present_members_count + present_trainers_count

    # Combined attendance — only fetch top 10
    combined_attendance = sorted(
        list(member_attendance[:10]) + list(trainer_attendance[:10]),
        key=lambda x: x.check_in_time,
        reverse=True
    )[:10]

    total_trainers = Trainer.objects.filter(gym=gym).count()
    absent_members_count = max(0, total_members - present_members_count)
    absent_trainers_count = max(0, total_trainers - present_trainers_count)

    # Enquiries (upcoming follow-ups first, fallback to latest active enquiries)
    recent_enquiries = Enquiry.objects.filter(
        gym=gym, next_follow_up_date__gte=today
    ).order_by('next_follow_up_date')[:5]

    if not recent_enquiries.exists():
        recent_enquiries = Enquiry.objects.filter(
            gym=gym
        ).exclude(status__in=['converted', 'closed']).order_by('-id')[:5]
        if not recent_enquiries.exists():
            recent_enquiries = Enquiry.objects.filter(gym=gym).order_by('-id')[:5]

    total_enquiries = Enquiry.objects.filter(gym=gym).count()

    # Dues (2 queries)
    membership_dues = MembershipHistory.objects.filter(
        gym=gym, status='active', is_deleted=False, member__is_deleted=False
    ).exclude(paid_amount=models.F('total_amount')).select_related('member', 'plan')
    pt_dues = PersonalTrainer.objects.filter(
        gym=gym, status='active', is_deleted=False, member__is_deleted=False
    ).exclude(paid_amount=models.F('total_amount')).select_related('member', 'trainer')

    future_dues = [
        due for due in list(membership_dues) + list(pt_dues)
        if due.follow_up_date and due.follow_up_date >= today
    ]
    all_dues = sorted(future_dues, key=lambda x: x.follow_up_date)
    total_dues = len(all_dues)
    recent_dues = all_dues[:5]

    # Recent Payments (1 query)
    recent_payments = Payment.objects.filter(
        member__gym=gym,
        is_deleted=False,
        member__is_deleted=False
    ).exclude(
        membership_history__is_deleted=True
    ).exclude(
        personal_trainer__is_deleted=True
    ).select_related('member').order_by('-payment_date')[:10]
    total_recent_payments = sum(payment.amount for payment in recent_payments)

    # Birthdays — single combined query instead of 7 separate queries
    today_birthdays = Member.objects.filter(
        gym=gym, is_deleted=False,
        date_of_birth__month=today.month, date_of_birth__day=today.day
    )

    # Upcoming birthdays: 1 query with OR conditions
    birthday_q = Q()
    for i in range(1, 8):
        future_date = today + timedelta(days=i)
        birthday_q |= Q(date_of_birth__month=future_date.month, date_of_birth__day=future_date.day)

    upcoming_birthdays_list = list(
        Member.objects.filter(birthday_q, gym=gym, is_deleted=False)
    ) if birthday_q else []

    context = {
        'total_members': total_members,
        'active_members': active_members,
        'inactive_members': inactive_members,
        'new_members_last_30_days': new_members_last_30_days,
        'upcoming_expiries': upcoming_expiries,
        'expired_members': expired_members,
        'month_labels': month_labels,
        'new_member_counts': new_member_counts,
        'expired_member_counts': expired_member_counts,
        'today_attendance_count': today_attendance_count,
        'todays_attendance': combined_attendance,
        'present_members_count': present_members_count,
        'present_trainers_count': present_trainers_count,
        'absent_members_count': absent_members_count,
        'absent_trainers_count': absent_trainers_count,
        'recent_enquiries': recent_enquiries,
        'total_enquiries': total_enquiries,
        'recent_dues': recent_dues,
        'total_dues': total_dues,
        'recent_payments': recent_payments,
        'total_recent_payments': total_recent_payments,
        'today_birthdays': today_birthdays,
        'upcoming_birthdays': upcoming_birthdays_list,
        'gym_quota': get_gym_quota_status(gym),
        'available_upgrade_plans': SubscriptionPlan.objects.filter(is_active=True).order_by('price'),
    }
    return render(request, "dashboard.html", context)


@login_required(login_url='login')
@custom_permission_required('view_member')
def member_growth_chart_data(request):
    gym = getattr(request, 'gym', None)
    six_months_ago = timezone.now() - timedelta(days=180)

    # New members per month (single DB query)
    new_members_data = list(Member.objects.filter(
        gym=gym, is_deleted=False,
        membership_history__membership_start_date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('membership_history__membership_start_date')
    ).values('month').annotate(
        count=Count('id', distinct=True)
    ).order_by('month'))

    # Active members per month — fetch all members once, then compute in Python
    all_members = Member.objects.filter(gym=gym, is_deleted=False).prefetch_related(
        Prefetch('membership_history',
                 queryset=MembershipHistory.objects.select_related('plan').prefetch_related('freezes')),
    )

    active_members_data = []
    for i in range(6):
        month_start = (timezone.now() - timedelta(days=i * 30)).replace(day=1).date()
        active_count = 0
        for member in all_members:
            latest_membership = member.latest_membership
            if latest_membership:
                end_date = latest_membership.get_end_date()
                if end_date and latest_membership.membership_start_date < month_start and end_date >= month_start:
                    active_count += 1
        active_members_data.append({
            'month': month_start,
            'count': active_count
        })
    active_members_data.reverse()

    labels = [item['month'].strftime("%b") for item in new_members_data]
    new_members = [item['count'] for item in new_members_data]
    active_members = [item['count'] for item in active_members_data]

    return JsonResponse({
        'labels': labels,
        'new_members': new_members,
        'active_members': active_members
    })