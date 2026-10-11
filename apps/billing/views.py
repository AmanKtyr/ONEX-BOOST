from django.shortcuts import render, get_object_or_404, redirect
from apps.members.models import Member, MembershipHistory, PersonalTrainer
from .models import Payment
from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.views.decorators.cache import never_cache
from django.db import models
from django.db.models import Q, Sum, F, Value, DecimalField, Case, When
from django.db.models.functions import Coalesce, Greatest, Concat
from django.core.paginator import Paginator
from django.contrib import messages
from decimal import Decimal
from datetime import date, datetime
from .forms import PaymentForm
from django.http import JsonResponse
from django.utils import timezone
import logging
from apps.whatsapp.services import WhatsAppService
from apps.superadmin.notifications import notify_payment_submitted

logger = logging.getLogger(__name__)





@never_cache
@login_required(login_url='login')
@custom_permission_required('view_payment')
def submit_due(request):
    gym = getattr(request, 'gym', None)

    # Subquery for membership due (exclude trashed invoices)
    membership_due_subquery = MembershipHistory.objects.filter(
        member=models.OuterRef('pk'),
        status='active',
        is_deleted=False,
        gym=gym
    ).values('member').annotate(
        total_due=Sum(F('total_amount') - F('paid_amount'))
    ).values('total_due')

    # Subquery for personal trainer due (exclude trashed invoices)
    pt_due_subquery = PersonalTrainer.objects.filter(
        member=models.OuterRef('pk'),
        status='active',
        is_deleted=False,
        gym=gym
    ).values('member').annotate(
        total_due=Sum(F('total_amount') - F('paid_amount'))
    ).values('total_due')

    latest_membership_follow_up = MembershipHistory.objects.filter(
        member=models.OuterRef('pk'),
        follow_up_date__isnull=False,
        is_deleted=False,
        gym=gym
    ).order_by('-follow_up_date', '-id').values('follow_up_date')[:1]

    latest_pt_follow_up = PersonalTrainer.objects.filter(
        member=models.OuterRef('pk'),
        follow_up_date__isnull=False,
        is_deleted=False,
        gym=gym
    ).order_by('-follow_up_date', '-id').values('follow_up_date')[:1]

    members_with_due = Member.objects.filter(gym=gym, is_deleted=False).annotate(
        membership_due=Coalesce(models.Subquery(membership_due_subquery, output_field=DecimalField()), Value(0, output_field=DecimalField())),
        pt_due=Coalesce(models.Subquery(pt_due_subquery, output_field=DecimalField()), Value(0, output_field=DecimalField())),
        latest_membership_follow_up_date=models.Subquery(latest_membership_follow_up),
        latest_pt_follow_up_date=models.Subquery(latest_pt_follow_up)
    ).annotate(
        latest_follow_up_date=Case(
            When(latest_membership_follow_up_date__isnull=False, latest_pt_follow_up_date__isnull=False,
                 then=Greatest('latest_membership_follow_up_date', 'latest_pt_follow_up_date')),
            When(latest_membership_follow_up_date__isnull=False, then=F('latest_membership_follow_up_date')),
            When(latest_pt_follow_up_date__isnull=False, then=F('latest_pt_follow_up_date')),
            default=None,
            output_field=models.DateField()
        )
    ).filter(Q(membership_due__gt=0) | Q(pt_due__gt=0)).distinct()

    query = request.GET.get('q')
    due_type = request.GET.get('due_type')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    follow_up_date_filter = request.GET.get('follow_up_date')

    if query:
        members_with_due = members_with_due.annotate(
            full_name=Concat('first_name', Value(' '), 'last_name')
        ).filter(
            Q(full_name__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(mobile_number__icontains=query) |
            Q(member_id__icontains=query)
        )

    if due_type in ['membership', 'membership_due']:
        members_with_due = members_with_due.filter(membership_due__gt=0)
    elif due_type in ['pt', 'pt_due']:
        members_with_due = members_with_due.filter(pt_due__gt=0)
    elif due_type == 'both':
        members_with_due = members_with_due.filter(membership_due__gt=0, pt_due__gt=0)

    if from_date and to_date:
        members_with_due = members_with_due.filter(latest_follow_up_date__range=[from_date, to_date])
    
    if follow_up_date_filter:
        members_with_due = members_with_due.filter(latest_follow_up_date=follow_up_date_filter)

    members_with_due = members_with_due.order_by('-id')
    paginator = Paginator(members_with_due, 10)  # Show 10 members per page
    page_number = request.GET.get('page')
    members_page = paginator.get_page(page_number)

    context = {
        'members': members_page,
        'query': query,
        'due_type': due_type,
        'from_date': from_date,
        'to_date': to_date,
        'follow_up_date': follow_up_date_filter,
    }
    return render(request, 'billing/submit_due.html', context)

@login_required
@custom_permission_required('add_payment')
def pay_due_payment(request, member_id):
    gym = getattr(request, 'gym', None)
    member = Member.objects.filter(id=member_id, gym=gym, is_deleted=False).first()
    if not member:
        messages.error(request, 'Member not found.')
        return redirect('billing:submit_due')

    membership_invoices = MembershipHistory.objects.filter(member=member, status='active', is_deleted=False, gym=gym).exclude(paid_amount=F('total_amount')).annotate(due=F('total_amount') - F('paid_amount'))
    pt_invoices = PersonalTrainer.objects.filter(member=member, status='active', is_deleted=False, gym=gym).exclude(paid_amount=F('total_amount')).annotate(due=F('total_amount') - F('paid_amount'))

    form = PaymentForm()
    if request.method == 'POST':
        invoice_type = request.POST.get('invoice_type')
        invoice_id = request.POST.get('invoice_id')
        
        invoice = None
        if invoice_type == 'membership':
            invoice = MembershipHistory.objects.filter(id=invoice_id, member=member, is_deleted=False, gym=gym).first()
        elif invoice_type == 'pt':
            invoice = PersonalTrainer.objects.filter(id=invoice_id, member=member, is_deleted=False, gym=gym).first()

        if invoice:
            due_amount = invoice.total_amount - invoice.paid_amount
            form = PaymentForm(request.POST, due_amount=due_amount)
            if form.is_valid():
                payment = form.save(commit=False)
                payment.member = member
                payment.gym = gym
                payment_date_str = request.POST.get('payment_date')
                if payment_date_str:
                    try:
                        p_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                        payment.payment_date = timezone.make_aware(datetime.combine(p_date, timezone.localtime().time()))
                    except (ValueError, TypeError):
                        payment.payment_date = timezone.now()
                else:
                    payment.payment_date = timezone.now()
                
                if invoice_type == 'membership':
                    payment.membership_history = invoice
                elif invoice_type == 'pt':
                    payment.personal_trainer = invoice
                
                if form.cleaned_data.get('follow_up_date'):
                    follow_up_date = form.cleaned_data['follow_up_date']
                    MembershipHistory.objects.filter(member=member, status='active', gym=gym).exclude(paid_amount=F('total_amount')).update(follow_up_date=follow_up_date)
                    PersonalTrainer.objects.filter(member=member, status='active', gym=gym).exclude(paid_amount=F('total_amount')).update(follow_up_date=follow_up_date)
                
                invoice.paid_amount += payment.amount
                invoice.save()
                payment.save()

                # Dispatch in-app platform notification & receipt
                try:
                    notify_payment_submitted(payment=payment, member=member, invoice=invoice, invoice_type=invoice_type)
                except Exception as notif_err:
                    logger.error(f"Failed to dispatch payment notification: {notif_err}")

                if gym and gym.whatsapp_enabled:
                    try:
                        whatsapp_service = WhatsAppService(gym_id=gym.id)
                        plan_name = invoice.plan.title if invoice_type == 'membership' else "Personal Training"
                        
                        wa_res = whatsapp_service.send_due_payment_received(
                            request=request,
                            to_number=member.mobile_number,
                            name=member.name,
                            amount_received=payment.amount,
                            payment_date=payment.payment_date.strftime('%d-%m-%Y') if hasattr(payment.payment_date, 'strftime') else str(payment.payment_date),
                            due_balance=invoice.total_amount - invoice.paid_amount,
                            gym_name=gym.name,
                            plan_name=plan_name,
                            gym_contact_number=gym.phone,
                            gym_logo_url=gym.logo.url if gym.logo else None
                        )
                        msg_text = 'Payment submitted successfully.'
                        if wa_res and wa_res.get('success'):
                            messages.success(request, msg_text, extra_tags='whatsapp_success')
                        else:
                            messages.warning(request, msg_text, extra_tags='whatsapp_warning')
                    except Exception as e:
                        logger.error(f"WhatsApp Error: {e}")
                        messages.warning(request, 'Payment submitted successfully.', extra_tags='whatsapp_warning')
                else:
                    messages.warning(request, 'Payment submitted successfully.', extra_tags='whatsapp_warning')

                if invoice_type == 'pt':
                    return redirect('billing:pt_invoice', member_id=member.id, pt_invoice_id=invoice.id)
                else:
                    return redirect('billing:submit_due')
            else:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
        else:
            messages.error(request, 'Invalid invoice selected.')

    context = {
        'member': member,
        'membership_invoices': membership_invoices,
        'pt_invoices': pt_invoices,
        'form': form,
        'today': timezone.localdate(),
    }
    return render(request, 'billing/pay_due_payment.html', context)

@login_required
@custom_permission_required('change_payment')
def update_follow_up(request, member_id):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        follow_up_date_str = request.POST.get('follow_up_date')
        if follow_up_date_str:
            try:
                follow_up_date = date.fromisoformat(follow_up_date_str)
                if follow_up_date < timezone.localdate():
                    messages.error(request, "Follow-up date cannot be in the past.")
                    return redirect('billing:submit_due')

                member = Member.objects.filter(id=member_id, gym=gym, is_deleted=False).first()
                if not member:
                    messages.error(request, 'Member not found.')
                    return redirect('billing:submit_due')
                
                # Update all outstanding non-deleted invoices for the member
                MembershipHistory.objects.filter(member=member, status='active', is_deleted=False, gym=gym).exclude(paid_amount=F('total_amount')).update(follow_up_date=follow_up_date)
                PersonalTrainer.objects.filter(member=member, status='active', is_deleted=False, gym=gym).exclude(paid_amount=F('total_amount')).update(follow_up_date=follow_up_date)

                # Calculate total due for the member
                from django.db.models import Sum, F as F_expr
                membership_due = MembershipHistory.objects.filter(
                    member=member, status='active', is_deleted=False, gym=gym
                ).exclude(paid_amount=F_expr('total_amount')).aggregate(
                    total=Sum(F_expr('total_amount') - F_expr('paid_amount'))
                )['total'] or 0

                pt_due = PersonalTrainer.objects.filter(
                    member=member, status='active', is_deleted=False, gym=gym
                ).exclude(paid_amount=F_expr('total_amount')).aggregate(
                    total=Sum(F_expr('total_amount') - F_expr('paid_amount'))
                )['total'] or 0

                total_due = membership_due + pt_due

                # Fetch membership details for the template
                latest_membership = member.latest_membership
                plan_name = latest_membership.plan.title if latest_membership and latest_membership.plan else "Gym Membership"
                total_amount = latest_membership.total_amount if latest_membership else 0
                follow_up_date_formatted = follow_up_date.strftime('%d-%m-%Y')

                # Send WhatsApp follow-up reminder
                if gym and gym.whatsapp_enabled:
                    try:
                        whatsapp_service = WhatsAppService(gym_id=gym.id)
                        wa_res = whatsapp_service.send_due_follow_up_reminder(
                            request=request,
                            to_number=member.mobile_number,
                            name=member.name,
                            plan_name=plan_name,
                            total_amount=total_amount,
                            last_payment_date=follow_up_date_formatted,
                            pending_due=total_due,
                            gym_name=gym.name,
                            gym_contact_number=gym.phone,
                            gym_logo_url=gym.logo.url if gym.logo else "/static/images/logo.jpg"
                        )
                        msg_text = f"Follow-up date for {member.first_name} {member.last_name} updated successfully."
                        if wa_res and wa_res.get('success'):
                            messages.success(request, msg_text, extra_tags='whatsapp_success')
                        else:
                            messages.warning(request, msg_text, extra_tags='whatsapp_warning')
                    except Exception as e:
                        logger.error(f"WhatsApp follow-up reminder error: {e}")
                        msg_text = f"Follow-up date for {member.first_name} {member.last_name} updated successfully."
                        messages.warning(request, msg_text, extra_tags='whatsapp_warning')
                else:
                    msg_text = f"Follow-up date for {member.first_name} {member.last_name} updated successfully."
                    messages.warning(request, msg_text, extra_tags='whatsapp_warning')

            except (ValueError, TypeError):
                messages.error(request, "Invalid date format.")
        else:
            messages.error(request, "No follow-up date provided.")
    
    return redirect('billing:submit_due')


@never_cache
@login_required(login_url='login')
@custom_permission_required('view_payment')
def invoice(request, member_id, history_id):
    gym = getattr(request, 'gym', None)
    member = Member.objects.filter(id=member_id, gym=gym, is_deleted=False).first()
    if not member:
        messages.error(request, 'Member not found.')
        return redirect('member_list')
    history = MembershipHistory.objects.filter(id=history_id, is_deleted=False, gym=gym).first()
    if not history:
        messages.error(request, 'Invoice not found.')
        return redirect('member_profile', member_id=member.id)

    # Get all non-deleted invoices for the member to find the next and previous
    member_invoices = list(MembershipHistory.objects.filter(member=member, is_deleted=False, gym=gym).order_by('created_at'))
    current_invoice_index = member_invoices.index(history)

    previous_invoice = member_invoices[current_invoice_index - 1] if current_invoice_index > 0 else None
    next_invoice = member_invoices[current_invoice_index + 1] if current_invoice_index < len(member_invoices) - 1 else None

    sgst = history.sgst
    cgst = history.cgst

    sgst_rate = 0
    cgst_rate = 0
    if gym.gst_enabled:
        gst_rate = gym.gst_rate
        sgst_rate = gst_rate / 2
        cgst_rate = gst_rate / 2

    context = {
        'member': member,
        'history': history,
        'previous_invoice': previous_invoice,
        'next_invoice': next_invoice,
        'sgst': sgst,
        'cgst': cgst,
        'sgst_rate': sgst_rate,
        'cgst_rate': cgst_rate,
    }
    return render(request, 'billing/invoice.html', context)

@never_cache
@login_required(login_url='login')
@custom_permission_required('view_payment')
def pt_invoice(request, member_id, pt_invoice_id):
    gym = getattr(request, 'gym', None)
    member = Member.objects.filter(id=member_id, gym=gym, is_deleted=False).first()
    if not member:
        messages.error(request, 'Member not found.')
        return redirect('member_list')
    pt_invoice = PersonalTrainer.objects.filter(id=pt_invoice_id, is_deleted=False, gym=gym).first()
    if not pt_invoice:
        messages.error(request, 'PT invoice not found.')
        return redirect('member_profile', member_id=member.id)

    # Get all non-deleted PT invoices for the member to find the next and previous
    member_pt_invoices = list(PersonalTrainer.objects.filter(member=member, is_deleted=False, gym=gym).order_by('created_at'))
    current_invoice_index = member_pt_invoices.index(pt_invoice)

    previous_invoice = member_pt_invoices[current_invoice_index - 1] if current_invoice_index > 0 else None
    next_invoice = member_pt_invoices[current_invoice_index + 1] if current_invoice_index < len(member_pt_invoices) - 1 else None

    context = {
        'member': member,
        'pt_invoice': pt_invoice,
        'previous_invoice': previous_invoice,
        'next_invoice': next_invoice,
        'gym': gym
    }
    return render(request, 'billing/pt_invoice.html', context)

@never_cache
@login_required(login_url='login')
@custom_permission_required('view_payment')
def invoices_list(request):
    gym = getattr(request, 'gym', None)
    # Get query parameters
    query = request.GET.get('q', '')  # Default to an empty string
    status_filter = request.GET.get('status')
    sort_by = request.GET.get('sort', '-date')

    # Fetch membership invoices
    membership_invoices = MembershipHistory.objects.select_related('member', 'plan').filter(gym=gym, is_deleted=False, member__is_deleted=False).annotate(
        date=F('payment_date'),
        type=Value('membership', output_field=models.CharField()),
        amount=F('total_amount'),
        due_amount=F('total_amount') - F('paid_amount'),
        invoice_id=F('id'),
        plan_title=F('plan__title')
    ).values('invoice_id', 'date', 'type', 'amount', 'paid_amount', 'due_amount', 'member_id', 'member__member_id', 'member__first_name', 'member__last_name', 'member__mobile_number', 'plan_title')

    # Fetch personal training invoices
    pt_invoices = PersonalTrainer.objects.select_related('member', 'trainer').filter(gym=gym, is_deleted=False, member__is_deleted=False).annotate(
        date=F('payment_date'),
        type=Value('pt', output_field=models.CharField()),
        amount=F('total_amount'),
        due_amount=F('total_amount') - F('paid_amount'),
        invoice_id=F('id'),
        plan_title=F('trainer__name')
    ).values('invoice_id', 'date', 'type', 'amount', 'member_id', 'member__member_id', 'member__first_name', 'member__last_name', 'member__mobile_number', 'plan_title', 'due_amount')

    # Combine and sort invoices
    all_invoices = sorted(
        list(membership_invoices) + list(pt_invoices),
        key=lambda x: x['date'],
        reverse='-' in sort_by
    )

    # Filter out invoices with no member_id
    all_invoices = [inv for inv in all_invoices if inv.get('member_id')]

    # Apply search filter
    if query:
        all_invoices = [inv for inv in all_invoices if
                        query.lower() in inv.get('member__first_name', '').lower() or
                        query.lower() in inv.get('member__last_name', '').lower() or
                        query.lower() in inv.get('member__member_id', '').lower() or
                        query.lower() in inv.get('member__mobile_number', '').lower() or
                        (inv.get('plan_title') and query.lower() in inv.get('plan_title', '').lower())]

    # Apply date range filter
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    if from_date and to_date:
        all_invoices = [inv for inv in all_invoices if str(inv['date']) >= from_date and str(inv['date']) <= to_date]
    elif from_date:
        all_invoices = [inv for inv in all_invoices if str(inv['date']) >= from_date]
    elif to_date:
        all_invoices = [inv for inv in all_invoices if str(inv['date']) <= to_date]

    # Apply status filter
    if status_filter:
        if status_filter == 'paid':
            all_invoices = [inv for inv in all_invoices if inv['due_amount'] == 0]
        elif status_filter == 'unpaid':
            all_invoices = [inv for inv in all_invoices if inv['due_amount'] > 0]

    # Pagination
    paginator = Paginator(all_invoices, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'billing/invoices_list.html', {
        'invoices': page_obj,
        'sort_by': sort_by,
        'status_filter': status_filter,
        'query': query,
        'from_date': from_date,
        'to_date': to_date,
    })

@login_required
@custom_permission_required('delete_payment')
def delete_invoice(request, invoice_type, invoice_id):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        try:
            if invoice_type == 'membership':
                invoice = MembershipHistory.objects.filter(id=invoice_id, gym=gym).first()
            elif invoice_type == 'pt':
                invoice = PersonalTrainer.objects.filter(id=invoice_id, gym=gym).first()
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid invoice type.'}, status=400)
            if not invoice:
                return JsonResponse({'status': 'error', 'message': 'Invoice not found.'}, status=404)

            invoice.is_deleted = True
            invoice.save()
            # Also soft-delete any associated payments so they do not count in reports/income
            invoice.payments.all().update(is_deleted=True)
            return JsonResponse({'status': 'success', 'message': 'Invoice moved to trash successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

@login_required
@custom_permission_required('view_payment')
def trash_invoices(request):
    gym = getattr(request, 'gym', None)
    # Fetch inactive membership invoices
    membership_invoices = MembershipHistory.objects.select_related('member', 'plan').filter(gym=gym, is_deleted=True).annotate(
        date=F('created_at'),
        type=Value('membership', output_field=models.CharField()),
        amount=F('total_amount'),
        due_amount=F('total_amount') - F('paid_amount'),
        invoice_id=F('id'),
        plan_title=F('plan__title')
    ).values('invoice_id', 'date', 'type', 'amount', 'member_id', 'member__member_id', 'member__first_name', 'member__last_name', 'plan_title', 'due_amount')

    # Fetch inactive personal training invoices
    pt_invoices = PersonalTrainer.objects.select_related('member', 'trainer').filter(gym=gym, is_deleted=True).annotate(
        date=F('created_at'),
        type=Value('pt', output_field=models.CharField()),
        amount=F('total_amount'),
        due_amount=F('total_amount') - F('paid_amount'),
        invoice_id=F('id'),
        plan_title=F('trainer__name')
    ).values('invoice_id', 'date', 'type', 'amount', 'member_id', 'member__member_id', 'member__first_name', 'member__last_name', 'plan_title', 'due_amount')

    all_invoices = list(membership_invoices) + list(pt_invoices)

    # Sort by date
    all_invoices.sort(key=lambda x: x['date'], reverse=True)

    # Pagination
    paginator = Paginator(all_invoices, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'billing/trash.html', {'invoices': page_obj})

@login_required
@custom_permission_required('change_payment')
def restore_invoice(request, invoice_type, invoice_id):
    gym = getattr(request, 'gym', None)
    if invoice_type == 'membership':
        invoice = MembershipHistory.objects.filter(id=invoice_id, gym=gym).first()
    elif invoice_type == 'pt':
        invoice = PersonalTrainer.objects.filter(id=invoice_id, gym=gym).first()
    else:
        messages.error(request, 'Invalid invoice type.')
        return redirect('billing:trash_invoices')
    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('billing:trash_invoices')

    invoice.is_deleted = False
    invoice.save()
    # Restore associated payments
    invoice.payments.all().update(is_deleted=False)
    messages.success(request, 'Invoice restored successfully.')
    return redirect('billing:trash_invoices')

@login_required
@custom_permission_required('delete_payment')
def delete_permanently(request, invoice_type, invoice_id):
    gym = getattr(request, 'gym', None)
    if invoice_type == 'membership':
        invoice = MembershipHistory.objects.filter(id=invoice_id, gym=gym).first()
    elif invoice_type == 'pt':
        invoice = PersonalTrainer.objects.filter(id=invoice_id, gym=gym).first()
    else:
        messages.error(request, 'Invalid invoice type.')
        return redirect('billing:trash_invoices')
    if not invoice:
        messages.error(request, 'Invoice not found.')
        return redirect('billing:trash_invoices')

    invoice.payments.all().delete()
    invoice.delete()
    messages.success(request, 'Invoice deleted permanently.')
    return redirect('billing:trash_invoices')