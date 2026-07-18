from .models import Notification, CustomUser


def send_notification(
    recipient,
    title,
    message,
    notification_type='general',
    sender=None,
    link=None,
    priority='medium'
):
    """
    Send a notification to a single user.
    """
    Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
        priority=priority,
        link=link,
    )


def send_notification_to_role(
    role,
    title,
    message,
    notification_type='general',
    sender=None,
    link=None,
    priority='medium'
):
    """
    Send a notification to all users with a specific role.
    """
    users = CustomUser.objects.filter(
        role=role,
        is_active=True,
        is_disabled=False
    )
    for user in users:
        send_notification(
            recipient=user,
            title=title,
            message=message,
            notification_type=notification_type,
            sender=sender,
            link=link,
            priority=priority,
        )


def send_notification_to_roles(
    roles,
    title,
    message,
    notification_type='general',
    sender=None,
    link=None,
    priority='medium'
):
    """
    Send a notification to multiple roles.
    """
    users = CustomUser.objects.filter(
        role__in=roles,
        is_active=True,
        is_disabled=False
    )
    for user in users:
        send_notification(
            recipient=user,
            title=title,
            message=message,
            notification_type=notification_type,
            sender=sender,
            link=link,
            priority=priority,
        )


# ─────────────────────────────────────────
# Specific Notification Helpers
# ─────────────────────────────────────────

def notify_listing_submitted(property_obj):
    send_notification_to_roles(
        roles=['broker', 'admin'],
        title='New Listing Submitted',
        message=f'"{property_obj.title}" has been submitted for approval by {property_obj.owner.get_full_name()}.',
        notification_type='listing_submitted',
        sender=property_obj.owner,
        link=f'/manage/listings/{property_obj.pk}/',
        priority='medium',
    )


def notify_listing_approved(property_obj, approved_by):
    send_notification(
        recipient=property_obj.owner,
        title='Your Listing was Approved',
        message=f'"{property_obj.title}" has been approved and is now live.',
        notification_type='listing_approved',
        sender=approved_by,
        link=f'/properties/{property_obj.pk}/',
        priority='high',
    )


def notify_listing_rejected(property_obj, rejected_by, reason):
    send_notification(
        recipient=property_obj.owner,
        title='Your Listing was Rejected',
        message=f'"{property_obj.title}" was rejected. Reason: {reason}',
        notification_type='listing_rejected',
        sender=rejected_by,
        link=f'/manage/listings/{property_obj.pk}/',
        priority='high',
    )


def notify_listing_flagged(property_obj, flagged_by, reason):
    send_notification(
        recipient=property_obj.owner,
        title='Your Listing was Flagged',
        message=f'"{property_obj.title}" was flagged for review. Reason: {reason}',
        notification_type='listing_flagged',
        sender=flagged_by,
        link=f'/manage/listings/{property_obj.pk}/',
        priority='high',
    )


def notify_reservation_created(reservation):
    send_notification_to_roles(
        roles=['broker', 'staff', 'sale_assistant'],
        title='New Reservation Request',
        message=f'{reservation.client.get_full_name()} reserved "{reservation.property.title}".',
        notification_type='reservation_created',
        sender=reservation.client,
        link=f'/manage/reservations/{reservation.pk}/',
        priority='high',
    )
    # Also notify property owner
    send_notification(
        recipient=reservation.property.owner,
        title='Your Property has a New Reservation',
        message=f'"{reservation.property.title}" has a new reservation request.',
        notification_type='reservation_created',
        link=f'/manage/reservations/{reservation.pk}/',
        priority='medium',
    )


def notify_reservation_status(reservation, changed_by):
    send_notification(
        recipient=reservation.client,
        title=f'Reservation {reservation.get_status_display()}',
        message=f'Your reservation for "{reservation.property.title}" is now {reservation.get_status_display()}.',
        notification_type=f'reservation_{reservation.status}',
        sender=changed_by,
        link=f'/manage/reservations/{reservation.pk}/',
        priority='high',
    )


def notify_appointment_created(appointment):
    send_notification_to_roles(
        roles=['broker', 'sale_assistant'],
        title='New Appointment Request',
        message=f'{appointment.client.get_full_name()} wants to visit "{appointment.property.title}" on {appointment.preferred_date}.',
        notification_type='appointment_created',
        sender=appointment.client,
        link=f'/manage/reservations/appointments/{appointment.pk}/update/',
        priority='high',
    )


def notify_appointment_confirmed(appointment):
    send_notification(
        recipient=appointment.client,
        title='Appointment Confirmed',
        message=f'Your visit to "{appointment.property.title}" is confirmed on {appointment.confirmed_date or appointment.preferred_date}.',
        notification_type='appointment_confirmed',
        link=f'/my-appointments/',
        priority='high',
    )


def notify_sale_created(sale):
    send_notification_to_roles(
        roles=['broker', 'admin'],
        title='New Sale Created',
        message=f'Sale #{sale.id} for "{sale.property.title}" has been created.',
        notification_type='sale_created',
        link=f'/manage/sales/{sale.pk}/',
        priority='high',
    )


def notify_sale_approved(sale, approved_by):
    recipients = [sale.client]
    if sale.sale_assistant:
        recipients.append(sale.sale_assistant)
    if sale.property.owner:
        recipients.append(sale.property.owner)

    for recipient in recipients:
        send_notification(
            recipient=recipient,
            title='Sale Approved',
            message=f'Sale #{sale.id} for "{sale.property.title}" has been approved.',
            notification_type='sale_approved',
            sender=approved_by,
            link=f'/manage/sales/{sale.pk}/',
            priority='high',
        )


def notify_disbursement_approved(disbursement, approved_by):
    """Notify recipient when disbursement is approved"""
    # Safely convert amount to number
    try:
        amount = float(disbursement.amount)
    except (TypeError, ValueError):
        amount = 0.0

    send_notification(
        recipient=disbursement.recipient,
        title='Disbursement Approved',
        message=f'Your {disbursement.get_disbursement_type_display()} of ₱{amount:,.2f} has been approved and is pending payment.',
        notification_type='disbursement_approved',
        sender=approved_by,
        link=f'/manage/sales/disbursements/',
        priority='high',
    )


def notify_disbursement_completed(disbursement):
    """Notify recipient when disbursement is completed"""
    
    amount = disbursement.amount
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except:
            amount = 0.0

    send_notification(
        recipient=disbursement.recipient,
        title='Payment Completed',
        message=f'Your {disbursement.get_disbursement_type_display()} of ₱{amount:,.2f} has been completed.',
        notification_type='disbursement_completed',
        link=f'/manage/sales/disbursements/',
        priority='medium',
    )


def notify_document_uploaded(document):
    send_notification_to_roles(
        roles=['broker', 'admin'],
        title='New Document Uploaded',
        message=f'{document.uploaded_by.get_full_name()} uploaded "{document.title}" — pending your approval.',
        notification_type='document_uploaded',
        sender=document.uploaded_by,
        link=f'/manage/documents/{document.pk}/',
        priority='medium',
    )


def notify_document_approved(document, approved_by):
    send_notification(
        recipient=document.uploaded_by,
        title='Document Approved',
        message=f'Your document "{document.title}" has been approved.',
        notification_type='document_approved',
        sender=approved_by,
        link=f'/manage/documents/{document.pk}/',
        priority='medium',
    )


def notify_document_rejected(document, rejected_by, feedback):
    send_notification(
        recipient=document.uploaded_by,
        title='Document Rejected',
        message=f'Your document "{document.title}" was rejected. Feedback: {feedback}',
        notification_type='document_rejected',
        sender=rejected_by,
        link=f'/manage/documents/{document.pk}/',
        priority='high',
    )


def notify_task_assigned(task):
    send_notification(
        recipient=task.assigned_to,
        title='New Task Assigned',
        message=f'You have been assigned: "{task.title}" for Sale #{task.sale.id}.',
        notification_type='task_assigned',
        sender=task.assigned_by,
        link=f'/manage/sales/{task.sale.pk}/',
        priority=task.priority,
    )


def notify_appointment_status(appointment, changed_by):
    """Notify client when appointment is cancelled/rejected."""
    send_notification(
        recipient=appointment.client,
        title=f'Appointment {appointment.get_status_display()}',
        message=f'Your appointment for "{appointment.property.title}" has been {appointment.get_status_display().lower()}.',
        notification_type=f'appointment_{appointment.status}',
        sender=changed_by,
        link='/my-appointments/',
        priority='high',
    )


def notify_favorite_property_unavailable(property_obj, changed_by=None):
    """Notify all users who favorited a property that it is no longer available."""
    for user in property_obj.favorited_by.all():
        send_notification(
            recipient=user,
            title='Favorite Property Unavailable',
            message=f'"{property_obj.title}" is no longer available.',
            notification_type='favorite_unavailable',
            sender=changed_by,
            link=f'/properties/{property_obj.pk}/',
            priority='medium',
        )


def notify_favorite_property_updated(property_obj, changes, changed_by=None):
    """Notify all users who favorited a property that it has been updated."""
    for user in property_obj.favorited_by.all():
        send_notification(
            recipient=user,
            title='Favorite Property Updated',
            message=f'"{property_obj.title}" has been updated: {changes}',
            notification_type='favorite_updated',
            sender=changed_by,
            link=f'/properties/{property_obj.pk}/',
            priority='low',
        )