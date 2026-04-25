"""
SMS Notification utilities using Twilio
Supports Philippine phone numbers (+63XXX)
"""
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("Twilio not installed. SMS notifications will be disabled.")


def send_sms(phone_number, message):
    """
    Send SMS to a Philippine phone number using Twilio
    
    Args:
        phone_number (str): Phone number in format +639XXXXXXXXX or 09XXXXXXXXX
        message (str): SMS message content
        
    Returns:
        dict: {'success': bool, 'message_id': str or None, 'error': str or None}
    """
    
    if not settings.SMS_ENABLED:
        return {'success': False, 'message_id': None, 'error': 'SMS is not enabled'}
    
    if not TWILIO_AVAILABLE:
        return {'success': False, 'message_id': None, 'error': 'Twilio library not installed'}
    
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return {'success': False, 'message_id': None, 'error': 'Twilio credentials not configured'}
    
    try:
        # Normalize Philippine phone number
        phone_number = normalize_ph_number(phone_number)
        
        if not phone_number:
            return {'success': False, 'message_id': None, 'error': 'Invalid Philippine phone number format'}
        
        # Initialize Twilio client
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        
        # Send SMS
        message_obj = client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        
        logger.info(f"SMS sent successfully to {phone_number}. Message ID: {message_obj.sid}")
        return {
            'success': True,
            'message_id': message_obj.sid,
            'error': None
        }
    
    except Exception as e:
        logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
        return {
            'success': False,
            'message_id': None,
            'error': str(e)
        }


def normalize_ph_number(phone_number):
    """
    Convert Philippine phone number to E.164 format (+639XXXXXXXXX)
    
    Args:
        phone_number (str): Phone number in various formats:
            - 09XXXXXXXXX (local)
            - +639XXXXXXXXX (international)
            - 639XXXXXXXXX (no +)
    
    Returns:
        str: Normalized number in E.164 format or None if invalid
    """
    
    if not phone_number:
        return None
    
    # Remove all non-digit characters
    digits = ''.join(filter(str.isdigit, str(phone_number)))
    
    # Philippine numbers should have 10 or 12 digits
    if len(digits) == 10:
        # Format: 09XXXXXXXXX → +639XXXXXXXXX
        if digits.startswith('9'):
            return f"+63{digits}"
        return None
    
    elif len(digits) == 11:
        # Format: 09XXXXXXXXX (with leading 0)
        if digits.startswith('0'):
            return f"+63{digits[1:]}"
        # 639XXXXXXXXX → +639XXXXXXXXX
        if digits.startswith('63'):
            return f"+{digits}"
        return None
    
    elif len(digits) == 12:
        # Format: 639XXXXXXXXX → +639XXXXXXXXX
        if digits.startswith('63'):
            return f"+{digits}"
        return None
    
    return None


def send_property_notification(user, property_obj):
    """
    Send property recommendation SMS to user
    
    Args:
        user: User object with phone_number and preferences
        property_obj: Property object
        
    Returns:
        dict: SMS send result
    """
    
    # Check if user has SMS notifications enabled
    try:
        if not user.preferences.sms_notifications:
            return {'success': False, 'error': 'User has SMS notifications disabled'}
    except:
        return {'success': False, 'error': 'User preferences not found'}
    
    # Check if user has a phone number
    if not user.phone_number:
        return {'success': False, 'error': 'User phone number not set'}
    
    # Create SMS message
    message = f"New property match! {property_obj.title} - ₱{property_obj.price:,.0f}. " \
              f"View: http://boholana-erealty.com/property/{property_obj.id}/ " \
              f"Reply STOP to unsubscribe."
    
    # Send SMS
    return send_sms(user.phone_number, message)


def send_reservation_notification(user, reservation_obj):
    """
    Send reservation status update SMS
    
    Args:
        user: User object
        reservation_obj: Reservation object
        status: Status update message
        
    Returns:
        dict: SMS send result
    """
    
    # Check if user has SMS notifications enabled
    try:
        if not user.preferences.sms_notifications:
            return {'success': False, 'error': 'User has SMS notifications disabled'}
    except:
        return {'success': False, 'error': 'User preferences not found'}
    
    if not user.phone_number:
        return {'success': False, 'error': 'User phone number not set'}
    
    property_title = reservation_obj.property.title if hasattr(reservation_obj, 'property') else 'Property'
    status = reservation_obj.get_status_display() if hasattr(reservation_obj, 'get_status_display') else 'Unknown'
    
    message = f"Reservation update: {property_title} - Status: {status}. " \
              f"Check your account for details."
    
    return send_sms(user.phone_number, message)


def send_appointment_notification(user, appointment_obj):
    """
    Send appointment confirmation SMS
    
    Args:
        user: User object
        appointment_obj: Appointment object
        
    Returns:
        dict: SMS send result
    """
    
    try:
        if not user.preferences.sms_notifications:
            return {'success': False, 'error': 'User has SMS notifications disabled'}
    except:
        return {'success': False, 'error': 'User preferences not found'}
    
    if not user.phone_number:
        return {'success': False, 'error': 'User phone number not set'}
    
    property_title = appointment_obj.property.title if hasattr(appointment_obj, 'property') else 'Property'
    appointment_date = appointment_obj.scheduled_date if hasattr(appointment_obj, 'scheduled_date') else 'Soon'
    
    message = f"Appointment confirmed for {property_title} on {appointment_date}. " \
              f"Reply CONFIRM or CANCEL to update status."
    
    return send_sms(user.phone_number, message)
