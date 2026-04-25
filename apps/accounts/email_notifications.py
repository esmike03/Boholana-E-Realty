from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings


def send_email(subject, recipient_email, template, context):
    if not recipient_email:
        print(f"send_email skipped: no recipient for '{subject}'")
        return

    try:
        html_message = render_to_string(template, context)
        send_mail(
            subject=subject,
            message='',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            html_message=html_message,
            fail_silently=False,  # ✅ Changed to False so we see errors
        )
        print(f"Email sent to {recipient_email}: {subject}")
    except Exception as e:
        print(f"Email error sending to {recipient_email}: {e}")


# ─────────────────────────────────────────
# Inquiry Emails
# ─────────────────────────────────────────

def email_new_inquiry(inquiry):
    """Notify admin/broker about new inquiry + confirmation to sender"""
    from apps.accounts.models import CustomUser

    # ✅ Email ALL brokers and admins, not just the first one
    staff_list = CustomUser.objects.filter(
        role__in=['broker', 'admin'],
        is_active=True,
        email__isnull=False
    ).exclude(email='')

    for staff in staff_list:
        send_email(
            subject=f'New Inquiry from {inquiry.name} — Boholana E-Realty',
            recipient_email=staff.email,
            template='emails/new_inquiry.html',
            context={'inquiry': inquiry, 'staff': staff}
        )

    # ✅ Confirmation email to sender if they provided email
    if inquiry.email:
        send_email(
            subject='We received your inquiry — Boholana E-Realty',
            recipient_email=inquiry.email,
            template='emails/inquiry_confirmation.html',
            context={'inquiry': inquiry}
        )
    else:
        print(f"No email provided by {inquiry.name} — skipping confirmation email.")


def notify_inquiry(reservation, subject, message, sender):
    """Send inquiry email about a reservation"""
    from apps.accounts.models import CustomUser

    # Get staff to notify (brokers and admins)
    staff_list = CustomUser.objects.filter(
        role__in=['broker', 'admin'],
        is_active=True,
        email__isnull=False
    ).exclude(email='')

    for staff in staff_list:
        send_email(
            subject=f'Reservation Inquiry: {subject}',
            recipient_email=staff.email,
            template='emails/reservation_inquiry.html',
            context={
                'reservation': reservation,
                'subject': subject,
                'message': message,
                'sender': sender,
                'staff': staff
            }
        )

    # Confirmation to client
    send_email(
        subject='Inquiry Sent — Boholana E-Realty',
        recipient_email=sender.email,
        template='emails/inquiry_sent.html',
        context={
            'reservation': reservation,
            'subject': subject,
            'sender': sender
        }
    )


# ─────────────────────────────────────────
# Reservation Emails
# ─────────────────────────────────────────

def email_reservation_created(reservation):
    """Notify client and broker about new reservation"""
    # Email to client
    send_email(
        subject='Reservation Submitted — Boholana E-Realty',
        recipient_email=reservation.client.email,
        template='emails/reservation_created.html',
        context={'reservation': reservation}
    )

    # Email to broker/admin
    from apps.accounts.models import CustomUser
    staff = CustomUser.objects.filter(
        role__in=['broker', 'admin'],
        is_active=True
    ).first()
    if staff:
        send_email(
            subject=f'New Reservation — {reservation.property.title}',
            recipient_email=staff.email,
            template='emails/reservation_notify_staff.html',
            context={'reservation': reservation, 'staff': staff}
        )


def email_reservation_status_changed(reservation):
    """Notify client when reservation status changes"""
    status_subjects = {
        'approved': f'Your Reservation is Approved — {reservation.property.title}',
        'rejected': f'Your Reservation was Rejected — {reservation.property.title}',
        'cancelled': f'Reservation Cancelled — {reservation.property.title}',
        'completed': f'Reservation Completed — {reservation.property.title}',
    }
    subject = status_subjects.get(
        reservation.status,
        f'Reservation Update — {reservation.property.title}'
    )
    send_email(
        subject=subject,
        recipient_email=reservation.client.email,
        template='emails/reservation_status.html',
        context={'reservation': reservation}
    )


# ─────────────────────────────────────────
# Chat / Message Emails
# ─────────────────────────────────────────

def email_new_chat_message(message):
    """Notify receiver about new chat message"""
    sender = message.sender
    receiver = message.receiver

    # Don't email if receiver is online (optional check)
    subject = f'New message from {sender.get_full_name() or sender.username} — Boholana E-Realty'

    send_email(
        subject=subject,
        recipient_email=receiver.email,
        template='emails/new_message.html',
        context={
            'message': message,
            'sender': sender,
            'receiver': receiver,
        }
    )


# ─────────────────────────────────────────
# Account Emails
# ─────────────────────────────────────────

def email_account_created(user, created_by=None):
    """Welcome email for new company accounts"""
    send_email(
        subject='Your Account has been Created — Boholana E-Realty',
        recipient_email=user.email,
        template='emails/account_created.html',
        context={'user': user, 'created_by': created_by}
    )


def email_account_disabled(user):
    """Notify user their account was disabled"""
    send_email(
        subject='Your Account has been Disabled — Boholana E-Realty',
        recipient_email=user.email,
        template='emails/account_disabled.html',
        context={'user': user}
    )


def email_role_assigned(user, new_role):
    """Notify user their role was changed"""
    send_email(
        subject='Your Role has been Updated — Boholana E-Realty',
        recipient_email=user.email,
        template='emails/role_assigned.html',
        context={'user': user, 'new_role': new_role}
    )