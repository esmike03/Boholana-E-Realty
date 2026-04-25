from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from apps.listings.models import Property
from apps.accounts.notify import send_notification_to_roles
from apps.accounts.models import CustomUser
from .models import PropertyPreference
from .forms import PropertyPreferenceForm


def _save_preference_from_post(request, preference):
    """Save preference fields from POST data."""
    preference.preferred_property_types = request.POST.get('preferred_property_types', '')
    preference.preferred_cities = request.POST.get('preferred_cities', '')
    preference.min_price = request.POST.get('min_price') or None
    preference.max_price = request.POST.get('max_price') or None
    preference.min_lot_area = request.POST.get('min_lot_area') or None
    preference.max_lot_area = request.POST.get('max_lot_area') or None
    preference.min_floor_area = request.POST.get('min_floor_area') or None
    preference.max_floor_area = request.POST.get('max_floor_area') or None
    preference.min_bedrooms = request.POST.get('min_bedrooms') or None
    preference.min_bathrooms = request.POST.get('min_bathrooms') or None
    preference.preferred_amenities = request.POST.get('preferred_amenities', '')
    preference.save()
    return preference


@login_required
def preference_form(request):
    """Display and save property preferences form"""
    try:
        preference = request.user.property_preference
    except PropertyPreference.DoesNotExist:
        preference = None

    if request.method == 'POST':
        if not preference:
            preference = PropertyPreference(user=request.user)

        preference = _save_preference_from_post(request, preference)

        if 'submit_to_office' in request.POST:
            # Mark as submitted to office
            preference.submitted_to_office = True
            preference.submitted_at = timezone.now()
            preference.save()

            # Notify admin, broker, and staff
            client_name = request.user.get_full_name() or request.user.username
            ptype = preference.preferred_property_types or 'Any'
            location = preference.preferred_cities or 'Any location'
            budget = ''
            if preference.min_price or preference.max_price:
                min_p = f'₱{preference.min_price:,.0f}' if preference.min_price else 'Any'
                max_p = f'₱{preference.max_price:,.0f}' if preference.max_price else 'Any'
                budget = f' | Budget: {min_p} - {max_p}'

            send_notification_to_roles(
                roles=['admin', 'broker', 'staff'],
                title=f'Property Preference Submitted: {client_name}',
                message=f'{client_name} has submitted their property preferences to the office. '
                        f'Looking for {ptype} in {location}{budget}.',
                notification_type='general',
                sender=request.user,
                link='/preferences/clients/',
                priority='medium',
            )

            messages.success(request, 'Your property preferences have been submitted to the office. Our team will review them and get back to you soon.')
            return redirect('preference_form')

        # Default: Find Properties flow
        return redirect('search_with_preferences')

    context = {
        'preference': preference,
    }
    return render(request, 'preferences/preference_form.html', context)


@login_required
def client_preferences_list(request):
    """List all client preferences for broker/staff view"""
    if request.user.role not in ['broker', 'admin', 'staff'] and not request.user.is_superuser:
        return redirect('home')

    preferences = PropertyPreference.objects.select_related('user').order_by('-updated_at')
    context = {
        'preferences': preferences,
    }
    return render(request, 'preferences/client_preferences.html', context)


@login_required
def search_with_preferences(request):
    """Search properties based on saved preferences"""
    try:
        preference = request.user.property_preference
    except PropertyPreference.DoesNotExist:
        messages.info(request, 'Please set your property preferences first.')
        return redirect('preference_form')

    # Start with approved properties
    properties = Property.objects.filter(listing_status='approved')

    # Apply preference filters
    if preference.preferred_property_types:
        property_types = [t.strip() for t in preference.preferred_property_types.split(',')]
        properties = properties.filter(property_type__in=property_types)

    if preference.preferred_cities:
        cities = [c.strip() for c in preference.preferred_cities.split(',')]
        properties = properties.filter(city__in=cities)

    if preference.preferred_provinces:
        provinces = [p.strip() for p in preference.preferred_provinces.split(',')]
        properties = properties.filter(province__in=provinces)

    if preference.min_price:
        properties = properties.filter(price__gte=preference.min_price)

    if preference.max_price:
        properties = properties.filter(price__lte=preference.max_price)

    if preference.min_bedrooms:
        properties = properties.filter(bedrooms__gte=preference.min_bedrooms)

    if preference.max_bedrooms:
        properties = properties.filter(bedrooms__lte=preference.max_bedrooms)

    if preference.min_bathrooms:
        properties = properties.filter(bathrooms__gte=preference.min_bathrooms)

    if preference.max_bathrooms:
        properties = properties.filter(bathrooms__lte=preference.max_bathrooms)

    if preference.min_garage:
        properties = properties.filter(garage__gte=preference.min_garage)

    if preference.min_lot_area:
        properties = properties.filter(lot_area__gte=preference.min_lot_area)

    if preference.max_lot_area:
        properties = properties.filter(lot_area__lte=preference.max_lot_area)

    if preference.min_floor_area:
        properties = properties.filter(floor_area__gte=preference.min_floor_area)

    if preference.max_floor_area:
        properties = properties.filter(floor_area__lte=preference.max_floor_area)

    if preference.negotiable_only:
        properties = properties.filter(is_negotiable=True)

    if preference.preferred_tags.exists():
        properties = properties.filter(tags__in=preference.preferred_tags.all()).distinct()

    context = {
        'properties': properties,
        'preference': preference,
        'count': properties.count(),
    }
    return render(request, 'preferences/search_results.html', context)
