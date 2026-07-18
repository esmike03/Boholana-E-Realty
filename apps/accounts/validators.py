"""Shared input validators for account-related forms/views."""
import re
from datetime import date


def normalize_phone(raw):
    """Strip spaces, dashes and parentheses from a phone number string."""
    if not raw:
        return ''
    return re.sub(r'[\s\-()]', '', str(raw))


def validate_phone_number(raw):
    """
    Validate a Philippine mobile number: exactly 11 digits (e.g. 09171234567).
    Returns (cleaned_value, error_message). error_message is None when valid.
    Blank is allowed (field is optional); callers requiring it should check first.
    """
    phone = normalize_phone(raw)
    if phone == '':
        return '', None
    if not phone.isdigit():
        return phone, 'Phone number must contain digits only.'
    if len(phone) != 11:
        return phone, 'Phone number must be exactly 11 digits (e.g. 09171234567).'
    return phone, None


def validate_not_future_date(value, field_label='Date'):
    """Return an error message if a date is in the future, else None."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            from datetime import datetime
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return f'{field_label} is not a valid date.'
    if value > date.today():
        return f'{field_label} cannot be in the future.'
    return None
