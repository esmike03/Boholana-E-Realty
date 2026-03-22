from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from apps.listings.models import Property
from apps.reservations.models import Reservation
from apps.sales.models import Sale
from apps.documents.models import Document
from .models import CustomUser, UserActivityLog, UserPreference, Notification



# ─────────────────────────────────────────
# Auth Views
# ─────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'client':
            return redirect('home')
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_disabled:
                messages.error(request, 'Your account has been disabled. Please contact the administrator.')
                return render(request, 'accounts/login.html')

            login(request, user)

            # Log activity
            UserActivityLog.objects.create(
                user=user,
                action='login',
                description=f'User logged in',
                ip_address=get_client_ip(request),
                performed_by=user
            )

            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')

            if user.role == 'client':
                return redirect(request.GET.get('next') or 'home')
            return redirect(request.GET.get('next') or 'dashboard')
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'accounts/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        UserActivityLog.objects.create(
            user=request.user,
            action='logout',
            description='User logged out',
            ip_address=get_client_ip(request),
            performed_by=request.user
        )
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        address = request.POST.get('address')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/register.html')

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'accounts/register.html')

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/register.html')

        if len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
            return render(request, 'accounts/register.html')

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            address=address,
            role='client',
        )

        UserPreference.objects.create(user=user)

        UserActivityLog.objects.create(
            user=user,
            action='register',
            description='New client registered',
            ip_address=get_client_ip(request),
            performed_by=user
        )

        login(request, user)
        messages.success(request, f'Welcome to Boholana E-Realty, {first_name}!')
        return redirect('home')

    return render(request, 'accounts/register.html')


# ─────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────

@login_required
def dashboard_view(request):
    user = request.user

    if user.role == 'client':
        return redirect('home')

    context = {}

    if user.role in ['broker', 'admin'] or user.is_superuser:
        context = {
            'total_properties': Property.objects.count(),
            'available_properties': Property.objects.filter(listing_status='approved').count(),
            'pending_properties': Property.objects.filter(listing_status='pending_approval').count(),
            'sold_properties': Property.objects.filter(listing_status='sold').count(),
            'total_reservations': Reservation.objects.count(),
            'pending_reservations': Reservation.objects.filter(status='pending').count(),
            'total_sales': Sale.objects.count(),
            'active_sales': Sale.objects.filter(status='approved').count(),
            'pending_documents': Document.objects.filter(status='pending_approval').count(),
            'total_users': CustomUser.objects.exclude(role='client').count(),
            'recent_reservations': Reservation.objects.select_related(
                'property', 'client'
            ).order_by('-created_at')[:5],
            'recent_sales': Sale.objects.select_related(
                'property', 'client'
            ).order_by('-created_at')[:5],
        }

    elif user.role == 'staff':
        context = {
            'total_properties': Property.objects.count(),
            'available_properties': Property.objects.filter(listing_status='approved').count(),
            'pending_properties': Property.objects.filter(listing_status='pending_approval').count(),
            'total_reservations': Reservation.objects.count(),
            'pending_reservations': Reservation.objects.filter(status='pending').count(),
            'pending_documents': Document.objects.filter(status='pending_approval').count(),
            'recent_reservations': Reservation.objects.select_related(
                'property', 'client'
            ).order_by('-created_at')[:5],
        }

    elif user.role == 'sale_assistant':
        context = {
            'total_sales': Sale.objects.filter(sale_assistant=user).count(),
            'active_sales': Sale.objects.filter(
                sale_assistant=user, status='approved'
            ).count(),
            'total_reservations': Reservation.objects.filter(handled_by=user).count(),
            'pending_reservations': Reservation.objects.filter(
                handled_by=user, status='pending'
            ).count(),
            'recent_sales': Sale.objects.filter(
                sale_assistant=user
            ).select_related('property', 'client').order_by('-created_at')[:5],
            'recent_reservations': Reservation.objects.filter(
                handled_by=user
            ).select_related('property', 'client').order_by('-created_at')[:5],
        }

    elif user.role == 'property_owner':
        context = {
            'total_properties': Property.objects.filter(owner=user).count(),
            'available_properties': Property.objects.filter(
                owner=user, listing_status='approved'
            ).count(),
            'pending_properties': Property.objects.filter(
                owner=user, listing_status='pending_approval'
            ).count(),
            'sold_properties': Property.objects.filter(
                owner=user, listing_status='sold'
            ).count(),
            'recent_sales': Sale.objects.filter(
                property__owner=user
            ).select_related('property', 'client').order_by('-created_at')[:5],
        }

    return render(request, 'accounts/dashboard.html', context)


# ─────────────────────────────────────────
# Profile
# ─────────────────────────────────────────

@login_required
def profile_view(request):
    user = request.user
    try:
        preference = user.preferences
    except UserPreference.DoesNotExist:
        preference = UserPreference.objects.create(user=user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'personal':
            user.first_name = request.POST.get('first_name', user.first_name)
            user.last_name = request.POST.get('last_name', user.last_name)
            user.email = request.POST.get('email', user.email)
            user.phone_number = request.POST.get('phone_number', user.phone_number)
            user.address = request.POST.get('address', user.address)
            user.birth_date = request.POST.get('birth_date') or None
            user.gender = request.POST.get('gender', user.gender)
            if request.FILES.get('profile_picture'):
                user.profile_picture = request.FILES['profile_picture']
            user.save()

            UserActivityLog.objects.create(
                user=user,
                action='update_profile',
                description='User updated personal information',
                ip_address=get_client_ip(request),
                performed_by=user
            )
            messages.success(request, 'Profile updated successfully.')

        elif form_type == 'password':
            from django.contrib.auth import update_session_auth_hash
            current_password = request.POST.get('current_password')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            if not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
            elif len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)

                UserActivityLog.objects.create(
                    user=user,
                    action='change_password',
                    description='User changed their password',
                    ip_address=get_client_ip(request),
                    performed_by=user
                )
                messages.success(request, 'Password changed successfully.')

        elif form_type == 'preferences':
            preference.preferred_property_type = request.POST.get(
                'preferred_property_type', ''
            ) or None
            preference.preferred_location = request.POST.get(
                'preferred_location', ''
            )
            preference.min_budget = request.POST.get('min_budget') or None
            preference.max_budget = request.POST.get('max_budget') or None
            preference.preferred_bedrooms = request.POST.get(
                'preferred_bedrooms'
            ) or None
            preference.preferred_bathrooms = request.POST.get(
                'preferred_bathrooms'
            ) or None
            preference.preferred_amenities = request.POST.get(
                'preferred_amenities', ''
            )
            preference.email_notifications = 'email_notifications' in request.POST
            preference.sms_notifications = 'sms_notifications' in request.POST
            preference.save()
            messages.success(request, 'Preferences saved successfully.')

        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {
        'preference': preference
    })


# ─────────────────────────────────────────
# Manage Users (Admin & Broker only)
# ─────────────────────────────────────────

@login_required
def users_list_view(request):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')

    # Filters
    role_filter = request.GET.get('role', '')
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    users = CustomUser.objects.all().order_by('-date_joined')

    if role_filter:
        users = users.filter(role=role_filter)

    if search:
        users = users.filter(
            Q(username__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )

    if status_filter == 'active':
        users = users.filter(is_disabled=False, is_active=True)
    elif status_filter == 'disabled':
        users = users.filter(is_disabled=True)

    context = {
        'users': users,
        'role_filter': role_filter,
        'search': search,
        'status_filter': status_filter,
        'role_choices': CustomUser.ROLE_CHOICES,
        'total_users': CustomUser.objects.count(),
        'active_users': CustomUser.objects.filter(is_disabled=False).count(),
        'disabled_users': CustomUser.objects.filter(is_disabled=True).count(),
    }

    return render(request, 'accounts/users_list.html', context)


@login_required
def user_create_view(request):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone_number = request.POST.get('phone_number')
        address = request.POST.get('address')
        role = request.POST.get('role')
        employee_id = request.POST.get('employee_id')
        department = request.POST.get('department')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        # Validations
        if password1 != password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'accounts/user_create.html', {
                'role_choices': CustomUser.ROLE_CHOICES
            })

        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
            return render(request, 'accounts/user_create.html', {
                'role_choices': CustomUser.ROLE_CHOICES
            })

        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'accounts/user_create.html', {
                'role_choices': CustomUser.ROLE_CHOICES
            })

        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            address=address,
            role=role,
            employee_id=employee_id,
            department=department,
            assigned_by=request.user,
            assigned_at=timezone.now(),
        )

        UserPreference.objects.create(user=user)

        UserActivityLog.objects.create(
            user=user,
            action='role_assigned',
            description=f'Account created with role: {role} by {request.user.username}',
            ip_address=get_client_ip(request),
            performed_by=request.user
        )

        messages.success(request, f'Account for {user.get_full_name()} created successfully.')
        return redirect('accounts:users')

    return render(request, 'accounts/user_create.html', {
        'role_choices': CustomUser.ROLE_CHOICES
    })


@login_required
def user_detail_view(request, pk):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    user = get_object_or_404(CustomUser, pk=pk)
    activity_logs = UserActivityLog.objects.filter(user=user).order_by('-created_at')[:10]

    return render(request, 'accounts/user_detail.html', {
        'viewed_user': user,
        'activity_logs': activity_logs,
    })


@login_required
def user_update_view(request, pk):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    user = get_object_or_404(CustomUser, pk=pk)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone_number = request.POST.get('phone_number', user.phone_number)
        user.address = request.POST.get('address', user.address)
        user.role = request.POST.get('role', user.role)
        user.employee_id = request.POST.get('employee_id', user.employee_id)
        user.department = request.POST.get('department', user.department)
        user.is_verified = 'is_verified' in request.POST

        user.save()

        UserActivityLog.objects.create(
            user=user,
            action='update_profile',
            description=f'Account updated by {request.user.username}',
            ip_address=get_client_ip(request),
            performed_by=request.user
        )

        messages.success(request, f'{user.get_full_name()} updated successfully.')
        return redirect('accounts:user_detail', pk=user.pk)

    return render(request, 'accounts/user_update.html', {
        'viewed_user': user,
        'role_choices': CustomUser.ROLE_CHOICES,
    })


@login_required
def user_disable_view(request, pk):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    user = get_object_or_404(CustomUser, pk=pk)

    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        action = request.POST.get('action')

        if action == 'disable':
            user.is_disabled = True
            user.disabled_reason = reason
            user.disabled_at = timezone.now()
            user.disabled_by = request.user
            user.save()

            UserActivityLog.objects.create(
                user=user,
                action='account_disabled',
                description=f'Account disabled by {request.user.username}. Reason: {reason}',
                ip_address=get_client_ip(request),
                performed_by=request.user
            )

            messages.success(request, f'{user.get_full_name()} account has been disabled.')

        elif action == 'enable':
            user.is_disabled = False
            user.disabled_reason = None
            user.disabled_at = None
            user.disabled_by = None
            user.save()

            UserActivityLog.objects.create(
                user=user,
                action='account_enabled',
                description=f'Account enabled by {request.user.username}',
                ip_address=get_client_ip(request),
                performed_by=request.user
            )

            messages.success(request, f'{user.get_full_name()} account has been enabled.')

        return redirect('accounts:user_detail', pk=user.pk)

    return render(request, 'accounts/user_disable.html', {
        'viewed_user': user
    })


@login_required
def assign_role_view(request, pk):
    if request.user.role not in ['admin', 'broker'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    user = get_object_or_404(CustomUser, pk=pk)

    if request.method == 'POST':
        new_role = request.POST.get('role')
        old_role = user.role
        user.role = new_role
        user.assigned_by = request.user
        user.assigned_at = timezone.now()
        user.save()

        UserActivityLog.objects.create(
            user=user,
            action='role_assigned',
            description=f'Role changed from {old_role} to {new_role} by {request.user.username}',
            ip_address=get_client_ip(request),
            performed_by=request.user
        )

        messages.success(request, f'Role updated to {user.get_role_display()} for {user.get_full_name()}.')
        return redirect('accounts:user_detail', pk=user.pk)

    return render(request, 'accounts/assign_role.html', {
        'viewed_user': user,
        'role_choices': CustomUser.ROLE_CHOICES,
    })


# ─────────────────────────────────────────
# Helper
# ─────────────────────────────────────────

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

def error_404(request, exception):
    return render(request, '404.html', status=404)

def error_500(request):
    return render(request, '500.html', status=500)



@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')

    # Mark all as read if requested
    if request.GET.get('mark_all_read'):
        from django.utils import timezone
        notifications.filter(is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        messages.success(request, 'All notifications marked as read.')
        return redirect('accounts:notifications')

    unread_count = notifications.filter(is_read=False).count()

    # Filter
    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'unread':
        notifications = notifications.filter(is_read=False)
    elif filter_type == 'read':
        notifications = notifications.filter(is_read=True)

    return render(request, 'accounts/notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
        'filter_type': filter_type,
    })


@login_required
def notification_read(request, pk):
    notification = get_object_or_404(
        Notification,
        pk=pk,
        recipient=request.user
    )
    notification.mark_as_read()

    if notification.link:
        return redirect(notification.link)
    return redirect('accounts:notifications')


@login_required
def notification_count(request):
    from django.http import JsonResponse
    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).count()
    return JsonResponse({'count': count})

@login_required
def notifications_json(request):
    from django.http import JsonResponse
    notifications = Notification.objects.filter(
        recipient=request.user,
        is_read=False
    ).order_by('-created_at')[:5]

    data = [{
        'id': n.pk,
        'title': n.title,
        'message': n.message[:80],
        'is_read': n.is_read,
        'created_at': n.created_at.strftime('%b %d, %Y'),
        'link': n.link or '',
        'priority': n.priority,
    } for n in notifications]

    return JsonResponse({'notifications': data})

@login_required
def global_search(request):
    query = request.GET.get('q', '').strip()
    results = {}

    if query and len(query) >= 2:
        from apps.listings.models import Property, PropertyTag
        from apps.reservations.models import Reservation, Appointment
        from apps.sales.models import Sale
        from apps.documents.models import Document

        user = request.user

        # Properties
        properties = Property.objects.filter(
            Q(title__icontains=query) |
            Q(city__icontains=query) |
            Q(address__icontains=query) |
            Q(description__icontains=query)
        )
        if user.role == 'property_owner':
            properties = properties.filter(owner=user)
        results['properties'] = properties[:5]

        # Reservations
        if user.role in ['broker', 'admin', 'staff', 'sale_assistant']:
            reservations = Reservation.objects.filter(
                Q(property__title__icontains=query) |
                Q(client__first_name__icontains=query) |
                Q(client__last_name__icontains=query)
            )
            results['reservations'] = reservations[:5]

        # Sales
        if user.role in ['broker', 'admin', 'staff', 'sale_assistant']:
            sales = Sale.objects.filter(
                Q(property__title__icontains=query) |
                Q(client__first_name__icontains=query) |
                Q(client__last_name__icontains=query)
            )
            if user.role == 'sale_assistant':
                sales = sales.filter(sale_assistant=user)
            results['sales'] = sales[:5]

        # Documents
        documents = Document.objects.filter(
            Q(title__icontains=query) |
            Q(document_type__icontains=query)
        )
        if user.role == 'property_owner':
            documents = documents.filter(uploaded_by=user)
        results['documents'] = documents[:5]

        # Users (broker/admin only)
        if user.role in ['broker', 'admin'] or user.is_superuser:
            users = CustomUser.objects.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(username__icontains=query) |
                Q(email__icontains=query)
            )
            results['users'] = users[:5]

    total_results = sum(
        len(v) for v in results.values()
        if hasattr(v, '__len__')
    )

    return render(request, 'accounts/search.html', {
        'query': query,
        'results': results,
        'total_results': total_results,
    })
    
    