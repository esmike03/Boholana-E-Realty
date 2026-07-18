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
from decimal import Decimal


# ─────────────────────────────────────────
# Helper
# ─────────────────────────────────────────

def create_disbursements_for_sale(sale):
    """Reusable function to create disbursements"""
    commissions = calculate_commissions(sale)
    created = 0

    # Sale Assistant
    if sale.sale_assistant and not Disbursement.objects.filter(sale=sale, recipient=sale.sale_assistant).exists():
        Disbursement.objects.create(
            sale=sale,
            recipient=sale.sale_assistant,
            disbursement_type='sale_assistant_commission',
            amount=commissions['sale_assistant'],
            percentage=2.5,
            status='in_review',
            remarks='Auto-generated'
        )
        created += 1

    # Broker
    if sale.broker and not Disbursement.objects.filter(sale=sale, recipient=sale.broker).exists():
        Disbursement.objects.create(
            sale=sale,
            recipient=sale.broker,
            disbursement_type='broker_commission',
            amount=commissions['broker'],
            percentage=2.5,
            status='in_review',
            remarks='Auto-generated'
        )
        created += 1

    # Property Owner
    if not Disbursement.objects.filter(sale=sale, recipient=sale.property.owner).exists():
        Disbursement.objects.create(
            sale=sale,
            recipient=sale.property.owner,
            disbursement_type='owner_proceeds',
            amount=commissions['owner'],
            percentage=93.5,
            status='in_review',
            remarks='Auto-generated'
        )
        created += 1

    # Company Share
    if sale.broker and not Disbursement.objects.filter(sale=sale, disbursement_type='company_share').exists():
        Disbursement.objects.create(
            sale=sale,
            recipient=sale.broker,
            disbursement_type='company_share',
            amount=commissions['company'],
            percentage=1.5,
            status='in_review',
            remarks='Auto-generated - Company share'
        )
        created += 1

    return created

def calculate_commissions(sale):
    """Calculate commissions using Decimal for money precision"""
    net_price = sale.net_price  # This is now Decimal

    # Use Decimal percentages (never use float for money)
    rate_sale_assistant = Decimal('0.025')
    rate_broker         = Decimal('0.025')
    rate_company        = Decimal('0.015')
    rate_owner          = Decimal('0.935')

    commissions = {
        'sale_assistant': (net_price * rate_sale_assistant).quantize(Decimal('0.01')),
        'broker':         (net_price * rate_broker).quantize(Decimal('0.01')),
        'company':        (net_price * rate_company).quantize(Decimal('0.01')),
        'owner':          (net_price * rate_owner).quantize(Decimal('0.01')),
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

    from apps.pagination import paginate
    page_obj, querystring = paginate(request, sales.order_by('-created_at'), per_page=12)

    context = {
        'sales': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
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
    if request.user.role not in ['broker', 'staff', 'admin'] and not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('sales:list')

    if request.method == 'POST':
        property_id = request.POST.get('property_id')
        client_id = request.POST.get('client_id')
        sale_assistant_id = request.POST.get('sale_assistant_id')
        payment_scheme = request.POST.get('payment_scheme')
        selling_price_str = request.POST.get('selling_price')
        discount_str = request.POST.get('discount', '0')
        sale_date = request.POST.get('sale_date')
        notes = request.POST.get('notes', '')
        reservation_id = request.POST.get('reservation_id')

        # ✅ Convert to Decimal (precise money handling)
        try:
            selling_price = Decimal(selling_price_str)
            discount = Decimal(discount_str or '0')
        except Exception:
            messages.error(request, 'Invalid selling price or discount.')
            return redirect('sales:create')

        # Reject negative values (also blocks "-0")
        if selling_price <= 0:
            messages.error(request, 'Selling price must be greater than zero.')
            return redirect('sales:create')
        if discount < 0:
            messages.error(request, 'Discount cannot be negative.')
            return redirect('sales:create')
        if discount > selling_price:
            messages.error(request, 'Discount cannot exceed the selling price.')
            return redirect('sales:create')

        # Sale date cannot be in the future
        from datetime import date as _date, datetime as _dt
        if sale_date:
            try:
                _sd = _dt.strptime(sale_date, '%Y-%m-%d').date()
                if _sd > _date.today():
                    messages.error(request, 'Sale date cannot be in the future.')
                    return redirect('sales:create')
            except ValueError:
                messages.error(request, 'Invalid sale date.')
                return redirect('sales:create')

        property_obj = get_object_or_404(Property, pk=property_id)
        client = get_object_or_404(CustomUser, pk=client_id, role='client')

        sale_assistant = None
        if sale_assistant_id:
            sale_assistant = get_object_or_404(CustomUser, pk=sale_assistant_id, role='sale_assistant')

        reservation = None
        if reservation_id:
            reservation = get_object_or_404(Reservation, pk=reservation_id)

        # ✅ Create the Sale first
        sale = Sale.objects.create(
            property=property_obj,
            client=client,
            sale_assistant=sale_assistant,
            broker=request.user if request.user.role == 'broker' else None,
            payment_scheme=payment_scheme,
            selling_price=selling_price,
            discount=discount,
            sale_date=sale_date,
            notes=notes,
            reservation=reservation,
            status='pending_verification',
        )

        # Mark property as sold
        property_obj.listing_status = 'sold'
        property_obj.save()

        # NOTE: Commissions/disbursements are NOT generated here. They are
        # calculated only once a payment has been recorded for the sale
        # (see record_payment). This enforces "cannot calculate if no payment".
        messages.success(
            request,
            f'Sale #{sale.id} created successfully! '
            f'Record a payment to generate commissions and disbursements.'
        )
        notify_sale_created(sale)

        return redirect('sales:detail', pk=sale.pk)

    # GET request - show form
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

    total_paid = payment_schedules.aggregate(t=Sum('amount_paid'))['t'] or Decimal('0')
    has_payment = total_paid > 0

    return render(request, 'sales/detail.html', {
        'sale': sale,
        'disbursements': disbursements,
        'payment_schedules': payment_schedules,
        'tasks': tasks,
        # Commissions can only be calculated once a payment exists
        'commissions': calculate_commissions(sale) if has_payment else None,
        'has_payment': has_payment,
        'total_paid': total_paid,
        'balance': (sale.net_price - total_paid),
        'can_manage': request.user.role in ['broker', 'staff', 'admin'] or request.user.is_superuser,
    })


@login_required
def sale_verify(request, pk):
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

            # === Create Disbursements on Approval ===
            try:
                commissions = calculate_commissions(sale)
                created_count = 0

                # Sale Assistant Commission
                if sale.sale_assistant and not Disbursement.objects.filter(
                    sale=sale, recipient=sale.sale_assistant
                ).exists():
                    Disbursement.objects.create(
                        sale=sale,
                        recipient=sale.sale_assistant,
                        disbursement_type='sale_assistant_commission',
                        amount=commissions['sale_assistant'],
                        percentage=2.5,
                        status='in_review',
                        remarks='Generated on sale approval'
                    )
                    created_count += 1

                # Broker Commission
                if sale.broker and not Disbursement.objects.filter(
                    sale=sale, recipient=sale.broker
                ).exists():
                    Disbursement.objects.create(
                        sale=sale,
                        recipient=sale.broker,
                        disbursement_type='broker_commission',
                        amount=commissions['broker'],
                        percentage=2.5,
                        status='in_review',
                        remarks='Generated on sale approval'
                    )
                    created_count += 1

                # Owner Proceeds
                if not Disbursement.objects.filter(
                    sale=sale, recipient=sale.property.owner
                ).exists():
                    Disbursement.objects.create(
                        sale=sale,
                        recipient=sale.property.owner,
                        disbursement_type='owner_proceeds',
                        amount=commissions['owner'],
                        percentage=93.5,
                        status='in_review',
                        remarks='Generated on sale approval'
                    )
                    created_count += 1

                # Company Share
                if sale.broker and not Disbursement.objects.filter(
                    sale=sale, disbursement_type='company_share'
                ).exists():
                    Disbursement.objects.create(
                        sale=sale,
                        recipient=sale.broker,
                        disbursement_type='company_share',
                        amount=commissions['company'],
                        percentage=1.5,
                        status='in_review',
                        remarks='Generated on sale approval - Company share'
                    )
                    created_count += 1

                messages.success(
                    request, 
                    f'Sale #{sale.id} approved successfully! '
                    f'{created_count} disbursement(s) generated.'
                )

            except Exception as e:
                messages.warning(request, f'Sale approved, but error creating disbursements: {str(e)}')

            # Notify
            notify_sale_approved(sale, request.user)

        elif action == 'correct':
            # ... your existing correction code ...
            sale.status = 'ready_for_approval'
            sale.save()
            messages.success(request, 'Sale data corrected and ready for approval.')

        return redirect('sales:detail', pk=sale.pk)

    return render(request, 'sales/verify.html', {'sale': sale})


@login_required
def sale_update_status(request, pk):
    # Only admins may manually change a sale's status.
    # Staff and brokers can view status but not change it.
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, 'Only administrators can change a sale status.')
        return redirect('sales:detail', pk=pk)

    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        valid = [s[0] for s in Sale.STATUS_CHOICES]
        if new_status not in valid:
            messages.error(request, 'Invalid status.')
            return redirect('sales:detail', pk=sale.pk)
        sale.status = new_status
        sale.save()
        messages.success(request, f'Sale status updated to {sale.get_status_display()}.')
        return redirect('sales:detail', pk=sale.pk)

    return render(request, 'sales/update_status.html', {
        'sale': sale,
        'status_choices': Sale.STATUS_CHOICES,
    })


@login_required
def record_payment(request, pk):
    """Single action to record a client payment against a sale.

    On the first payment, commissions/disbursements are generated
    (they are intentionally not created before any payment exists).
    """
    if request.user.role not in ['broker', 'staff', 'admin', 'sale_assistant'] \
            and not request.user.is_superuser:
        messages.error(request, 'You do not have permission to record payments.')
        return redirect('sales:detail', pk=pk)

    sale = get_object_or_404(Sale, pk=pk)

    if request.method == 'POST':
        amount_str = request.POST.get('amount', '')
        pay_date = request.POST.get('payment_date') or timezone.now().date()
        remarks = request.POST.get('remarks', '')

        try:
            amount = Decimal(amount_str)
        except Exception:
            messages.error(request, 'Invalid payment amount.')
            return redirect('sales:detail', pk=pk)

        if amount <= 0:
            messages.error(request, 'Payment amount must be greater than zero.')
            return redirect('sales:detail', pk=pk)

        already_paid = PaymentSchedule.objects.filter(sale=sale).aggregate(
            t=Sum('amount_paid'))['t'] or Decimal('0')
        if amount > (sale.net_price - already_paid):
            messages.error(request, 'Payment exceeds the remaining balance.')
            return redirect('sales:detail', pk=pk)

        PaymentSchedule.objects.create(
            sale=sale,
            due_date=pay_date,
            amount_due=amount,
            amount_paid=amount,
            status='paid',
            paid_at=timezone.now(),
            remarks=remarks,
        )

        # First payment → generate commissions/disbursements
        if not Disbursement.objects.filter(sale=sale).exists():
            created = create_disbursements_for_sale(sale)
            messages.success(
                request,
                f'Payment of ₱{amount} recorded. {created} disbursement(s) generated.'
            )
        else:
            messages.success(request, f'Payment of ₱{amount} recorded.')

        # Mark sale completed once fully paid
        total_paid = already_paid + amount
        if total_paid >= sale.net_price and sale.status not in ['cancelled', 'defaulted']:
            sale.status = 'completed'
            sale.save()

        return redirect('sales:detail', pk=sale.pk)

    return redirect('sales:detail', pk=sale.pk)


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
        disbursements = Disbursement.objects.filter(recipient=user)
    elif user.role == 'property_owner':
        disbursements = Disbursement.objects.filter(
            recipient=user,
            disbursement_type='owner_proceeds'
        )
    elif user.role in ['broker', 'admin', 'staff'] or user.is_superuser:
        disbursements = Disbursement.objects.all()
    else:
        messages.error(request, 'You do not have permission to access disbursements.')
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

    from apps.pagination import paginate
    page_obj, querystring = paginate(request, disbursements.order_by('-created_at'), per_page=12)

    context = {
        'disbursements': page_obj,
        'page_obj': page_obj,
        'querystring': querystring,
        'tab': tab,
        'total_amount': total_amount,
        'in_review_count': Disbursement.objects.filter(status='in_review').count(),
        'pending_count': Disbursement.objects.filter(status='pending').count(),
        'completed_count': Disbursement.objects.filter(status='completed').count(),
    }
    return render(request, 'sales/disbursements.html', context)


@login_required
def disbursement_approve(request, pk):
    # Disbursement approval is an admin action; brokers have view-only access.
    if request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, 'Only administrators can approve disbursements.')
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

