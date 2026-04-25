from django.conf import settings

def send_reservation_sms(reservation, new_status):
    client_user = reservation.client

    # Respect the client's SMS notification preference
    try:
        if not client_user.preferences.sms_notifications:
            return
    except Exception:
        return  # no preferences object — skip silently

    phone = client_user.phone_number
    if not phone:
        return  # no phone number stored — skip

    # Normalize to E.164 (handles local PH format like 09XXXXXXXXX)
    if phone.startswith('0'):
        phone = '+63' + phone[1:]
    elif not phone.startswith('+'):
        phone = '+' + phone

    status_messages = {
        'approved':  f'Good news! Your reservation #{reservation.id} for "{reservation.property.title}" has been APPROVED. Our team will be in touch shortly.',
        'rejected':  f'We regret to inform you that your reservation #{reservation.id} for "{reservation.property.title}" has been REJECTED. Please contact us for more details.',
        'cancelled': f'Your reservation #{reservation.id} for "{reservation.property.title}" has been CANCELLED. Contact us if you have questions.',
        'pending':   f'Your reservation #{reservation.id} for "{reservation.property.title}" is now PENDING review. We will update you soon.',
    }

    body = status_messages.get(new_status)
    if not body:
        return  # don't send SMS for statuses without a message

    try:
        twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        twilio_client.messages.create(
            body=body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone
        )
    except Exception as e:
        # Log but don't crash the view
        print(f'[Twilio SMS Error] Reservation #{reservation.id}: {e}')