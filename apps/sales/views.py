from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum
from django.http import JsonResponse
from .models import Sale, PaymentSchedule, Disbursement, SaleTask
from apps.listings.models import Property
from apps.reservations.models import Reservation
from apps.accounts.models import CustomUser
from apps.accounts.notify import (
    notify_sale_created,
    notify_sale_approved,
    notify_disbursement_approved,
    notify_disbursement_completed,
    notify_task_assigned,
)


# ─────────────────────────────────────────
# Helper
# ─────────────────────────────────────────

def calculate_commissions(sale):
    net_price = sale.net_price
    commissions = {
        'sale_assistant': round(net_price * 0.025, 2),
        'broker': round(net_price * 0.025, 2),
        'company': round(net_price * 0.015, 2),
        'owner': round(net_price * 0.935, 2),
    }
    return commissions


# ─────────────────────────────────────────
# Sales
# ─────────────────────────────────────────

@login_required
def sale_list(request):
    user = request.user

    if user.role == 'sale_assistant':
        sales = Sale.objects.filter(sale_assistant=user)
    elif user.role == 'property_owner':
        sales = Sale.objects.filter(property__owner=user)
    elif user.role == 'client':
        sales = Sale.objects.filter(client=user)
    else:
        sales = Sale.objects.all()

    sales = sales.select_related('property', 'client', 'sale_assistant')

    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    if search:
        sales = sales.filter(
            Q(property__title__icontains=search) |
            Q(client__first_name__icontains=search) |
            Q(client__last_name__icontains=search)
        )
    if status_filter:
        sales = sales.filter(status=status_filter)

    total_amount = sales.aggregate(total=Sum('net_price'))['total'] or 0

    context = {
        'sales': sales.order_by('-created_at'),
        'search': search,
        'status_filter': status_filter,
        'status_choices': Sale.STATUS_CHOICES,
        'total': sales.count(),
        'total_amount': total_amount,
        'pending': sales.filter(status='pending_verification').count(),
        'approved': sales.filter(status='approved').count(),
        'completed': sales.filter(status='completed').count(),
    }
    return render(request, 'sales/list.html', context)


@login_required
def sale_create(request):
    
    allowed = ['broker', 'admin', 'staff']
    if request.user.role not in allowed and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')
    if request.user.role not in ['broker', 'staff', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')

    if request.method == 'POST':
        property_id = request.POST.get('property_id')
        client_id = request.POST.get('client_id')
        sale_assistant_id = request.POST.get('sale_assistant_id')
        payment_scheme = request.POST.get('payment_scheme')
        selling_price = float(request.POST.get('selling_price') or 0)
        discount = float(request.POST.get('discount') or 0)
        sale_date = request.POST.get('sale_date')
        notes = request.POST.get('notes', '')
        reservation_id = request.POST.get('reservation_id') or None

        property_obj = get_object_or_404(Property, pk=property_id)
        client = get_object_or_404(CustomUser, pk=client_id, role='client')

        sale_assistant = None
        if sale_assistant_id:
            sale_assistant = get_object_or_404(
                CustomUser, pk=sale_assistant_id,
                role='sale_assistant'
            )

        reservation = None
        if reservation_id:
            reservation = get_object_or_404(Reservation, pk=reservation_id)

        # ✅ Create sale FIRST then notify
        sale = Sale.objects.create(
            property=property_obj,
            client=client,
            sale_assistant=sale_assistant,
            broker=request.user if request.user.role == 'broker' else None,
            payment_scheme=payment_scheme,
            selling_price=selling_price,
            discount=discount,
            net_price=selling_price - discount,   # both already floats now
            sale_date=sale_date,
            notes=notes,
            reservation=reservation,
            status='pending_verification',
        )

        # Auto calculate commissions
        commissions = calculate_commissions(sale)

        if sale.sale_assistant:
            Disbursement.objects.create(
                sale=sale,
                recipient=sale.sale_assistant,
                disbursement_type='sale_assistant_commission',
                amount=commissions['sale_assistant'],
                percentage=2.5,
                status='in_review',
            )

        if sale.broker:
            Disbursement.objects.create(
                sale=sale,
                recipient=sale.broker,
                disbursement_type='broker_commission',
                amount=commissions['broker'],
                percentage=2.5,
                status='in_review',
            )

        Disbursement.objects.create(
            sale=sale,
            recipient=property_obj.owner,
            disbursement_type='owner_proceeds',
            amount=commissions['owner'],
            percentage=93.5,
            status='in_review',
        )

        property_obj.listing_status = 'sold'
        property_obj.save()

        # ✅ Notify AFTER sale is created
        notify_sale_created(sale)

        messages.success(request, f'Sale created successfully for {property_obj.title}.')
        return redirect('sales:detail', pk=sale.pk)

    properties = Property.objects.filter(listing_status='approved')
    clients = CustomUser.objects.filter(role='client')
    sale_assistants = CustomUser.objects.filter(role='sale_assistant')
    reservations = Reservation.objects.filter(status='approved')

    return render(request, 'sales/create.html', {
        'properties': properties,
        'clients': clients,
        'sale_assistants': sale_assistants,
        'reservations': reservations,
        'payment_schemes': Sale.PAYMENT_SCHEME_CHOICES,
    })


@login_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    user = request.user

    if user.role == 'sale_assistant' and sale.sale_assistant != user:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')
    if user.role == 'property_owner' and sale.property.owner != user:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')
    if user.role == 'client' and sale.client != user:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')

    disbursements = Disbursement.objects.filter(sale=sale)
    payment_schedules = PaymentSchedule.objects.filter(sale=sale)
    tasks = SaleTask.objects.filter(sale=sale)

    return render(request, 'sales/detail.html', {
        'sale': sale,
        'disbursements': disbursements,
        'payment_schedules': payment_schedules,
        'tasks': tasks,
        'commissions': calculate_commissions(sale),
    })


@login_required
def sale_verify(request, pk):
    allowed = ['broker', 'admin', 'staff']
    if request.user.role not in allowed and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')
    if request.user.role not in ['broker', 'staff', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')

    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'approve':
            sale.status = 'approved'
            sale.verified_by = request.user
            sale.verified_at = timezone.now()
            sale.approved_by = request.user
            sale.approved_at = timezone.now()
            sale.save()

            # ✅ Notify INSIDE the approve block
            notify_sale_approved(sale, request.user)
            messages.success(request, 'Sale approved successfully.')

        elif action == 'correct':
            sale.selling_price = float(request.POST.get('selling_price') or sale.selling_price)
            sale.discount = float(request.POST.get('discount') or sale.discount)
            sale.net_price = sale.selling_price - sale.discount  # now both floats
            sale.notes = request.POST.get('notes', sale.notes)
            sale.status = 'ready_for_approval'
            sale.save()
            messages.success(request, 'Sale data corrected and ready for approval.')

        return redirect('sales:detail', pk=sale.pk)

    return render(request, 'sales/verify.html', {'sale': sale})


@login_required
def sale_update_status(request, pk):
    if request.user.role not in ['broker', 'staff', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')

    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        sale.status = new_status
        sale.save()
        messages.success(request, f'Sale status updated to {new_status}.')
        return redirect('sales:detail', pk=sale.pk)

    return render(request, 'sales/update_status.html', {
        'sale': sale,
        'status_choices': Sale.STATUS_CHOICES,
    })


@login_required
def assign_task(request, pk):
    sale = get_object_or_404(Sale, pk=pk)

    if request.user.role not in ['broker', 'staff', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:detail', pk=pk)

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        assigned_to_id = request.POST.get('assigned_to')
        priority = request.POST.get('priority', 'medium')
        due_date = request.POST.get('due_date') or None

        assigned_to = get_object_or_404(CustomUser, pk=assigned_to_id)

        # ✅ Store in variable then notify with correct variable
        task = SaleTask.objects.create(
            sale=sale,
            title=title,
            description=description,
            assigned_to=assigned_to,
            assigned_by=request.user,
            priority=priority,
            due_date=due_date,
        )

        # ✅ Use correct variable name
        notify_task_assigned(task)

        messages.success(request, f'Task assigned to {assigned_to.get_full_name()}.')
        return redirect('sales:detail', pk=pk)

    staff = CustomUser.objects.filter(role__in=['staff', 'sale_assistant'])

    return render(request, 'sales/assign_task.html', {
        'sale': sale,
        'staff': staff,
        'priority_choices': SaleTask.PRIORITY_CHOICES,
    })


# ─────────────────────────────────────────
# Disbursements
# ─────────────────────────────────────────

@login_required
def disbursement_list(request):
    user = request.user

    if user.role == 'sale_assistant':
        # Sale assistants see their own disbursements (view + calculate)
        disbursements = Disbursement.objects.filter(recipient=user)
    elif user.role == 'property_owner':
        disbursements = Disbursement.objects.filter(
            recipient=user,
            disbursement_type='owner_proceeds'
        )
    elif user.role in ['broker', 'admin']:
        disbursements = Disbursement.objects.all()
    else:
        # staff, client — no access to disbursements
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    disbursements = disbursements.select_related('sale', 'recipient')

    tab = request.GET.get('tab', 'all')
    if tab == 'in_review':
        disbursements = disbursements.filter(status='in_review')
    elif tab == 'pending':
        disbursements = disbursements.filter(status='pending')
    elif tab == 'completed':
        disbursements = disbursements.filter(status='completed')

    total_amount = disbursements.aggregate(total=Sum('amount'))['total'] or 0

    context = {
        'disbursements': disbursements.order_by('-created_at'),
        'tab': tab,
        'total_amount': total_amount,
        'in_review_count': Disbursement.objects.filter(status='in_review').count(),
        'pending_count': Disbursement.objects.filter(status='pending').count(),
        'completed_count': Disbursement.objects.filter(status='completed').count(),
    }
    return render(request, 'sales/disbursements.html', context)


@login_required
def disbursement_approve(request, pk):
    if request.user.role not in ['broker', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'Only brokers can approve disbursements.')
        return redirect('sales:disbursements')
    if request.user.role not in ['broker', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'Only brokers can approve disbursements.')
        return redirect('sales:disbursements')

    disbursement = get_object_or_404(Disbursement, pk=pk)

    if request.method == 'POST':
        new_amount = request.POST.get('amount')
        if new_amount:
            disbursement.amount = new_amount

        disbursement.status = 'pending'
        disbursement.approved_by = request.user
        disbursement.save()

        # ✅ Notify INSIDE the POST block BEFORE redirect
        notify_disbursement_approved(disbursement, request.user)

        messages.success(
            request,
            f'Disbursement approved for {disbursement.recipient.get_full_name()}.'
        )
        return redirect('sales:disbursements')

    return render(request, 'sales/disbursement_approve.html', {
        'disbursement': disbursement
    })


@login_required
def disbursement_receive(request, pk):
    disbursement = get_object_or_404(Disbursement, pk=pk)

    if disbursement.recipient != request.user:
        messages.error(request, 'You can only confirm your own disbursements.')
        return redirect('sales:disbursements')

    if disbursement.status != 'pending':
        messages.error(request, 'This disbursement is not in pending status.')
        return redirect('sales:disbursements')

    if request.method == 'POST':
        disbursement.status = 'completed'
        disbursement.received_by = request.user
        disbursement.received_at = timezone.now()
        disbursement.disbursed_at = timezone.now()
        disbursement.save()

        # ✅ Notify INSIDE the POST block BEFORE redirect
        notify_disbursement_completed(disbursement)

        messages.success(request, 'Payment receipt confirmed. Disbursement completed.')
        return redirect('sales:disbursements')

    return render(request, 'sales/disbursement_receive.html', {
        'disbursement': disbursement
    })