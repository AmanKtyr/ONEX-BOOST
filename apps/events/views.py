from django.shortcuts import render, redirect, get_object_or_404
from .models import Event, EventParticipant
from .forms import EventParticipantForm
from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.contrib import messages
from apps.superadmin.models import GymAdmin
 
def get_user_gym(request):
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
            except Exception:
                gym = None
    return gym


def event_registration(request, event_id):
    event = Event.objects.filter(id=event_id).first()
    if not event:
        return render(request, 'events/event_registration_form.html', {
            'error': 'This event does not exist or has been removed.',
            'event': None,
        })
    available_seats = event.max_participants - event.participants.count()

    if request.method == 'POST':
        form = EventParticipantForm(request.POST, request.FILES)
        if form.is_valid():
            participant = form.save(commit=False)
            participant.event = event
            participant.save()
            messages.success(request, 'You have successfully registered for the event!')
            return redirect('events:event_registration', event_id=event.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = EventParticipantForm()

    return render(request, 'events/event_registration_form.html', {'form': form, 'event': event, 'available_seats': available_seats})

@login_required
@custom_permission_required('view_event')
def all_event_registrations(request):
    gym = get_user_gym(request)
    if not gym:
        return redirect('login')
    registrations = EventParticipant.objects.filter(event__gym=gym)

    # Get distinct payment statuses and events for filter dropdowns
    payment_statuses = EventParticipant.objects.filter(event__gym=gym).values_list('payment_status', flat=True).distinct()
    events = Event.objects.filter(gym=gym)

    # Get filter parameters from request
    payment_status_filter = request.GET.get('payment_status')
    event_filter = request.GET.get('event')

    # Apply filters
    if payment_status_filter:
        registrations = registrations.filter(payment_status=payment_status_filter)
    if event_filter:
        registrations = registrations.filter(event__id=event_filter)

    context = {
        'registrations': registrations,
        'payment_statuses': payment_statuses,
        'events': events,
        'payment_status_filter': payment_status_filter,
        'event_filter': event_filter,
    }
    return render(request, 'events/all_event_registrations.html', context)

@login_required
@custom_permission_required('view_event')
def event_list(request):
    gym = get_user_gym(request)
    if not gym:
        return redirect('login')
    events = Event.objects.filter(gym=gym)
    
    # Get distinct statuses for filter dropdown
    statuses = Event.objects.filter(gym=gym).values_list('status', flat=True).distinct()
    
    # Get filter parameter from request
    status_filter = request.GET.get('status')
    
    # Apply filter
    if status_filter:
        events = events.filter(status=status_filter)
        
    context = {
        'events': events,
        'statuses': statuses,
        'status_filter': status_filter,
    }
    return render(request, 'events/event_list.html', context)

@login_required
@custom_permission_required('add_event')
def create_event(request):
    if request.method == 'POST':
        event_name = request.POST.get('event_name')
        event_type = request.POST.get('event_type')
        description = request.POST.get('description')
        banner_image = request.FILES.get('banner_image')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        trainer_name = request.POST.get('trainer_name')
        address = request.POST.get('address')
        max_participants = request.POST.get('max_participants')
        registration_deadline = request.POST.get('registration_deadline')
        fee_amount = request.POST.get('fee_amount')
        if fee_amount == '':
            fee_amount = None
        status = request.POST.get('status')
        payment_qr_code = request.FILES.get('payment_qr_code')
        upi_id = request.POST.get('upi_id')

        gym = get_user_gym(request)
        if not gym:
            return redirect('login')

        Event.objects.create(
            event_name=event_name,
            event_type=event_type,
            description=description,
            banner_image=banner_image,
            start_date=start_date,
            end_date=end_date,
            trainer_name=trainer_name,
            address=address,
            max_participants=max_participants,
            registration_deadline=registration_deadline,
            fee_amount=fee_amount   ,
            status=status,
            payment_qr_code=payment_qr_code,
            upi_id=upi_id,
            gym=gym
        )
        return redirect('events:event_list')

    event_types = Event.EventType.choices
    statuses = Event.EventStatus.choices

    context = {
        'event_types': event_types,
        'statuses': statuses,
    }
    return render(request, 'events/create_event.html', context)

@login_required
@custom_permission_required('change_event')
def edit_event(request, event_id):
    gym = get_user_gym(request)
    event = Event.objects.filter(id=event_id, gym=gym).first()
    if not event:
        messages.error(request, 'Event not found.')
        return redirect('events:event_list')
    if request.method == 'POST':
        event.event_name = request.POST.get('event_name')
        event.event_type = request.POST.get('event_type')
        event.description = request.POST.get('description')
        if request.FILES.get('banner_image'):
            event.banner_image = request.FILES.get('banner_image')
        event.start_date = request.POST.get('start_date')
        event.end_date = request.POST.get('end_date')
        event.trainer_name = request.POST.get('trainer_name')
        event.address = request.POST.get('address')     
        event.max_participants = request.POST.get('max_participants')
        event.registration_deadline = request.POST.get('registration_deadline')
        fee_amount = request.POST.get('fee_amount')
        if fee_amount == '':
            fee_amount = None
        event.fee_amount = fee_amount
        event.status = request.POST.get('status')
        if request.FILES.get('payment_qr_code'):
            event.payment_qr_code = request.FILES.get('payment_qr_code')
        event.upi_id = request.POST.get('upi_id')
        event.save()
        return redirect('events:event_list')

    event_types = Event.EventType.choices
    statuses = Event.EventStatus.choices

    context = {
        'event': event,
        'event_types': event_types,
        'statuses': statuses,
    }
    return render(request, 'events/edit_event.html', context)

@login_required
@custom_permission_required('delete_event')
def cancel_event(request, event_id):
    gym = get_user_gym(request)
    event = Event.objects.filter(id=event_id, gym=gym).first()
    if not event:
        messages.error(request, 'Event not found.')
        return redirect('events:event_list')
    event.delete()
    messages.success(request, f"Event '{event.event_name}' has been canceled successfully.")
    return redirect('events:event_list')

@login_required
@custom_permission_required('change_event')
def notify_members(request, event_id):
    gym = get_user_gym(request)
    event = Event.objects.filter(id=event_id, gym=gym).first()
    if not event:
        messages.error(request, 'Event not found.')
        return redirect('events:event_list')
    # Placeholder for sending notifications
    messages.success(request, f"Notifications for {event.event_name} will be sent to all registered members.")
    return redirect('events:event_list')

@login_required
@custom_permission_required('change_event')
def update_payment_status(request, registration_id):
    gym = get_user_gym(request)
    registration = EventParticipant.objects.filter(id=registration_id, event__gym=gym).first()
    if not registration:
        messages.error(request, 'Registration record not found.')
        return redirect('events:all_event_registrations')
    if request.method == 'POST':
        status = request.POST.get('status')
        if status in ['Successful', 'Failed']:
            registration.payment_status = status
            registration.save()
            messages.success(request, f"Payment status for {registration.full_name} has been updated to {status}.")
        else:
            messages.error(request, "Invalid status update.")
    return redirect('events:all_event_registrations')