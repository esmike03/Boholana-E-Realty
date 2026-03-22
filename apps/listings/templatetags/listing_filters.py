from django import template

register = template.Library()


@register.filter
def split(value, delimiter=','):
    return value.split(delimiter)


@register.filter
def currency(value):
    try:
        return f"₱{float(value):,.2f}"
    except (ValueError, TypeError):
        return value


@register.filter
def percentage(value, total):
    try:
        if float(total) == 0:
            return 0
        return round((float(value) / float(total)) * 100, 1)
    except (ValueError, TypeError):
        return 0