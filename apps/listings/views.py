from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Count
from .models import Property, PropertyImage, PropertyTag, PropertyStatusLog
from apps.accounts.email_notifications import email_new_inquiry
from apps.accounts.notify import (
    notify_listing_submitted,
    notify_listing_approved,
    notify_listing_rejected,
    notify_listing_flagged,
)

# ─────────────────────────────────────────
# Public Views
# ─────────────────────────────────────────

def home_view(request):
    context = {
        'featured_properties': Property.objects.filter(
            listing_status='approved'
        ).order_by('-created_at')[:6],
        'total_properties': Property.objects.filter(listing_status='approved').count(),
        'available_properties': Property.objects.filter(listing_status='approved').count(),
        'sold_properties': Property.objects.filter(listing_status='sold').count(),
    }
    return render(request, 'public/home.html', context)


def properties_view(request):
    properties = Property.objects.filter(listing_status='approved')

    search = request.GET.get('search', '')
    property_type = request.GET.get('type', '')
    listing_type = request.GET.get('listing_type', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    city = request.GET.get('city', '')
    tag = request.GET.get('tag', '')

    if search:
        properties = properties.filter(
            Q(title__icontains=search) |
            Q(address__icontains=search) |
            Q(city__icontains=search) |
            Q(description__icontains=search)
        )
    if property_type:
        properties = properties.filter(property_type=property_type)
    if listing_type:
        properties = properties.filter(listing_type=listing_type)
    if min_price:
        properties = properties.filter(price__gte=min_price)
    if max_price:
        properties = properties.filter(price__lte=max_price)
    if city:
        properties = properties.filter(city__icontains=city)
    if tag:
        properties = properties.filter(tags__slug=tag)

    # Sorting
    sort = request.GET.get('sort', '-created_at')
    if sort == 'price_asc':
        properties = properties.order_by('price')
    elif sort == 'price_desc':
        properties = properties.order_by('-price')
    else:
        properties = properties.order_by('-created_at')

    tags = PropertyTag.objects.all()

    return render(request, 'public/properties.html', {
        'properties': properties,
        'tags': tags,
    })


def property_detail_view(request, pk):
    property = get_object_or_404(Property, pk=pk)
    related_properties = Property.objects.filter(
        listing_status='approved',
        property_type=property.property_type
    ).exclude(pk=pk)[:3]

    is_favorited = False
    if request.user.is_authenticated:
        is_favorited = property.favorited_by.filter(pk=request.user.pk).exists()

    return render(request, 'public/property_detail.html', {
        'property': property,
        'related_properties': related_properties,
        'is_favorited': is_favorited,
    })


def contact_view(request):
    if request.method == 'POST':
        messages.success(request, 'Your inquiry has been sent! We will contact you shortly.')
        contact_msg = ContactMessage.objects.create(...)

        # ✅ Send email notifications
        email_new_inquiry(contact_msg)

        messages.success(request, 'Your message has been sent!')
        return redirect('contact')
    return render(request, 'public/contact.html')


# ─────────────────────────────────────────
# Company / Dashboard Views
# ─────────────────────────────────────────

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


@login_required
def listing_list(request):
    user = request.user
    properties = Property.objects.select_related('owner', 'broker')

    # Role-based filtering
    if user.role == 'property_owner':
        properties = properties.filter(owner=user)
    elif user.role == 'sale_assistant':
        properties = properties.filter(listing_status='approved')

    # Filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    if search:
        properties = properties.filter(
            Q(title__icontains=search) |
            Q(city__icontains=search) |
            Q(address__icontains=search)
        )
    if status_filter:
        properties = properties.filter(listing_status=status_filter)
    if type_filter:
        properties = properties.filter(property_type=type_filter)

    context = {
        'properties': properties.order_by('-created_at'),
        'search': search,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'total': properties.count(),
        'pending': Property.objects.filter(listing_status='pending_approval').count(),
        'approved': Property.objects.filter(listing_status='approved').count(),
        'flagged': Property.objects.filter(listing_status='flagged').count(),
        'status_choices': Property.LISTING_STATUS_CHOICES,
        'type_choices': Property.PROPERTY_TYPE_CHOICES,
    }
    return render(request, 'listings/list.html', context)


@login_required
def listing_create(request):
    if request.user.role not in ['broker', 'staff', 'property_owner', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to add listings.')
        return redirect('listings:list')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        property_type = request.POST.get('property_type')
        address = request.POST.get('address')
        city = request.POST.get('city')
        province = request.POST.get('province')
        zip_code = request.POST.get('zip_code')
        price = request.POST.get('price')
        lot_area = request.POST.get('lot_area') or None
        floor_area = request.POST.get('floor_area') or None
        bedrooms = request.POST.get('bedrooms', 0)
        bathrooms = request.POST.get('bathrooms', 0)
        garage = request.POST.get('garage', 0)
        amenities = request.POST.get('amenities', '')
        is_negotiable = 'is_negotiable' in request.POST
        latitude = request.POST.get('latitude') or None
        longitude = request.POST.get('longitude') or None

        # Owner logic
        if request.user.role == 'property_owner':
            owner = request.user
            listing_status = 'pending_approval'
        else:
            owner_id = request.POST.get('owner_id')
            from apps.accounts.models import CustomUser
            owner = get_object_or_404(
                CustomUser, pk=owner_id, role='property_owner'
            ) if owner_id else request.user
            listing_status = 'pending_approval'

        property = Property.objects.create(
            title=title,
            description=description,
            property_type=property_type,
            address=address,
            city=city,
            province=province,
            zip_code=zip_code,
            price=price,
            lot_area=lot_area,
            floor_area=floor_area,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            garage=garage,
            amenities=amenities,
            is_negotiable=is_negotiable,
            latitude=latitude,
            longitude=longitude,
            owner=owner,
            listing_status=listing_status,
        )

        # Tags
        tag_ids = request.POST.getlist('tags')
        if tag_ids:
            property.tags.set(tag_ids)

        # Images
        images = request.FILES.getlist('images')
        for i, image in enumerate(images):
            PropertyImage.objects.create(
                property=property,
                image=image,
                is_primary=(i == 0)
            )

        # Status log
        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status='draft',
            new_status=listing_status,
            remarks='Property created and submitted for approval.'
        )
        notify_listing_submitted(property)
        
        messages.success(request, f'Property "{title}" submitted for approval.')
        return redirect('listings:list')

    from apps.accounts.models import CustomUser
    owners = CustomUser.objects.filter(role='property_owner')
    tags = PropertyTag.objects.all()

    return render(request, 'listings/create.html', {
        'type_choices': Property.PROPERTY_TYPE_CHOICES,
        'owners': owners,
        'tags': tags,
    })


@login_required
def listing_detail(request, pk):
    property = get_object_or_404(Property, pk=pk)
    status_logs = PropertyStatusLog.objects.filter(
        property=property
    ).order_by('-changed_at')

    return render(request, 'listings/detail.html', {
        'property': property,
        'status_logs': status_logs,
    })


@login_required
def listing_update(request, pk):
    property = get_object_or_404(Property, pk=pk)

    # Permission check
    if request.user.role == 'property_owner' and property.owner != request.user:
        messages.error(request, 'You can only edit your own properties.')
        return redirect('listings:list')

    if request.method == 'POST':
        old_status = property.listing_status

        property.title = request.POST.get('title', property.title)
        property.description = request.POST.get('description', property.description)
        property.property_type = request.POST.get('property_type', property.property_type)
        property.address = request.POST.get('address', property.address)
        property.city = request.POST.get('city', property.city)
        property.province = request.POST.get('province', property.province)
        property.zip_code = request.POST.get('zip_code', property.zip_code)
        property.price = request.POST.get('price', property.price)
        property.lot_area = request.POST.get('lot_area') or None
        property.floor_area = request.POST.get('floor_area') or None
        property.bedrooms = request.POST.get('bedrooms', property.bedrooms)
        property.bathrooms = request.POST.get('bathrooms', property.bathrooms)
        property.garage = request.POST.get('garage', property.garage)
        property.amenities = request.POST.get('amenities', property.amenities)
        property.is_negotiable = 'is_negotiable' in request.POST
        property.latitude = request.POST.get('latitude') or None
        property.longitude = request.POST.get('longitude') or None

        # If owner updates, re-submit for approval
        if request.user.role == 'property_owner':
            property.listing_status = 'pending_approval'

        property.save()

        # Tags
        tag_ids = request.POST.getlist('tags')
        property.tags.set(tag_ids)

        # New images
        images = request.FILES.getlist('images')
        for i, image in enumerate(images):
            PropertyImage.objects.create(
                property=property,
                image=image,
                is_primary=False
            )

        # Log if status changed
        if request.user.role == 'property_owner' and old_status != 'pending_approval':
            PropertyStatusLog.objects.create(
                property=property,
                changed_by=request.user,
                old_status=old_status,
                new_status='pending_approval',
                remarks='Property updated and resubmitted for approval.'
            )

        messages.success(request, 'Property updated successfully.')
        return redirect('listings:detail', pk=property.pk)

    from apps.accounts.models import CustomUser
    owners = CustomUser.objects.filter(role='property_owner')
    tags = PropertyTag.objects.all()

    return render(request, 'listings/update.html', {
        'property': property,
        'type_choices': Property.PROPERTY_TYPE_CHOICES,
        'owners': owners,
        'tags': tags,
    })


@login_required
def listing_approve(request, pk):
    if request.user.role not in ['broker', 'admin'] and not request.user.is_superuser:
        messages.error(request, 'Only brokers can approve listings.')
        return redirect('listings:list')

    property = get_object_or_404(Property, pk=pk)

    if request.method == 'POST':
        old_status = property.listing_status
        property.listing_status = 'approved'
        property.approved_by = request.user
        property.approved_at = timezone.now()
        property.flagged_reason = None
        property.flagged_by = None
        property.save()

        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status=old_status,
            new_status='approved',
            remarks=request.POST.get('remarks', 'Listing approved.')
        )
        notify_listing_approved(property, request.user)
        messages.success(request, f'"{property.title}" has been approved and is now live.')
        return redirect('listings:detail', pk=property.pk)

    return render(request, 'listings/approve.html', {'property': property})


@login_required
def listing_reject(request, pk):
    if request.user.role not in ['broker', 'admin'] and not request.user.is_superuser:
        messages.error(request, 'Only brokers can reject listings.')
        return redirect('listings:list')

    property = get_object_or_404(Property, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        old_status = property.listing_status
        property.listing_status = 'rejected'
        property.rejected_reason = reason
        property.save()

        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status=old_status,
            new_status='rejected',
            remarks=reason
        )
        notify_listing_rejected(property, request.user, reason)
        messages.success(request, f'"{property.title}" has been rejected.')
        return redirect('listings:detail', pk=property.pk)

    return render(request, 'listings/reject.html', {'property': property})


@login_required
def listing_flag(request, pk):
    if request.user.role not in ['broker', 'staff', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to flag listings.')
        return redirect('listings:list')

    property = get_object_or_404(Property, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        old_status = property.listing_status
        property.listing_status = 'flagged'
        property.flagged_reason = reason
        property.flagged_by = request.user
        property.flagged_at = timezone.now()
        property.save()

        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status=old_status,
            new_status='flagged',
            remarks=reason
        )
        notify_listing_flagged(property, request.user, reason)
        messages.warning(request, f'"{property.title}" has been flagged for review.')
        return redirect('listings:detail', pk=property.pk)

    return render(request, 'listings/flag.html', {'property': property})


@login_required
def listing_archive(request, pk):
    if request.user.role not in ['broker', 'admin'] and not request.user.is_superuser:
        messages.error(request, 'Only brokers can archive listings.')
        return redirect('listings:list')

    property = get_object_or_404(Property, pk=pk)

    if request.method == 'POST':
        old_status = property.listing_status
        property.listing_status = 'archived'
        property.save()

        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status=old_status,
            new_status='archived',
            remarks=request.POST.get('remarks', 'Listing archived.')
        )

        messages.success(request, f'"{property.title}" has been archived.')
        return redirect('listings:list')

    return render(request, 'listings/archive.html', {'property': property})


@login_required
def listing_mark_sold(request, pk):
    if request.user.role not in ['broker', 'admin'] and not request.user.is_superuser:
        messages.error(request, 'Only brokers can mark listings as sold.')
        return redirect('listings:list')

    property = get_object_or_404(Property, pk=pk)

    if request.method == 'POST':
        old_status = property.listing_status
        property.listing_status = 'sold'
        property.save()

        PropertyStatusLog.objects.create(
            property=property,
            changed_by=request.user,
            old_status=old_status,
            new_status='sold',
            remarks='Property marked as sold.'
        )

        messages.success(request, f'"{property.title}" marked as sold.')
        return redirect('listings:detail', pk=property.pk)

    return redirect('listings:detail', pk=property.pk)


@login_required
def toggle_favorite(request, pk):
    property = get_object_or_404(Property, pk=pk)

    if property.favorited_by.filter(pk=request.user.pk).exists():
        property.favorited_by.remove(request.user)
        favorited = False
    else:
        property.favorited_by.add(request.user)
        favorited = True

    from django.http import JsonResponse
    return JsonResponse({'favorited': favorited})

def mortgage_calculator_view(request):
    return render(request, 'public/mortgage_calculator.html')


@login_required
def favorites_view(request):
    favorite_properties = request.user.favorite_properties.filter(
        listing_status='approved'
    ).order_by('-created_at')

    return render(request, 'public/favorites.html', {
        'properties': favorite_properties,
    })
    
    # ─────────────────────────────────────────
# Tags Management
# ─────────────────────────────────────────

@login_required
def tag_list(request):
    if request.user.role not in ['broker', 'admin', 'staff'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('listings:list')

    tags = PropertyTag.objects.annotate(
        property_count=Count('properties')
    ).order_by('name')

    return render(request, 'listings/tags/list.html', {
        'tags': tags,
        'total': tags.count(),
    })


@login_required
def tag_create(request):
    if request.user.role not in ['broker', 'admin', 'staff'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('listings:tags')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()

        if not name:
            messages.error(request, 'Tag name is required.')
            return redirect('listings:tag_create')

        if not slug:
            from django.utils.text import slugify
            slug = slugify(name)

        if PropertyTag.objects.filter(name__iexact=name).exists():
            messages.error(request, f'Tag "{name}" already exists.')
            return redirect('listings:tag_create')

        if PropertyTag.objects.filter(slug=slug).exists():
            messages.error(request, f'Slug "{slug}" already taken.')
            return redirect('listings:tag_create')

        tag = PropertyTag.objects.create(name=name, slug=slug)
        messages.success(request, f'Tag "{tag.name}" created successfully.')
        return redirect('listings:tags')

    return render(request, 'listings/tags/create.html')


@login_required
def tag_update(request, pk):
    if request.user.role not in ['broker', 'admin', 'staff'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('listings:tags')

    tag = get_object_or_404(PropertyTag, pk=pk)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        slug = request.POST.get('slug', '').strip()

        if not name:
            messages.error(request, 'Tag name is required.')
            return redirect('listings:tag_update', pk=pk)

        if PropertyTag.objects.filter(
            name__iexact=name
        ).exclude(pk=pk).exists():
            messages.error(request, f'Tag "{name}" already exists.')
            return redirect('listings:tag_update', pk=pk)

        tag.name = name
        tag.slug = slug
        tag.save()

        messages.success(request, f'Tag "{tag.name}" updated successfully.')
        return redirect('listings:tags')

    return render(request, 'listings/tags/update.html', {'tag': tag})


@login_required
def tag_delete(request, pk):
    if request.user.role not in ['broker', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'Only brokers can delete tags.')
        return redirect('listings:tags')

    tag = get_object_or_404(PropertyTag, pk=pk)

    if request.method == 'POST':
        name = tag.name
        tag.delete()
        messages.success(request, f'Tag "{name}" deleted.')
        return redirect('listings:tags')

    return render(request, 'listings/tags/delete.html', {'tag': tag})


@login_required
def tag_detail(request, pk):
    tag = get_object_or_404(PropertyTag, pk=pk)
    properties = Property.objects.filter(
        tags=tag,
        listing_status='approved'
    ).order_by('-created_at')

    return render(request, 'listings/tags/detail.html', {
        'tag': tag,
        'properties': properties,
        'total': properties.count(),
    })
    
def property_detail_view(request, pk):
    property = get_object_or_404(Property, pk=pk)

    related_properties = Property.objects.filter(
        listing_status='approved',
        property_type=property.property_type
    ).exclude(pk=pk)[:3]

    is_favorited = False
    has_active_reservation = False
    has_active_appointment = False  # ✅ Add this

    if request.user.is_authenticated:
        is_favorited = property.favorited_by.filter(
            pk=request.user.pk
        ).exists()

        if request.user.role == 'client':
            from apps.reservations.models import Reservation, Appointment
            has_active_reservation = Reservation.objects.filter(
                property=property,
                client=request.user,
                status__in=['pending', 'approved']
            ).exists()

            # ✅ Check active appointment
            has_active_appointment = Appointment.objects.filter(
                property=property,
                client=request.user,
                status__in=['pending', 'confirmed']
            ).exists()

    return render(request, 'public/property_detail.html', {
        'property': property,
        'related_properties': related_properties,
        'is_favorited': is_favorited,
        'has_active_reservation': has_active_reservation,
        'has_active_appointment': has_active_appointment,  # ✅
    })
    
def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        message = request.POST.get('message', '').strip()
        property_id = request.POST.get('property_id') or None

        if not name or not message:
            messages.error(request, 'Name and message are required.')
            return redirect('contact')

        from apps.accounts.models import ContactMessage
        property_obj = None
        if property_id:
            property_obj = Property.objects.filter(pk=property_id).first()

        ContactMessage.objects.create(
            name=name,
            email=email,
            phone=phone,
            message=message,
            property=property_obj,
        )

        messages.success(
            request,
            'Your message has been sent! We will contact you shortly.'
        )
        return redirect('contact')

    return render(request, 'public/contact.html')

