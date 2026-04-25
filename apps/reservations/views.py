from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.accounts.email_notifications import email_new_chat_message
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from .utils import send_reservation_sms
from apps.accounts.email_notifications import (
    email_reservation_created,
    email_reservation_status_changed,
)
from .models import (
    Reservation, ReservationStatusLog,
    Appointment, PropertyPreferenceForm,
    ChatMessage, ChatAvailability, AvailabilitySlot
)
from apps.listings.models import Property
from apps.accounts.models import CustomUser, ContactMessage
from apps.accounts.notify import (
    notify_reservation_created,
    notify_reservation_status,
    notify_appointment_created,
    notify_appointment_confirmed,
    notify_appointment_status,
)


def _has_appointment_conflict(property_obj, appointment_date, appointment_time, exclude_id=None):
    """Return True when a property already has a pending/confirmed appointment on the same date and time."""
    qs = Appointment.objects.filter(
        property=property_obj,
        status__in=['pending', 'confirmed'],
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)

    return qs.filter(
        Q(preferred_date=appointment_date, preferred_time=appointment_time) |
        Q(confirmed_date=appointment_date, confirmed_time=appointment_time)
    ).exists()


def _is_time_within_availability_slot(property_obj, slot_date, slot_time):
    slots = AvailabilitySlot.objects.filter(
        property=property_obj,
        slot_date=slot_date,
        is_active=True,
    )
    if not slots.exists():
        return False
    return slots.filter(start_time__lte=slot_time, end_time__gt=slot_time).exists()


def _get_inquiries_queryset_for_user(user):
    qs = ContactMessage.objects.select_related('property').order_by('-created_at')
    if user.role in ['admin', 'broker', 'staff'] or user.is_superuser:
        return qs
    if user.role == 'sale_assistant':
        return qs.filter(
            Q(property__sale_assistant=user) |
            Q(property__broker=user)
        )
    if user.role == 'property_owner':
        return qs.filter(property__owner=user)
    return ContactMessage.objects.none()


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
        messages.error(request, 'This property is no longer available for reservation.')
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

        # ✅ Validate reservation date format and that it's not in the past
        from datetime import date
        try:
            reservation_date_obj = date.fromisoformat(reservation_date)
            if reservation_date_obj < timezone.localdate():
                messages.error(request, 'Reservation date cannot be in the past.')
                return render(request, 'reservations/create.html', {
                    'property': property,
                    'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
                })
        except (ValueError, TypeError):
            messages.error(request, 'Invalid reservation date format.')
            return render(request, 'reservations/create.html', {
                'property': property,
                'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
            })

        # Validate expiry date if provided
        if expiry_date:
            try:
                expiry_date_obj = date.fromisoformat(expiry_date)
                if expiry_date_obj <= reservation_date_obj:
                    messages.error(request, 'Expiry date must be after reservation date.')
                    return render(request, 'reservations/create.html', {
                        'property': property,
                        'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
                    })
            except (ValueError, TypeError):
                messages.error(request, 'Invalid expiry date format.')
                return render(request, 'reservations/create.html', {
                    'property': property,
                    'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
                })

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
            reservation_date=reservation_date_obj,
            expiry_date=expiry_date_obj if expiry_date else None,
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
        'today': timezone.localdate(),
    })


@login_required
def reservation_update_status(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    user = request.user

    # Allow property owners to update status for their own properties
    if user.role == 'property_owner' and reservation.property.owner != user:
        messages.error(request, 'You can only manage reservations for your own properties.')
        return redirect('reservations:list')
    elif user.role not in ['broker', 'staff', 'sale_assistant', 'admin', 'property_owner'] \
            and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:list')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        remarks = request.POST.get('remarks', '')
        old_status = reservation.status

        valid_statuses = {choice[0] for choice in Reservation.STATUS_CHOICES}
        if new_status not in valid_statuses:
            messages.error(request, 'Invalid reservation status selected.')
            return redirect('reservations:update_status', pk=reservation.pk)

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
        elif old_status == 'approved' and new_status in ['rejected', 'cancelled']:
            has_other_approved = Reservation.objects.filter(
                property=reservation.property,
                status='approved'
            ).exclude(pk=reservation.pk).exists()
            if not has_other_approved and reservation.property.listing_status == 'reserved':
                reservation.property.listing_status = 'approved'
                reservation.property.save()

        # ✅ Notify INSIDE POST block BEFORE redirect
        notify_reservation_status(reservation, user)
        email_reservation_status_changed(reservation)
        send_reservation_sms(reservation, new_status) 
        messages.success(request, f'Reservation status updated to {new_status}.')
        return redirect('reservations:detail', pk=reservation.pk)

    # ✅ No notify here — this is the GET request (show the form)
    return render(request, 'reservations/update_status.html', {
        'reservation': reservation,
        'status_choices': Reservation.STATUS_CHOICES,
    })


@login_required
def reservation_update(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    # Only client can update their own reservation
    if request.user.role == 'client' and reservation.client != request.user:
        messages.error(request, 'You can only update your own reservations.')
        return redirect('my_reservations')

    # Only allow updates for pending reservations
    if reservation.status not in ['pending']:
        messages.error(request, 'You can only update pending reservations.')
        return redirect('my_reservations')

    if request.method == 'POST':
        reservation_date = request.POST.get('reservation_date')
        expiry_date = request.POST.get('expiry_date') or None
        reservation_fee = request.POST.get('reservation_fee', 0)
        payment_method = request.POST.get('payment_method', 'cash')
        notes = request.POST.get('notes', '')

        # Basic validation
        if not reservation_date:
            messages.error(request, 'Reservation date is required.')
            return redirect('reservation_update', pk=pk)

        from datetime import date
        try:
            reservation_date_obj = date.fromisoformat(reservation_date)
            if reservation_date_obj < date.today():
                messages.error(request, 'Reservation date cannot be in the past.')
                return redirect('reservation_update', pk=pk)
        except ValueError:
            messages.error(request, 'Invalid reservation date format.')
            return redirect('reservation_update', pk=pk)

        if expiry_date:
            try:
                expiry_date_obj = date.fromisoformat(expiry_date)
                if expiry_date_obj <= reservation_date_obj:
                    messages.error(request, 'Expiry date must be after reservation date.')
                    return redirect('reservation_update', pk=pk)
            except ValueError:
                messages.error(request, 'Invalid expiry date format.')
                return redirect('reservation_update', pk=pk)

        try:
            reservation_fee = float(reservation_fee)
            if reservation_fee < 0:
                messages.error(request, 'Reservation fee cannot be negative.')
                return redirect('reservation_update', pk=pk)
        except ValueError:
            messages.error(request, 'Invalid reservation fee format.')
            return redirect('reservation_update', pk=pk)

        reservation.reservation_date = reservation_date_obj
        reservation.expiry_date = expiry_date_obj if expiry_date else None
        reservation.reservation_fee = reservation_fee
        reservation.payment_method = payment_method
        reservation.notes = notes
        reservation.save()

        messages.success(request, 'Reservation updated successfully.')
        return redirect('my_reservations')

    return render(request, 'reservations/reservation_update.html', {
        'reservation': reservation,
        'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
        'today': timezone.localdate(),
    })


@login_required
def reservation_inquiry(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)

    # Security: Only the client or staff can send inquiry
    if request.user != reservation.client and request.user.role not in ['admin', 'broker', 'staff', 'sale_assistant']:
        messages.error(request, "You do not have permission to send an inquiry for this reservation.")
        return redirect('my_reservations')

    if request.method == 'POST':
        subject = request.POST.get('subject')
        message = request.POST.get('message')

        if subject and message:
            # Send email notification to staff + confirmation to client
            from apps.accounts.email_notifications import notify_inquiry
            notify_inquiry(reservation, subject, message, request.user)

            messages.success(request, "Your inquiry has been sent successfully!")
            return redirect('my_reservations')
        else:
            messages.error(request, "Please fill in both subject and message.")

    return render(request, 'reservations/reservation_inquiry.html', {
        'reservation': reservation
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

        # Restore property availability if it was approved/reserved
        if old_status == 'approved':
            prop = reservation.property
            if prop.listing_status == 'reserved':
                prop.listing_status = 'approved'
                prop.save(update_fields=['listing_status'])

        ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=request.user,
            old_status=old_status,
            new_status='cancelled',
            remarks=request.POST.get('reason', 'Cancelled by user.')
        )

        notify_reservation_status(reservation)

        messages.success(request, 'Reservation cancelled successfully.')
        return redirect('my_reservations')

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

    today = timezone.localdate()
    available_slots = AvailabilitySlot.objects.filter(
        property=property,
        slot_date__gte=today,
        is_active=True,
    ).order_by('slot_date', 'start_time')[:20]

    if request.method == 'POST':
        preferred_date = request.POST.get('preferred_date')
        preferred_time = request.POST.get('preferred_time')
        notes = request.POST.get('notes', '')
        # ✅ Reject past dates
        from datetime import date as date_type
        try:
            parsed_date = date_type.fromisoformat(preferred_date)
        except (ValueError, TypeError):
            parsed_date = None

        if not parsed_date or parsed_date < today:
            messages.error(
                request,
                'You cannot schedule an appointment on a past date. Please select today or a future date.'
            )
            return render(request, 'reservations/appointment_create.html', {
                'property': property,
                'blocked_dates': property.blocked_dates or [],
                'available_slots': available_slots,
                'today': today.isoformat(),
            })

        from datetime import time as time_type
        try:
            parsed_time = time_type.fromisoformat(preferred_time)
        except (ValueError, TypeError):
            parsed_time = None

        if not parsed_time:
            messages.error(request, 'Please provide a valid appointment time.')
            return render(request, 'reservations/appointment_create.html', {
                'property': property,
                'blocked_dates': property.blocked_dates or [],
                'available_slots': available_slots,
                'today': today.isoformat(),
            })

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
                'available_slots': available_slots,
                'today': today.isoformat(),
            })

        if not _is_time_within_availability_slot(property, parsed_date, parsed_time):
            messages.error(request, 'No available schedules for the selected date.')
            return render(request, 'reservations/appointment_create.html', {
                'property': property,
                'blocked_dates': blocked,
                'available_slots': available_slots,
                'today': today.isoformat(),
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

        if _has_appointment_conflict(property, parsed_date, parsed_time):
            messages.error(request, 'Selected schedule is no longer available.')
            return render(request, 'reservations/appointment_create.html', {
                'property': property,
                'blocked_dates': property.blocked_dates or [],
                'available_slots': available_slots,
                'today': today.isoformat(),
            })

        appointment = Appointment.objects.create(
            property=property,
            client=request.user,
            preferred_date=parsed_date,
            preferred_time=parsed_time,
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
        'available_slots': available_slots,
        'today': today.isoformat(),
    })


@login_required
def appointment_update(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    user = request.user

    # Allow property owners to approve appointments for their own properties
    if user.role == 'property_owner' and appointment.property.owner != user:
        messages.error(request, 'You can only manage appointments for your own properties.')
        return redirect('reservations:appointments')
    elif user.role not in ['broker', 'staff', 'sale_assistant', 'admin', 'property_owner'] \
            and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:appointments')

    if request.method == 'POST':
        new_status = request.POST.get('status')
        confirmed_date = request.POST.get('confirmed_date') or None
        confirmed_time = request.POST.get('confirmed_time') or None
        notes = request.POST.get('notes', '')

        valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}
        if new_status not in valid_statuses:
            messages.error(request, 'Invalid appointment status selected.')
            return redirect('reservations:appointment_update', pk=appointment.pk)

        confirmed_date_obj = None
        confirmed_time_obj = None
        if confirmed_date:
            from datetime import date as date_type
            try:
                confirmed_date_obj = date_type.fromisoformat(confirmed_date)
            except (TypeError, ValueError):
                messages.error(request, 'Invalid confirmed date format.')
                return redirect('reservations:appointment_update', pk=appointment.pk)

        if confirmed_time:
            from datetime import time as time_type
            try:
                confirmed_time_obj = time_type.fromisoformat(confirmed_time)
            except (TypeError, ValueError):
                messages.error(request, 'Invalid confirmed time format.')
                return redirect('reservations:appointment_update', pk=appointment.pk)

        if new_status == 'confirmed':
            if not confirmed_date_obj or not confirmed_time_obj:
                messages.error(request, 'Confirmed appointments require date and time.')
                return redirect('reservations:appointment_update', pk=appointment.pk)
            if not _is_time_within_availability_slot(appointment.property, confirmed_date_obj, confirmed_time_obj):
                messages.error(request, 'No available schedules for the selected date.')
                return redirect('reservations:appointment_update', pk=appointment.pk)
            if _has_appointment_conflict(appointment.property, confirmed_date_obj, confirmed_time_obj, exclude_id=appointment.pk):
                messages.error(request, 'Selected schedule is no longer available.')
                return redirect('reservations:appointment_update', pk=appointment.pk)

        appointment.status = new_status
        appointment.confirmed_date = confirmed_date_obj
        appointment.confirmed_time = confirmed_time_obj
        appointment.notes = notes

        if not appointment.handled_by:
            appointment.handled_by = user
            
        if new_status == 'confirmed':
            notify_appointment_confirmed(appointment)
        elif new_status in ('cancelled', 'no_show'):
            notify_appointment_status(appointment, user)

        appointment.save()

        messages.success(request, f'Appointment updated to {new_status}.')
        return redirect('reservations:appointments')

    return render(request, 'reservations/appointment_update.html', {
        'appointment': appointment,
        'status_choices': Appointment.STATUS_CHOICES,
        'today': timezone.localdate(),
    })


@login_required
def block_dates(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)

    if request.user != property.owner and \
            request.user.role not in ['broker', 'admin', 'sale_assistant'] and \
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
        'blocked_dates': ', '.join(property.blocked_dates or []),
        'today': timezone.now().date().isoformat(),
    })


# ─────────────────────────────────────────
# Client — My Reservations
# ─────────────────────────────────────────

@login_required
def my_reservations(request):
    reservations = Reservation.objects.filter(
        client=request.user
    ).select_related('property').order_by('-created_at')

    return render(request, 'public/my_reservations.html', {
        'reservations': reservations,
    })


# ─────────────────────────────────────────
# Client — My Appointments
# ─────────────────────────────────────────

@login_required
def my_appointments(request):
    appointments = Appointment.objects.filter(
        client=request.user
    ).select_related('property').order_by('-created_at')

    return render(request, 'public/my_appointments.html', {
        'appointments': appointments,
    })


# ─────────────────────────────────────────
# Reservation Management Dashboard
# ─────────────────────────────────────────

@login_required
def manage_reservation(request):
    """
    Comprehensive reservation management dashboard with:
    - Schedule appointments
    - Check reservations
    - Update reservations
    - Cancel reservations
    - Approve appointments
    - Live chat integration
    """
    user = request.user

    # Permission check - allow property owners, brokers, staff, and sale assistants
    if user.role not in ['broker', 'staff', 'admin', 'sale_assistant', 'property_owner'] and not user.is_superuser:
        messages.error(request, 'You do not have permission to access reservation management.')
        return redirect('dashboard')

    # Get data based on user role
    if user.role in ['broker', 'admin', 'staff']:
        # Full access for management staff
        reservations = Reservation.objects.all()
        appointments = Appointment.objects.all()
        properties = Property.objects.filter(listing_status='approved')
        clients = CustomUser.objects.filter(role='client')
    elif user.role == 'sale_assistant':
        # Limited to assigned reservations/appointments
        reservations = Reservation.objects.filter(handled_by=user)
        appointments = Appointment.objects.filter(handled_by=user)
        # Sale assistants can schedule appointments for all approved properties
        properties = Property.objects.filter(listing_status='approved')
        clients = CustomUser.objects.filter(role='client')
    elif user.role == 'property_owner':
        # Property owners can see reservations/appointments for their properties
        reservations = Reservation.objects.filter(property__owner=user)
        appointments = Appointment.objects.filter(property__owner=user)
        properties = Property.objects.filter(owner=user, listing_status='approved')
        clients = CustomUser.objects.filter(role='client')
    else:
        # Fallback
        reservations = Reservation.objects.none()
        appointments = Appointment.objects.none()
        properties = Property.objects.none()
        clients = CustomUser.objects.none()

    # Select related objects for performance
    reservations = reservations.select_related('property', 'client', 'handled_by')
    appointments = appointments.select_related('property', 'client', 'handled_by')
    inquiries = _get_inquiries_queryset_for_user(user)
    availability_slots = AvailabilitySlot.objects.filter(
        property__in=properties
    ).select_related('property', 'created_by').order_by('slot_date', 'start_time')

    # Statistics
    stats = {
        'total_reservations': reservations.count(),
        'pending_reservations': reservations.filter(status='pending').count(),
        'approved_reservations': reservations.filter(status='approved').count(),
        'cancelled_reservations': reservations.filter(status='cancelled').count(),
        'total_appointments': appointments.count(),
        'pending_appointments': appointments.filter(status='pending').count(),
        'confirmed_appointments': appointments.filter(status='confirmed').count(),
        'cancelled_appointments': appointments.filter(status='cancelled').count(),
        'total_inquiries': inquiries.count(),
        'unread_inquiries': inquiries.filter(is_read=False).count(),
        'total_availability_slots': availability_slots.filter(is_active=True).count(),
    }

    # Recent activity (last 10 items)
    recent_reservations = reservations.order_by('-updated_at')[:5]
    recent_appointments = appointments.order_by('-updated_at')[:5]
    recent_inquiries = inquiries[:5]
    recent_slots = availability_slots[:8]

    # Chat availability
    availability, _ = ChatAvailability.objects.get_or_create(user=user)

    # Handle POST requests for quick actions
    if request.method == 'POST':
        action = request.POST.get('action')
        item_type = request.POST.get('item_type')
        item_id = request.POST.get('item_id')

        if action == 'approve_appointment' and item_type == 'appointment':
            appointment = get_object_or_404(Appointment, pk=item_id)
            if appointment.status == 'pending':
                if not _is_time_within_availability_slot(
                    appointment.property,
                    appointment.preferred_date,
                    appointment.preferred_time,
                ):
                    messages.error(request, 'No available schedules for the selected date.')
                    return redirect('reservations:manage')
                appointment.status = 'confirmed'
                appointment.handled_by = user
                appointment.confirmed_date = appointment.preferred_date
                appointment.confirmed_time = appointment.preferred_time
                appointment.save()
                notify_appointment_confirmed(appointment)
                messages.success(request, f'Appointment #{appointment.id} approved.')

        elif action == 'cancel_appointment' and item_type == 'appointment':
            appointment = get_object_or_404(Appointment, pk=item_id)
            if appointment.status in ['pending', 'confirmed']:
                appointment.status = 'cancelled'
                appointment.cancellation_reason = request.POST.get('reason', 'Cancelled by staff')
                appointment.save()
                messages.success(request, f'Appointment #{appointment.id} cancelled.')

        elif action == 'update_reservation_status' and item_type == 'reservation':
            reservation = get_object_or_404(Reservation, pk=item_id)
            new_status = request.POST.get('status')
            old_status = reservation.status
            valid_statuses = {choice[0] for choice in Reservation.STATUS_CHOICES}

            if new_status in valid_statuses and new_status != old_status:
                reservation.status = new_status
                if not reservation.handled_by:
                    reservation.handled_by = user
                reservation.save()

                # Log status change
                ReservationStatusLog.objects.create(
                    reservation=reservation,
                    changed_by=user,
                    old_status=old_status,
                    new_status=new_status,
                    remarks=request.POST.get('remarks', '')
                )

                # Update property status if approved
                if new_status == 'approved':
                    reservation.property.listing_status = 'reserved'
                    reservation.property.save()
                elif old_status == 'approved' and new_status in ['rejected', 'cancelled']:
                    has_other_approved = Reservation.objects.filter(
                        property=reservation.property,
                        status='approved'
                    ).exclude(pk=reservation.pk).exists()
                    if not has_other_approved and reservation.property.listing_status == 'reserved':
                        reservation.property.listing_status = 'approved'
                        reservation.property.save()

                # Notifications
                notify_reservation_status(reservation, user)
                email_reservation_status_changed(reservation)
                send_reservation_sms(reservation, new_status)

                messages.success(request, f'Reservation #{reservation.id} status updated to {new_status}.')
            elif new_status not in valid_statuses:
                messages.error(request, 'Invalid reservation status selected.')

        elif action == 'cancel_reservation' and item_type == 'reservation':
            reservation = get_object_or_404(Reservation, pk=item_id)
            if reservation.status in ['pending', 'approved']:
                old_status = reservation.status
                reservation.status = 'cancelled'
                reservation.save()

                ReservationStatusLog.objects.create(
                    reservation=reservation,
                    changed_by=user,
                    old_status=old_status,
                    new_status='cancelled',
                    remarks=request.POST.get('reason', 'Cancelled by staff')
                )

                messages.success(request, f'Reservation #{reservation.id} cancelled.')

        elif action == 'toggle_chat_availability':
            availability.is_available = not availability.is_available
            availability.save()
            messages.success(request, f'Chat availability {"enabled" if availability.is_available else "disabled"}.')

        elif action == 'mark_inquiry_read':
            inquiry = _get_inquiries_queryset_for_user(user).filter(pk=item_id).first()
            if not inquiry:
                messages.error(request, 'Inquiry not found or not accessible.')
            elif not inquiry.is_read:
                inquiry.is_read = True
                inquiry.replied_by = user
                inquiry.save(update_fields=['is_read', 'replied_by'])
                messages.success(request, 'Inquiry marked as read.')

        elif action == 'create_availability_slot':
            property_id = request.POST.get('property_id')
            slot_date = request.POST.get('slot_date')
            start_time = request.POST.get('start_time')
            end_time = request.POST.get('end_time')
            slot_notes = request.POST.get('slot_notes', '').strip()

            if not property_id or not slot_date or not start_time or not end_time:
                messages.error(request, 'Please complete the required fields.')
                return redirect('reservations:manage')

            property_obj = get_object_or_404(properties, pk=property_id)
            from datetime import date as date_type, time as time_type

            try:
                slot_date_obj = date_type.fromisoformat(slot_date)
            except (TypeError, ValueError):
                slot_date_obj = None

            try:
                start_time_obj = time_type.fromisoformat(start_time)
                end_time_obj = time_type.fromisoformat(end_time)
            except (TypeError, ValueError):
                start_time_obj = None
                end_time_obj = None

            if not slot_date_obj or slot_date_obj < timezone.localdate():
                messages.error(request, 'Availability date must be today or a future date.')
                return redirect('reservations:manage')

            if not start_time_obj or not end_time_obj or start_time_obj >= end_time_obj:
                messages.error(request, 'Please provide a valid start and end time range.')
                return redirect('reservations:manage')

            if slot_date in (property_obj.blocked_dates or []):
                messages.error(request, 'No available schedules for the selected date.')
                return redirect('reservations:manage')

            has_overlap = AvailabilitySlot.objects.filter(
                property=property_obj,
                slot_date=slot_date_obj,
                is_active=True,
                start_time__lt=end_time_obj,
                end_time__gt=start_time_obj,
            ).exists()

            if has_overlap:
                messages.error(request, 'Selected schedule is no longer available.')
                return redirect('reservations:manage')

            AvailabilitySlot.objects.create(
                property=property_obj,
                created_by=user,
                slot_date=slot_date_obj,
                start_time=start_time_obj,
                end_time=end_time_obj,
                notes=slot_notes,
                is_active=True,
            )
            messages.success(request, 'Availability slot saved successfully.')

        elif action == 'toggle_availability_slot':
            slot = AvailabilitySlot.objects.filter(property__in=properties, pk=item_id).first()
            if not slot:
                messages.error(request, 'Availability slot not found.')
            else:
                slot.is_active = not slot.is_active
                slot.save(update_fields=['is_active', 'updated_at'])
                messages.success(request, 'Availability slot updated.')

        elif action == 'schedule_appointment':
            property_id = request.POST.get('property_id')
            client_id = request.POST.get('client_id')
            preferred_date = request.POST.get('preferred_date')
            preferred_time = request.POST.get('preferred_time')
            notes = request.POST.get('notes', '')

            if not property_id or not client_id or not preferred_date or not preferred_time:
                messages.error(request, 'Please complete the required fields.')
                return redirect('reservations:manage')

            property_obj = get_object_or_404(Property, pk=property_id)
            client_obj = get_object_or_404(CustomUser, pk=client_id, role='client')

            # Check for existing appointment
            existing = Appointment.objects.filter(
                property=property_obj,
                client=client_obj,
                status__in=['pending', 'confirmed']
            ).first()

            if existing:
                messages.warning(request, f'Client already has an active appointment for this property.')
            else:
                # Check blocked dates
                blocked = property_obj.blocked_dates or []
                if preferred_date in blocked:
                    messages.error(request, 'No available schedules for the selected date.')
                else:
                    # Validate preferred_date when scheduled from dashboard
                    from datetime import date as date_type
                    from datetime import time as time_type
                    try:
                        pd = date_type.fromisoformat(preferred_date)
                    except (ValueError, TypeError):
                        pd = None

                    try:
                        pt = time_type.fromisoformat(preferred_time)
                    except (ValueError, TypeError):
                        pt = None

                    if not pd or pd < timezone.now().date():
                        messages.error(request, 'Preferred date must be today or a future date.')
                    elif not pt:
                        messages.error(request, 'Please complete the required fields.')
                    elif not _is_time_within_availability_slot(property_obj, pd, pt):
                        messages.error(request, 'No available schedules for the selected date.')
                    elif _has_appointment_conflict(property_obj, pd, pt):
                        messages.error(request, 'Selected schedule is no longer available.')
                    else:
                        appointment = Appointment.objects.create(
                            property=property_obj,
                            client=client_obj,
                            preferred_date=pd,
                            preferred_time=pt,
                            notes=notes,
                            status='pending',
                            handled_by=user
                        )

                        # Save preference form if provided
                        prop_type = request.POST.get('preferred_property_type')
                        if prop_type:
                            PropertyPreferenceForm.objects.create(
                                client=client_obj,
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
                        messages.success(request, f'Appointment scheduled for {client_obj.get_full_name()} on {preferred_date}.')

        elif action == 'create_reservation':
            property_id = request.POST.get('property_id')
            client_id = request.POST.get('client_id')
            reservation_date = request.POST.get('reservation_date')
            expiry_date = request.POST.get('expiry_date') or None
            reservation_fee = request.POST.get('reservation_fee', 0)
            payment_method = request.POST.get('payment_method', 'cash')
            notes = request.POST.get('notes', '')

            if not property_id or not client_id or not reservation_date:
                messages.error(request, 'Please fill out the required fields.')
                return redirect('reservations:manage')

            property_obj = get_object_or_404(Property, pk=property_id)
            client_obj = get_object_or_404(CustomUser, pk=client_id, role='client')

            if property_obj.listing_status != 'approved':
                messages.error(request, 'This property is no longer available for reservation.')
                return redirect('reservations:manage')

            # Check for existing active reservation
            existing = Reservation.objects.filter(
                property=property_obj,
                client=client_obj,
                status__in=['pending', 'approved']
            ).first()

            if existing:
                messages.warning(request, f'Client already has an active reservation for this property.')
            else:
                # Validate reservation date for staff-created reservations
                from datetime import date
                try:
                    rd = date.fromisoformat(reservation_date)
                except (ValueError, TypeError):
                    rd = None

                if not rd or rd < date.today():
                    messages.error(request, 'Reservation date must be today or a future date.')
                else:
                    # Validate expiry_date if provided
                    ed_obj = None
                    if expiry_date:
                        try:
                            ed_obj = date.fromisoformat(expiry_date)
                            if ed_obj <= rd:
                                messages.error(request, 'Expiry date must be after reservation date.')
                                ed_obj = None
                        except (ValueError, TypeError):
                            messages.error(request, 'Invalid expiry date format.')
                            ed_obj = None

                    if ed_obj is None and expiry_date:
                        # error already added; skip creation
                        pass
                    else:
                        reservation = Reservation.objects.create(
                            property=property_obj,
                            client=client_obj,
                            status='pending',
                            reservation_date=rd,
                            expiry_date=ed_obj,
                            reservation_fee=reservation_fee,
                            payment_method=payment_method,
                            notes=notes,
                            handled_by=user
                        )

                        ReservationStatusLog.objects.create(
                            reservation=reservation,
                            changed_by=user,
                            old_status='none',
                            new_status='pending',
                            remarks='Reservation created by staff.'
                        )

                        email_reservation_created(reservation)
                        notify_reservation_created(reservation)
                        messages.success(request, f'Reservation created for {client_obj.get_full_name()}.')

        return redirect('reservations:manage')

    context = {
        'stats': stats,
        'recent_reservations': recent_reservations,
        'recent_appointments': recent_appointments,
        'recent_inquiries': recent_inquiries,
        'recent_slots': recent_slots,
        'properties': properties,
        'clients': clients,
        'availability': availability,
        'reservation_status_choices': Reservation.STATUS_CHOICES,
        'appointment_status_choices': Appointment.STATUS_CHOICES,
    }

    return render(request, 'reservations/manage.html', context)

@login_required
def chat_view(request, property_pk):
    property = get_object_or_404(Property, pk=property_pk)
    user = request.user

    # Check permissions
    if user.role == 'client':
        # Clients can only chat about properties they're interested in
        pass  # Allow
    elif user.role == 'property_owner':
        # Property owners can only chat about their own properties
        if property.owner != user:
            messages.error(request, 'You can only chat about your own properties.')
            return redirect('reservations:chat_inbox')
    elif user.role not in ['broker', 'staff', 'sale_assistant', 'property_owner']:
        messages.error(request, 'You do not have permission to access this chat.')
        return redirect('dashboard')

    if user.role == 'client':
        # Check if recipient is already selected via recipient_id
        recipient_id = request.GET.get('recipient_id')
        if recipient_id:
            receiver = get_object_or_404(
                CustomUser,
                pk=recipient_id,
                role__in=['broker', 'staff', 'sale_assistant'],
            )
        else:
            # Build list of available recipients: assigned broker/SA + all staff
            available_recipients = []
            seen_ids = set()

            # Property's assigned broker
            if property.broker and property.broker.pk not in seen_ids:
                broker_avail = getattr(property.broker, 'chat_availability', None)
                available_recipients.append({
                    'type': 'broker',
                    'user': property.broker,
                    'available': broker_avail.is_available if broker_avail else False,
                })
                seen_ids.add(property.broker.pk)

            # Property's assigned sale assistant
            if getattr(property, 'sale_assistant', None) and property.sale_assistant.pk not in seen_ids:
                sa_avail = getattr(property.sale_assistant, 'chat_availability', None)
                available_recipients.append({
                    'type': 'sale_assistant',
                    'user': property.sale_assistant,
                    'available': sa_avail.is_available if sa_avail else False,
                })
                seen_ids.add(property.sale_assistant.pk)

            # All active staff
            for staff_user in CustomUser.objects.filter(
                role='staff', is_active=True, is_disabled=False
            ).exclude(pk__in=seen_ids).order_by('first_name', 'last_name'):
                staff_avail = getattr(staff_user, 'chat_availability', None)
                available_recipients.append({
                    'type': 'staff',
                    'user': staff_user,
                    'available': staff_avail.is_available if staff_avail else False,
                })
                seen_ids.add(staff_user.pk)

            # Fall back: if no one added, include all active brokers
            if not available_recipients:
                for broker_user in CustomUser.objects.filter(
                    role='broker', is_active=True, is_disabled=False
                ).order_by('first_name', 'last_name'):
                    broker_avail = getattr(broker_user, 'chat_availability', None)
                    available_recipients.append({
                        'type': 'broker',
                        'user': broker_user,
                        'available': broker_avail.is_available if broker_avail else False,
                    })

            return render(request, 'reservations/chat_select.html', {
                'property': property,
                'available_recipients': available_recipients,
            })
    elif user.role == 'property_owner':
        # Property owner chats with a specific client
        client_id = request.GET.get('client_id')
        if not client_id:
            return redirect('reservations:chat_inbox')
        receiver = get_object_or_404(CustomUser, pk=client_id)
        # Verify the client has some interaction with this property
        if not (Reservation.objects.filter(client=receiver, property=property).exists() or
                Appointment.objects.filter(client=receiver, property=property).exists()):
            messages.error(request, 'This client has no active interaction with this property.')
            return redirect('reservations:chat_inbox')
    else:
        # Broker/staff replies to a specific client
        client_id = request.GET.get('client_id')
        if not client_id:
            return redirect('reservations:chat_inbox')
        receiver = get_object_or_404(CustomUser, pk=client_id)

    if not receiver:
        messages.error(request, 'No recipient available at the moment.')
        return redirect('property_detail', pk=property_pk)

    # Get messages between the two users
    chat_messages = ChatMessage.objects.filter(
        Q(sender=user, receiver=receiver) |
        Q(sender=receiver, receiver=user),
        property=property
    ).order_by('created_at')

    # Mark as read
    ChatMessage.objects.filter(
        sender=receiver,
        receiver=user,
        property=property,
        is_read=False
    ).update(is_read=True)

    # Availability
    availability, _ = ChatAvailability.objects.get_or_create(user=receiver)

    if request.method == 'POST':
        message_text = request.POST.get('message', '').strip()
        if message_text:
            chat_msg = ChatMessage.objects.create(
                sender=user,
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
        notify_appointment_status(appointment, request.user)
        messages.success(request, 'Appointment cancelled successfully.')
        return redirect('my_reservations')

    return redirect('my_reservations')

@login_required
def chat_inbox(request):
    """Shows all conversations for broker/staff/sale_assistant/property_owner"""
    user = request.user

    if user.role not in ['broker', 'staff', 'sale_assistant', 'property_owner']:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    # Get all unique conversations (latest message per client+property)
    from django.db.models import Max, OuterRef, Subquery

    # Build query based on user role
    if user.role == 'property_owner':
        # Property owners only see conversations about their properties
        message_filter = Q(property__owner=user)
    else:
        # Staff/brokers see all conversations they're involved in
        message_filter = Q(receiver=user) | Q(sender=user)

    # Get latest message timestamp per sender+property pair
    latest_messages = ChatMessage.objects.filter(message_filter).values('property').annotate(
        latest=Max('created_at')
    ).order_by('-latest')

    # Get unique conversations
    conversations = []
    seen = set()

    all_messages = ChatMessage.objects.filter(message_filter).select_related(
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

    # Get all unique conversations for this client (exclude property owners)
    all_messages = ChatMessage.objects.filter(
        Q(sender=user) | Q(receiver=user)
    ).exclude(
        # Exclude conversations with property owners
        Q(sender__role='property_owner') | Q(receiver__role='property_owner')
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


# ─────────────────────────────────────────
# Chat Widget API (Messenger-style)
# ─────────────────────────────────────────

@login_required
def widget_conversations(request):
    """Return conversations as JSON for the floating chat widget."""
    from django.utils.timesince import timesince
    user = request.user
    all_messages = ChatMessage.objects.filter(
        Q(sender=user) | Q(receiver=user)
    ).exclude(
        # Exclude conversations with property owners
        Q(sender__role='property_owner') | Q(receiver__role='property_owner')
    ).select_related('sender', 'receiver', 'property').order_by('-created_at')

    conversations = []
    seen = set()
    for msg in all_messages:
        other = msg.sender if msg.receiver == user else msg.receiver
        prop = msg.property
        if not prop:
            continue
        key = (other.pk, prop.pk)
        if key in seen:
            continue
        seen.add(key)
        unread_count = ChatMessage.objects.filter(
            sender=other, receiver=user, property=prop, is_read=False
        ).count()
        avatar_url = None
        if other.profile_picture:
            avatar_url = other.profile_picture.url
        conversations.append({
            'other_user_pk': other.pk,
            'other_user_name': other.get_full_name() or other.username,
            'initials': other.get_initials() if hasattr(other, 'get_initials') else other.username[:2].upper(),
            'avatar_url': avatar_url,
            'property_pk': prop.pk,
            'property_title': prop.title,
            'last_message': msg.message[:80],
            'is_mine': msg.sender == user,
            'time_ago': timesince(msg.created_at) + ' ago',
            'unread_count': unread_count,
        })
    return JsonResponse({'conversations': conversations})


@login_required
def widget_send_message(request, property_pk):
    """Send a message from the chat widget."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    prop = get_object_or_404(Property, pk=property_pk)
    receiver_pk = request.POST.get('receiver_pk')
    message_text = request.POST.get('message', '').strip()
    if not receiver_pk or not message_text:
        return JsonResponse({'error': 'Missing data'}, status=400)
    receiver = get_object_or_404(CustomUser, pk=receiver_pk)
    chat_msg = ChatMessage.objects.create(
        sender=request.user,
        receiver=receiver,
        property=prop,
        message=message_text,
    )
    email_new_chat_message(chat_msg)
    return JsonResponse({'ok': True})


@login_required
def widget_mark_read(request, property_pk, sender_pk):
    """Mark messages as read for the chat widget."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    ChatMessage.objects.filter(
        sender_id=sender_pk,
        receiver=request.user,
        property_id=property_pk,
        is_read=False,
    ).update(is_read=True)
    return JsonResponse({'ok': True})


@login_required
def staff_reservation_create(request):
    """
    Allows broker/staff/admin/sale_assistant to create a reservation
    on behalf of a client directly from the management dashboard.
    """
    if request.user.role not in ['broker', 'staff', 'admin', 'sale_assistant'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:list')

    from apps.accounts.models import CustomUser

    if request.method == 'POST':
        property_pk = request.POST.get('property_id')
        client_pk = request.POST.get('client_id')
        reservation_date = request.POST.get('reservation_date')
        expiry_date = request.POST.get('expiry_date') or None
        reservation_fee = request.POST.get('reservation_fee', 0) or 0
        payment_method = request.POST.get('payment_method', 'cash')
        notes = request.POST.get('notes', '')

        if not property_pk or not client_pk or not reservation_date:
            messages.error(request, 'Property, client, and reservation date are required.')
            return redirect('reservations:staff_create')

        property_obj = get_object_or_404(Property, pk=property_pk)
        client = get_object_or_404(CustomUser, pk=client_pk, role='client')

        if property_obj.listing_status != 'approved':
            messages.error(request, 'This property is no longer available for reservation.')
            return redirect('reservations:staff_create')

        existing = Reservation.objects.filter(
            property=property_obj,
            client=client,
            status__in=['pending', 'approved']
        ).first()

        if existing:
            messages.warning(
                request,
                f'{client.get_full_name()} already has an active reservation '
                f'for this property (#{existing.id}).'
            )
            return redirect('reservations:staff_create')

        # Validate reservation date for staff-created reservations
        from datetime import date
        try:
            rd = date.fromisoformat(reservation_date)
        except (ValueError, TypeError):
            rd = None

        if not rd or rd < timezone.localdate():
            messages.error(request, 'Reservation date must be today or a future date.')
            return redirect('reservations:staff_create')

        # Validate expiry_date if provided
        ed_obj = None
        if expiry_date:
            try:
                ed_obj = date.fromisoformat(expiry_date)
                if ed_obj <= rd:
                    messages.error(request, 'Expiry date must be after reservation date.')
                    return redirect('reservations:staff_create')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid expiry date format.')
                return redirect('reservations:staff_create')

        reservation = Reservation.objects.create(
            property=property_obj,
            client=client,
            status='pending',
            reservation_date=rd,
            expiry_date=ed_obj,
            reservation_fee=reservation_fee,
            payment_method=payment_method,
            notes=notes,
            handled_by=request.user,
        )

        ReservationStatusLog.objects.create(
            reservation=reservation,
            changed_by=request.user,
            old_status='none',
            new_status='pending',
            remarks=f'Reservation created by staff: {request.user.get_full_name()}.'
        )

        from apps.accounts.email_notifications import email_reservation_created
        from apps.accounts.notify import notify_reservation_created
        email_reservation_created(reservation)
        notify_reservation_created(reservation)

        messages.success(
            request,
            f'Reservation #{reservation.id} created for {client.get_full_name()}.'
        )
        return redirect('reservations:detail', pk=reservation.pk)

    properties = Property.objects.filter(listing_status='approved').order_by('title')
    clients = CustomUser.objects.filter(role='client', is_disabled=False).order_by('first_name', 'last_name')

    return render(request, 'reservations/staff_reservation_create.html', {
        'properties': properties,
        'clients': clients,
        'payment_choices': Reservation.PAYMENT_METHOD_CHOICES,
        'today': timezone.localdate(),
    })


@login_required
def staff_appointment_create(request):
    """
    Allows broker/staff/admin/sale_assistant to schedule an appointment
    on behalf of a client directly from the management dashboard.
    """
    if request.user.role not in ['broker', 'staff', 'admin', 'sale_assistant'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reservations:appointments')

    from apps.accounts.models import CustomUser

    if request.method == 'POST':
        property_pk = request.POST.get('property_id')
        client_pk = request.POST.get('client_id')
        preferred_date = request.POST.get('preferred_date')
        preferred_time = request.POST.get('preferred_time')
        confirmed_date = request.POST.get('confirmed_date') or None
        confirmed_time = request.POST.get('confirmed_time') or None
        status = request.POST.get('status', 'pending')
        notes = request.POST.get('notes', '')

        valid_statuses = {choice[0] for choice in Appointment.STATUS_CHOICES}
        if status not in valid_statuses:
            messages.error(request, 'Invalid appointment status selected.')
            return redirect('reservations:staff_appointment_create')

        if not property_pk or not client_pk or not preferred_date or not preferred_time:
            messages.error(request, 'Property, client, date, and time are required.')
            return redirect('reservations:staff_appointment_create')

        property_obj = get_object_or_404(Property, pk=property_pk)
        client = get_object_or_404(CustomUser, pk=client_pk, role='client')

        existing = Appointment.objects.filter(
            property=property_obj,
            client=client,
            status__in=['pending', 'confirmed']
        ).first()

        if existing:
            messages.warning(
                request,
                f'{client.get_full_name()} already has an active appointment '
                f'for this property (#{existing.id}).'
            )
            return redirect('reservations:staff_appointment_create')

        # Validate preferred_date
        from datetime import date as date_type
        try:
            pd = date_type.fromisoformat(preferred_date)
        except (ValueError, TypeError):
            pd = None

        if not pd or pd < timezone.localdate():
            messages.error(request, 'Preferred date must be today or a future date.')
            return redirect('reservations:staff_appointment_create')

        from datetime import time as time_type
        try:
            pt = time_type.fromisoformat(preferred_time)
        except (ValueError, TypeError):
            pt = None

        if not pt:
            messages.error(request, 'Invalid preferred time format.')
            return redirect('reservations:staff_appointment_create')

        blocked = property_obj.blocked_dates or []
        if preferred_date in blocked:
            messages.error(request, 'No available schedules for the selected date.')
            return redirect('reservations:staff_appointment_create')

        if _has_appointment_conflict(property_obj, pd, pt):
            messages.error(request, 'Selected schedule is no longer available.')
            return redirect('reservations:staff_appointment_create')

        if not _is_time_within_availability_slot(property_obj, pd, pt):
            messages.error(request, 'No available schedules for the selected date.')
            return redirect('reservations:staff_appointment_create')

        # Validate confirmed_date if provided
        cd_obj = None
        ct_obj = None
        if confirmed_date:
            try:
                cd_obj = date_type.fromisoformat(confirmed_date)
                if cd_obj < pd:
                    messages.error(request, 'Confirmed date cannot be earlier than the preferred date.')
                    return redirect('reservations:staff_appointment_create')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid confirmed date format.')
                return redirect('reservations:staff_appointment_create')

        if confirmed_time:
            try:
                ct_obj = time_type.fromisoformat(confirmed_time)
            except (ValueError, TypeError):
                messages.error(request, 'Invalid confirmed time format.')
                return redirect('reservations:staff_appointment_create')

        if status == 'confirmed':
            if not cd_obj or not ct_obj:
                messages.error(request, 'Confirmed appointments require date and time.')
                return redirect('reservations:staff_appointment_create')
            if not _is_time_within_availability_slot(property_obj, cd_obj, ct_obj):
                messages.error(request, 'No available schedules for the selected date.')
                return redirect('reservations:staff_appointment_create')
            if _has_appointment_conflict(property_obj, cd_obj, ct_obj):
                messages.error(request, 'Selected schedule is no longer available.')
                return redirect('reservations:staff_appointment_create')

        appointment = Appointment.objects.create(
            property=property_obj,
            client=client,
            preferred_date=pd,
            preferred_time=pt,
            confirmed_date=cd_obj,
            confirmed_time=ct_obj,
            status=status,
            notes=notes,
            handled_by=request.user,
        )

        from apps.accounts.notify import notify_appointment_created, notify_appointment_confirmed
        notify_appointment_created(appointment)
        if status == 'confirmed':
            notify_appointment_confirmed(appointment)

        messages.success(
            request,
            f'Appointment #{appointment.id} scheduled for {client.get_full_name()} '
            f'on {preferred_date} at {preferred_time}.'
        )
        return redirect('reservations:appointments')

    properties = Property.objects.filter(listing_status='approved').order_by('title')
    clients = CustomUser.objects.filter(role='client', is_disabled=False).order_by('first_name', 'last_name')

    return render(request, 'reservations/staff_appointment_create.html', {
        'properties': properties,
        'clients': clients,
        'status_choices': Appointment.STATUS_CHOICES,
        'today': timezone.localdate(),
    })