import json
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, F, Q, Value
from django.db.models.functions import Concat
from apps.billing.models import Payment
from apps.expenses.models import Expense
from apps.members.models import MembershipHistory, PersonalTrainer
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.views.decorators.cache import never_cache
from apps.superadmin.models import GymAdmin
from django.core.paginator import Paginator
import openpyxl
from openpyxl.styles import Font, Alignment
from django.http import HttpResponse


@never_cache
@login_required
@custom_permission_required('view_payment')
def business_report(request):
    gym = getattr(request, 'gym', None)
    if not gym:
        if hasattr(request.user, 'gymadmin'):
            gym = request.user.gymadmin.gym
        elif hasattr(request.user, 'subadmin'):
            gym = request.user.subadmin.gym
        else:
            try:
                gym_admin = GymAdmin.objects.get(user=request.user)
                gym = gym_admin.gym
            except GymAdmin.DoesNotExist:
                return render(request, 'error.html', {'message': 'Gym branch not found.'})

    today = timezone.localdate()
    from_date_str = request.GET.get('from_date')
    to_date_str = request.GET.get('to_date')

    start_date = None
    end_date = None
    if from_date_str:
        try:
            start_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            start_date = None
    if to_date_str:
        try:
            end_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            end_date = None

    is_filtered = bool(start_date or end_date)

    # Base Querysets (Strictly exclude soft-deleted/trashed records)
    payments_base = Payment.objects.filter(
        member__gym=gym,
        is_deleted=False,
        member__is_deleted=False
    ).exclude(
        membership_history__is_deleted=True
    ).exclude(
        personal_trainer__is_deleted=True
    )
    expenses_base = Expense.objects.filter(gym=gym, is_deleted=False)
    
    if start_date and end_date:
        payments_base = payments_base.filter(payment_date__date__range=[start_date, end_date])
        expenses_base = expenses_base.filter(date__range=[start_date, end_date])
    elif start_date:
        payments_base = payments_base.filter(payment_date__date__gte=start_date)
        expenses_base = expenses_base.filter(date__gte=start_date)
    elif end_date:
        payments_base = payments_base.filter(payment_date__date__lte=end_date)
        expenses_base = expenses_base.filter(date__lte=end_date)

    # Export logic
    export_type = request.GET.get('export')
    query = request.GET.get('q')
    if export_type == 'transactions':
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="transactions.xlsx"'
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = 'Transactions'

        columns = ['Invoice', 'Date', 'Member', 'Amount', 'Paid', 'Due', 'Status / Mode', 'Type']
        for col_num, column_title in enumerate(columns, 1):
            cell = worksheet.cell(row=1, column=col_num)
            cell.value = column_title
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        payments_queryset = payments_base.select_related('member', 'membership_history', 'personal_trainer').order_by('-payment_date')
        
        if query:
            payments_queryset = payments_queryset.annotate(
                full_name=Concat('member__first_name', Value(' '), 'member__last_name')
            ).filter(
                Q(full_name__icontains=query) |
                Q(member__first_name__icontains=query) |
                Q(member__last_name__icontains=query) |
                Q(member__member_id__icontains=query) |
                Q(member__mobile_number__icontains=query)
            )

        for row_num, p in enumerate(payments_queryset, 2):
            trans_type = "Due"
            invoice = p.membership_history or p.personal_trainer
            
            if p.personal_trainer:
                trans_type = "PT"
            elif p.membership_history:
                first_pay = p.membership_history.payments.filter(is_deleted=False).order_by('payment_date').first()
                is_first_payment = (first_pay.id == p.id) if first_pay else False
                if is_first_payment:
                    is_first_ever = not MembershipHistory.objects.filter(member=p.member, pk__lt=p.membership_history.pk, is_deleted=False).exists()
                    trans_type = "New" if is_first_ever else "Renewal"
            
            invoice_id = f"#{invoice.id}" if invoice else "N/A"
            member_name = f"{p.member.name} (#{p.member.member_id})"
            amount = invoice.total_amount if invoice else p.amount
            due = invoice.due_amount if invoice else 0
            status = 'Paid' if (invoice and invoice.due_amount <= 0) else 'Pending'
            mode = p.payment_mode or 'N/A'
            status_mode = f"{status} / {mode}"

            row_data = [
                invoice_id,
                timezone.localtime(p.payment_date).date() if p.payment_date else None,
                member_name,
                amount,
                p.amount,
                due,
                status_mode,
                trans_type,
            ]
            for col_num, cell_value in enumerate(row_data, 1):
                worksheet.cell(row=row_num, column=col_num).value = cell_value
        
        workbook.save(response)
        return response

    if export_type == 'expenses':
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="expenses.xlsx"'
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = 'Expenses'

        columns = ['Date', 'Category', 'Amount', 'Description']
        for col_num, column_title in enumerate(columns, 1):
            cell = worksheet.cell(row=1, column=col_num)
            cell.value = column_title
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')

        expenses_queryset = expenses_base.order_by('-date')
        
        for row_num, expense in enumerate(expenses_queryset, 2):
            row_data = [
                expense.date,
                expense.get_category_display(),
                expense.amount,
                expense.description,
            ]
            for col_num, cell_value in enumerate(row_data, 1):
                worksheet.cell(row=row_num, column=col_num).value = cell_value
        
        workbook.save(response)
        return response

    total_income = payments_base.aggregate(Sum('amount'))['amount__sum'] or 0
    total_expense = expenses_base.aggregate(Sum('amount'))['amount__sum'] or 0
    gross_income = total_income - total_expense

    # Dues Calculation (Exclude trashed invoices and deleted members)
    mh_queryset = MembershipHistory.objects.filter(member__gym=gym, status='active', is_deleted=False, member__is_deleted=False)
    pt_queryset = PersonalTrainer.objects.filter(member__gym=gym, status='active', is_deleted=False, member__is_deleted=False)

    if start_date and end_date:
        mh_queryset = mh_queryset.filter(membership_start_date__range=[start_date, end_date])
        pt_queryset = pt_queryset.filter(created_at__date__range=[start_date, end_date])
    elif start_date:
        mh_queryset = mh_queryset.filter(membership_start_date__gte=start_date)
        pt_queryset = pt_queryset.filter(created_at__date__gte=start_date)
    elif end_date:
        mh_queryset = mh_queryset.filter(membership_start_date__lte=end_date)
        pt_queryset = pt_queryset.filter(created_at__date__lte=end_date)

    membership_dues = mh_queryset.aggregate(total_due=Sum(F('total_amount') - F('paid_amount')))['total_due'] or 0
    pt_dues = pt_queryset.aggregate(total_due=Sum(F('total_amount') - F('paid_amount')))['total_due'] or 0
    total_due = membership_dues + pt_dues

    payments_queryset = payments_base.select_related('member', 'membership_history', 'personal_trainer').order_by('-payment_date')
    
    if start_date and end_date:
        payments_queryset = payments_queryset.filter(payment_date__date__range=[start_date, end_date])
    elif start_date:
        payments_queryset = payments_queryset.filter(payment_date__date__gte=start_date)
    elif end_date:
        payments_queryset = payments_queryset.filter(payment_date__date__lte=end_date)

    if query:
        payments_queryset = payments_queryset.annotate(
            full_name=Concat('member__first_name', Value(' '), 'member__last_name')
        ).filter(
            Q(full_name__icontains=query) |
            Q(member__first_name__icontains=query) |
            Q(member__last_name__icontains=query) |
            Q(member__member_id__icontains=query) |
            Q(member__mobile_number__icontains=query)
        )

    paginator = Paginator(payments_queryset, 20) # Increased to 20 for "sara data" feel
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    transactions = []
    for p in page_obj:
        trans_type = "Due"
        invoice = p.membership_history or p.personal_trainer
        
        if p.personal_trainer:
            trans_type = "PT"
        elif p.membership_history:
            # Note: This query is still inside the loop, but it's only 20 queries max per page now.
            first_pay = p.membership_history.payments.filter(is_deleted=False).order_by('payment_date').first()
            is_first_payment = (first_pay.id == p.id) if first_pay else False
            if is_first_payment:
                is_first_ever = not MembershipHistory.objects.filter(member=p.member, pk__lt=p.membership_history.pk, is_deleted=False).exists()
                trans_type = "New" if is_first_ever else "Renewal"
        
        transactions.append({
            'date': timezone.localtime(p.payment_date).date() if p.payment_date else None,
            'member': p.member,
            'invoice': invoice,
            'invoice_type': 'pt' if p.personal_trainer else 'membership' if p.membership_history else '',
            'amount': invoice.total_amount if invoice else p.amount,
            'paid': p.amount,
            'due': invoice.due_amount if invoice else 0,
            'status': 'Paid' if (invoice and invoice.due_amount <= 0) else 'Pending',
            'mode': p.payment_mode,
            'type': trans_type,
        })

    latest_transactions = page_obj
    
    latest_expenses = Expense.objects.filter(gym=gym, is_deleted=False).order_by('-date')
    if start_date and end_date:
        latest_expenses = latest_expenses.filter(date__range=[start_date, end_date])
    elif start_date:
        latest_expenses = latest_expenses.filter(date__gte=start_date)
    elif end_date:
        latest_expenses = latest_expenses.filter(date__lte=end_date)
    latest_expenses = latest_expenses[:10]

    labels = []
    income_data = []
    expense_data = []

    for i in range(5, -1, -1):
        month = today - relativedelta(months=i)
        month_start = month.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)

        labels.append(month.strftime("%b %Y"))

        monthly_income = Payment.objects.filter(
            member__gym=gym,
            is_deleted=False,
            member__is_deleted=False,
            payment_date__date__range=[month_start, month_end]
        ).exclude(
            membership_history__is_deleted=True
        ).exclude(
            personal_trainer__is_deleted=True
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        income_data.append(float(monthly_income))

        monthly_expense = Expense.objects.filter(
            gym=gym,
            is_deleted=False,
            date__range=[month_start, month_end]
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        expense_data.append(float(monthly_expense))

    expense_breakdown = (
        expenses_base
        .values('category')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )

    expense_categories = [item['category'] for item in expense_breakdown]
    expense_amounts = [float(item['total'] or 0) for item in expense_breakdown]

    context = {
        'total_income': total_income,
        'total_expense': total_expense,
        'gross_income': gross_income,
        'total_due': total_due,
        'is_filtered': is_filtered,
        'query': query,
        'latest_transactions': page_obj,
        'transactions_list': transactions,
        'latest_expenses': latest_expenses,
        'line_chart_labels': json.dumps(labels),
        'line_chart_income_data': json.dumps(income_data),
        'line_chart_expense_data': json.dumps(expense_data),
        'pie_chart_labels': json.dumps(expense_categories),
        'pie_chart_data': json.dumps(expense_amounts),
    }
    return render(request, 'business_report/business_report.html', context)