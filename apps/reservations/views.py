from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.email_notifications import email_new_chat_message
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from apps.accounts.email_notifications import (
    email_reservation_created,
    email_reservation_status_changed,
)
from .models import (
    Reservation, ReservationStatusLog,
    Appointment, PropertyPreferenceForm,
    ChatMessage, ChatAvailability
)
from apps.listings.models import Property
from apps.accounts.models import CustomUser
from apps.accounts.notify import (
    notify_reservation_created,
    notify_reservation_status,
    notify_appointment_created,
    notify_appointment_confirmed,
)


# ─────────────────────────────────────────
# Reservations
# ─────────────────────────────────────────

@login_required
def reservation_list(request):
    user = request.user

    if user.role == 'client':
        reservations = Reservation.objects.filter(
            client=user
        ).select_related('property')
    elif user.role == 'property_owner':
        reservations = Reservation.objects.filter(
            property__owner=user
        ).select_related('property', 'client')
    elif user.role == 'sale_assistant':
        reservations = Reservation.objects.filter(
            handled_by=user
        ).select_related('property', 'client')
    else:
        reservations = Reservation.objects.all().select_related('property', 'client')

    # Filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    if search:
        reservations = reservations.filter(
            Q(property__title__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )
    if status_filter:
        reservations = reservations.filter(status=status_filter)

    context = {
        'reservations': reservations.order_by('-created_at'),
        'search': search,
        'status_filter': status_filter,
        'status_choices': Reservation.STATUS_CHOICES,
        'total': reservations.count(),
        'pending': reservations.filter(status='pending').count(),
        'approved': reservations.filter(status='approved').count(),
        'cancelled': reservations.filter(status='cancelled').count(),
    }
    return render(request, 'reservations/list.html', context)


@login_required
def reservation_detail(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    # Permission check
    user = request.user
    if user.role == 'client' and reservation.client != user:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:list')
    if user.role == 'property_owner' and reservation.property.owner != user:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:list')

    status_logs = ReservationStatusLog.objects.filter(
        reservation=reservation
    ).order_by('-changed_at')

    return render(request, 'reservations/detail.html', {
        'reservation': reservation,
        'status_logs': status_logs,
    })


@login_required
def reservation_create(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)

    if property.listing_status != 'approved':
        messages.error(request, 'This property is not available for reservation.')
        return redirect('property_detail', pk=property_pk)

    # ✅ Check 1 — Prevent non-clients from reserving
    if request.user.role != 'client':
        messages.error(request, 'Only clients can make reservations.')
        return redirect('property_detail', pk=property_pk)

    # ✅ Check 2 — Prevent duplicate active reservation
    existing = Reservation.objects.filter(
        property=property,
        client=request.user,
        status__in=['pending', 'approved']
    ).first()

    if existing:
        messages.warning(
            request,
            f'You already have an active reservation for this property. '
            f'Status: {existing.get_status_display()}'
        )
        return redirect('my_reservations')

    if request.method == 'POST':
        reservation_date = request.POST.get('reservation_date')
        expiry_date = request.POST.get('expiry_date') or None
        reservation_fee = request.POST.get('reservation_fee', 0)
        payment_method = request.POST.get('payment_method', 'cash')
        notes = request.POST.get('notes', '')

        # ✅ Check 3 — Double-check on POST too (race condition protection)
        existing_post = Reservation.objects.filter(
            property=property,
            client=request.user,
            status__in=['pending', 'approved']
        ).first()

        if existing_post:
            messages.warning(request, 'You already have an active reservation for this property.')
            return redirect('my_reservations')

        reservation = Reservation.objects.create(
            property=property,
            client=request.user,
            status='pending',
            reservation_date=reservation_date,
            expiry_date=expiry_date,
            reservation_fee=reservation_fee,
            payment_method=payment_method,
            notes=notes,
        )

        ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=request.user,
            old_status='none',
            new_status='pending',
            remarks='Reservation created.'
        )
        email_reservation_created(reservation)
        notify_reservation_created(reservation)
        messages.success(request, 'Reservation submitted successfully!')
        return redirect('my_reservations')

    return render(request, 'reservations/create.html', {
        'property': property,
        'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
    })


@login_required
def reservation_update_status(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    user = request.user

    if user.role not in ['broker', 'staff', 'sale_assistant', 'admin'] \
            and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:list')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        remarks = request.POST.get('remarks', '')
        old_status = reservation.status

        reservation.status = new_status
        if new_status in ['approved', 'rejected', 'cancelled']:
            if not reservation.handled_by:
                reservation.handled_by = user
        reservation.save()

        ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=user,
            old_status=old_status,
            new_status=new_status,
            remarks=remarks
        )

        # Update property status if approved
        if new_status == 'approved':
            reservation.property.listing_status = 'reserved'
            reservation.property.save()

        # ✅ Notify INSIDE POST block BEFORE redirect
        notify_reservation_status(reservation, user)
        email_reservation_status_changed(reservation)
        messages.success(request, f'Reservation status updated to {new_status}.')
        return redirect('reservations:detail', pk=reservation.pk)

    # ✅ No notify here — this is the GET request (show the form)
    return render(request, 'reservations/update_status.html', {
        'reservation': reservation,
        'status_choices': Reservation.STATUS_CHOICES,
    })


@login_required
def reservation_cancel(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    # Only client can cancel their own
    if request.user.role == 'client' and reservation.client != request.user:
        messages.error(request, 'You can only cancel your own reservations.')
        return redirect('reservations:list')

    if request.method == 'POST':
        old_status = reservation.status
        reservation.status = 'cancelled'
        reservation.save()

        ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=request.user,
            old_status=old_status,
            new_status='cancelled',
            remarks=request.POST.get('reason', 'Cancelled by user.')
        )

        messages.success(request, 'Reservation cancelled successfully.')
        return redirect('my_reservations') ##reservations:list

    return render(request, 'reservations/cancel.html', {
        'reservation': reservation
    })


# ─────────────────────────────────────────
# Appointments
# ─────────────────────────────────────────

@login_required
def appointment_list(request):
    user = request.user

    if user.role == 'client':
        appointments = Appointment.objects.filter(client=user)
    elif user.role == 'property_owner':
        appointments = Appointment.objects.filter(property__owner=user)
    elif user.role == 'sale_assistant':
        appointments = Appointment.objects.filter(handled_by=user)
    else:
        appointments = Appointment.objects.all()

    appointments = appointments.select_related(
        'property', 'client', 'handled_by'
    ).order_by('-created_at')

    status_filter = request.GET.get('status', '')
    if status_filter:
        appointments = appointments.filter(status=status_filter)

    return render(request, 'reservations/appointments.html', {
        'appointments': appointments,
        'status_filter': status_filter,
        'status_choices': Appointment.STATUS_CHOICES,
        'total': appointments.count(),
        'pending': appointments.filter(status='pending').count(),
        'confirmed': appointments.filter(status='confirmed').count(),
    })


@login_required
def appointment_create(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)

    if property.listing_status != 'approved':
        messages.error(request, 'This property is not available for appointment.')
        return redirect('property_detail', pk=property_pk)

    # ✅ Only clients can book appointments
    if request.user.role != 'client':
        messages.error(request, 'Only clients can schedule appointments.')
        return redirect('property_detail', pk=property_pk)

    # ✅ Prevent duplicate active appointment
    existing = Appointment.objects.filter(
        property=property,
        client=request.user,
        status__in=['pending', 'confirmed']
    ).first()

    if existing:
        messages.warning(
            request,
            f'You already have an active appointment for this property. '
            f'Status: {existing.get_status_display()}'
        )
        return redirect('my_reservations')

    if request.method == 'POST':
        preferred_date = request.POST.get('preferred_date')
        preferred_time = request.POST.get('preferred_time')
        notes = request.POST.get('notes', '')

        # ✅ Check blocked dates
        blocked = property.blocked_dates or []
        if preferred_date in blocked:
            messages.error(
                request,
                'This date is not available. Please choose another date.'
            )
            return render(request, 'reservations/appointment_create.html', {
                'property': property,
                'blocked_dates': blocked,
            })

        # ✅ Race condition protection — check again on POST
        existing_post = Appointment.objects.filter(
            property=property,
            client=request.user,
            status__in=['pending', 'confirmed']
        ).first()

        if existing_post:
            messages.warning(
                request,
                'You already have an active appointment for this property.'
            )
            return redirect('my_reservations')

        appointment = Appointment.objects.create(
            property=property,
            client=request.user,
            preferred_date=preferred_date,
            preferred_time=preferred_time,
            notes=notes,
            status='pending',
        )

        # Save preference form if filled
        prop_type = request.POST.get('preferred_property_type')
        if prop_type:
            PropertyPreferenceForm.objects.create(
                client=request.user,
                appointment=appointment,
                preferred_property_type=prop_type,
                preferred_location=request.POST.get('preferred_location', ''),
                min_budget=request.POST.get('min_budget') or None,
                max_budget=request.POST.get('max_budget') or None,
                preferred_size=request.POST.get('preferred_size') or None,
                desired_amenities=request.POST.get('desired_amenities', ''),
                additional_notes=request.POST.get('additional_notes', ''),
            )

        notify_appointment_created(appointment)

        messages.success(
            request,
            'Appointment scheduled successfully! We will confirm shortly.'
        )

        # ✅ Redirect to client side
        return redirect('my_reservations')

    return render(request, 'reservations/appointment_create.html', {
        'property': property,
        'blocked_dates': property.blocked_dates or [],
    })


@login_required
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    user = request.user

    if user.role not in ['broker', 'staff', 'sale_assistant', 'admin'] \
            and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:appointments')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        confirmed_date = request.POST.get('confirmed_date') or None
        confirmed_time = request.POST.get('confirmed_time') or None
        notes = request.POST.get('notes', '')

        appointment.status = new_status
        appointment.confirmed_date = confirmed_date
        appointment.confirmed_time = confirmed_time
        appointment.notes = notes

        if not appointment.handled_by:
            appointment.handled_by = user
            
        if new_status == 'confirmed':
            notify_appointment_confirmed(appointment)

        appointment.save()

        messages.success(request, f'Appointment updated to {new_status}.')
        return redirect('reservations:appointments')

    return render(request, 'reservations/appointment_update.html', {
        'appointment': appointment,
        'status_choices': Appointment.STATUS_CHOICES,
    })


@login_required
def block_dates(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)

    if request.user != property.owner and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('listings:list')

    if request.method == 'POST':
        dates = request.POST.get('blocked_dates', '')
        date_list = [d.strip() for d in dates.split(',') if d.strip()]
        property.blocked_dates = date_list
        property.save()
        messages.success(request, 'Blocked dates updated.')
        return redirect('listings:detail', pk=property_pk)

    return render(request, 'reservations/block_dates.html', {
        'property': property,
        'blocked_dates': ', '.join(property.blocked_dates or [])
    })


# ─────────────────────────────────────────
# Client — My Reservations
# ─────────────────────────────────────────

@login_required
def my_reservations(request):
    reservations = Reservation.objects.filter(
        client=request.user
    ).select_related('property').order_by('-created_at')

    appointments = Appointment.objects.filter(
        client=request.user
    ).select_related('property').order_by('-created_at')

    return render(request, 'public/my_reservations.html', {
        'reservations': reservations,
        'appointments': appointments,
    })


# ─────────────────────────────────────────
# Live Chat
# ─────────────────────────────────────────

@login_required
def chat_view(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)

    if request.user.role == 'client':
        # Client chats with broker/sale_assistant
        receiver = property.broker or CustomUser.objects.filter(
            role__in=['broker', 'sale_assistant']
        ).first()
    else:
        # Broker/staff replies to a specific client
        client_id = request.GET.get('client_id')
        if not client_id:
            return redirect('reservations:chat_inbox')
        receiver = get_object_or_404(CustomUser, pk=client_id)

    if not receiver:
        messages.error(request, 'No broker available at the moment.')
        return redirect('property_detail', pk=property_pk)

    # Get messages between the two users
    chat_messages = ChatMessage.objects.filter(
        Q(sender=request.user, receiver=receiver) |
        Q(sender=receiver, receiver=request.user),
        property=property
    ).order_by('created_at')

    # Mark as read
    ChatMessage.objects.filter(
        sender=receiver,
        receiver=request.user,
        property=property,
        is_read=False
    ).update(is_read=True)

    # Availability
    availability, _ = ChatAvailability.objects.get_or_create(user=receiver)

    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()
        if message_text:
            chat_msg = ChatMessage.objects.create(
                sender=request.user,
                receiver=receiver,
                property=property,
                message=message_text,
            )
            email_new_chat_message(chat_msg)
        # ✅ Redirect based on role
        if request.user.role == 'client':
            return redirect('reservations:chat', property_pk=property_pk)
        else:
            return redirect(
                f"{request.path}?client_id={receiver.pk}"
            )

    return render(request, 'reservations/chat.html', {
        'property': property,
        'receiver': receiver,
        'chat_messages': chat_messages,
        'availability': availability,
    })


@login_required
def toggle_chat_availability(request):
    availability, _ = ChatAvailability.objects.get_or_create(
        user=request.user
    )

    if request.method == 'POST':
        availability.is_available = not availability.is_available
        availability.save()
        return JsonResponse({'is_available': availability.is_available})

    # ✅ GET returns current status
    return JsonResponse({'is_available': availability.is_available})


@login_required
def get_chat_messages(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)
    other_user_id = request.GET.get('user_id')
    other_user = get_object_or_404(CustomUser, pk=other_user_id)

    messages_qs = ChatMessage.objects.filter(
        Q(sender=request.user, receiver=other_user) |
        Q(sender=other_user, receiver=request.user),
        property=property
    ).order_by('created_at')

    data = [{
        'id': m.id,
        'message': m.message,
        'sender_id': m.sender_id,
        'is_mine': m.sender == request.user,
        'created_at': m.created_at.strftime('%H:%M'),
    } for m in messages_qs]

    return JsonResponse({'messages': data})

@login_required
def appointment_cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)

    # Only the client who made it can cancel
    if appointment.client != request.user:
        messages.error(request, 'You can only cancel your own appointments.')
        return redirect('my_reservations')

    # Can only cancel pending appointments
    if appointment.status not in ['pending', 'confirmed']:
        messages.error(request, 'This appointment can no longer be cancelled.')
        return redirect('my_reservations')

    if request.method == 'POST':
        appointment.status = 'cancelled'
        appointment.save()
        messages.success(request, 'Appointment cancelled successfully.')
        return redirect('my_reservations')
    
    return redirect('my_reservations')

@login_required
def chat_inbox(request):
    """Shows all conversations for broker/staff/sale_assistant"""
    user = request.user

    if user.role not in ['broker', 'admin', 'staff', 'sale_assistant'] \
            and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    # Get all unique conversations (latest message per client+property)
    from django.db.models import Max, OuterRef, Subquery

    # Get latest message timestamp per sender+property pair
    latest_messages = ChatMessage.objects.filter(
        Q(receiver=user) | Q(sender=user)
    ).values('property').annotate(
        latest=Max('created_at')
    ).order_by('-latest')

    # Get unique conversations
    conversations = []
    seen = set()

    all_messages = ChatMessage.objects.filter(
        Q(receiver=user) | Q(sender=user)
    ).select_related(
        'sender', 'receiver', 'property'
    ).order_by('-created_at')

    for msg in all_messages:
        # Identify the other person
        other = msg.sender if msg.receiver == user else msg.receiver
        key = (other.pk, msg.property.pk)

        if key not in seen:
            seen.add(key)
            unread_count = ChatMessage.objects.filter(
                sender=other,
                receiver=user,
                property=msg.property,
                is_read=False
            ).count()
            conversations.append({
                'other_user': other,
                'property': msg.property,
                'last_message': msg,
                'unread_count': unread_count,
            })

    return render(request, 'reservations/chat_inbox.html', {
        'conversations': conversations,
        'total_unread': sum(c['unread_count'] for c in conversations),
    })
    
@login_required
def client_chat_inbox(request):
    """Chat inbox for clients — shows all their conversations"""
    user = request.user

    if user.role != 'client':
        return redirect('reservations:chat_inbox')

    # Get all unique conversations for this client
    all_messages = ChatMessage.objects.filter(
        Q(sender=user) | Q(receiver=user)
    ).select_related(
        'sender', 'receiver', 'property'
    ).order_by('-created_at')

    conversations = []
    seen = set()

    for msg in all_messages:
        other = msg.sender if msg.receiver == user else msg.receiver
        key = (other.pk, msg.property.pk)

        if key not in seen:
            seen.add(key)
            unread_count = ChatMessage.objects.filter(
                sender=other,
                receiver=user,
                property=msg.property,
                is_read=False
            ).count()
            conversations.append({
                'other_user': other,
                'property': msg.property,
                'last_message': msg,
                'unread_count': unread_count,
            })

    total_unread = sum(c['unread_count'] for c in conversations)

    return render(request, 'reservations/client_chat_inbox.html', {
        'conversations': conversations,
        'total_unread': total_unread,
    })
    
@login_required
def client_unread_count(request):
    count = ChatMessage.objects.filter(
        receiver=request.user,
        is_read=False
    ).count()
    return JsonResponse({'count': count})
