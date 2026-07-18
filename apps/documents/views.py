from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q
from .models import Document, DocumentAuditLog, DocumentChecklist
from apps.listings.models import Property
from apps.sales.models import Sale
from apps.reservations.models import Reservation
from apps.accounts.notify import (
    notify_document_uploaded,
    notify_document_approved,
    notify_document_rejected,
)


# ─────────────────────────────────────────
# Helper
# ─────────────────────────────────────────

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')


def log_action(document, user, action, description=''):
    DocumentAuditLog.objects.create(
        document=document,
        performed_by=user,
        action=action,
        description=description,
    )


# ─────────────────────────────────────────
# Document List
# ─────────────────────────────────────────

@login_required
def document_list(request):
    user = request.user

    # Clients can only see their own documents
    if user.role == 'client':
        documents = Document.objects.filter(uploaded_by=user)
    elif user.role == 'property_owner':
        documents = Document.objects.filter(uploaded_by=user)
    elif user.role == 'sale_assistant':
        documents = Document.objects.filter(
            is_confidential=False
        )
    else:
        documents = Document.objects.all()

    documents = documents.select_related(
        'uploaded_by', 'reviewed_by', 'property', 'sale'
    )

    # Filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')

    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(uploaded_by__first_name__icontains=search) |
            Q(uploaded_by__last_name__icontains=search)
        )
    if status_filter:
        documents = documents.filter(status=status_filter)
    if type_filter:
        documents = documents.filter(document_type=type_filter)

    documents = documents.order_by('property__title', '-created_at')

    # Group documents by property for a "documents by property" view
    grouped = {}
    unlinked = []
    for doc in documents:
        if doc.property_id:
            grouped.setdefault(doc.property_id, {'property': doc.property, 'docs': []})
            grouped[doc.property_id]['docs'].append(doc)
        else:
            unlinked.append(doc)
    property_groups = sorted(grouped.values(), key=lambda g: g['property'].title.lower())

    context = {
        'property_groups': property_groups,
        'unlinked_documents': unlinked,
        'search': search,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'status_choices': Document.STATUS_CHOICES,
        'type_choices': Document.DOCUMENT_TYPE_CHOICES,
        'total': documents.count(),
        'pending': documents.filter(status='pending_approval').count(),
        'approved': documents.filter(status='approved').count(),
        'rejected': documents.filter(status='rejected').count(),
    }
    return render(request, 'documents/list.html', context)


# ─────────────────────────────────────────
# Document Upload
# ─────────────────────────────────────────

@login_required
def document_upload(request):
    # Manual document upload has been removed. Documents are tracked per
    # property/sale through the workflow; this entry point is disabled.
    messages.info(request, 'Manual document upload has been removed. Documents are tracked by property.')
    return redirect('documents:list')


@login_required
def _document_upload_disabled(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        document_type = request.POST.get('document_type')
        file = request.FILES.get('file')
        file_format = request.POST.get('file_format', 'pdf')
        property_id = request.POST.get('property_id') or None
        sale_id = request.POST.get('sale_id') or None
        reservation_id = request.POST.get('reservation_id') or None
        is_confidential = 'is_confidential' in request.POST
        expiry_date = request.POST.get('expiry_date') or None
        remarks = request.POST.get('remarks', '')

        if not file:
            messages.error(request, 'Please select a file to upload.')
            return redirect('documents:upload')

        # Linked objects
        property_obj = None
        sale_obj = None
        reservation_obj = None

        if property_id:
            property_obj = get_object_or_404(Property, pk=property_id)
        if sale_id:
            sale_obj = get_object_or_404(Sale, pk=sale_id)
        if reservation_id:
            reservation_obj = get_object_or_404(Reservation, pk=reservation_id)

        document = Document.objects.create(
            title=title,
            document_type=document_type,
            file=file,
            file_format=file_format,
            property=property_obj,
            sale=sale_obj,
            reservation=reservation_obj,
            uploaded_by=request.user,
            is_confidential=is_confidential,
            expiry_date=expiry_date,
            remarks=remarks,
            status='pending_approval',
        )

        log_action(
            document, request.user, 'uploaded',
            f'Document uploaded by {request.user.username}'
        )
        notify_document_uploaded(document)
        messages.success(request, f'"{title}" uploaded successfully and pending approval.')
        return redirect('documents:detail', pk=document.pk)

    # Dropdown data
    properties = Property.objects.filter(
        listing_status__in=['approved', 'sold']
    )
    sales = Sale.objects.all()
    reservations = Reservation.objects.all()

    # Role-based filtering
    if request.user.role == 'property_owner':
        properties = properties.filter(owner=request.user)
        sales = sales.filter(property__owner=request.user)

    return render(request, 'documents/upload.html', {
        'type_choices': Document.DOCUMENT_TYPE_CHOICES,
        'format_choices': Document.FILE_FORMAT_CHOICES,
        'properties': properties,
        'sales': sales,
        'reservations': reservations,
    })


# ─────────────────────────────────────────
# Document Detail
# ─────────────────────────────────────────

@login_required
def document_detail(request, pk):
    document = get_object_or_404(Document, pk=pk)
    user = request.user

    # Permission check
    if user.role == 'client' and document.uploaded_by != user:
        messages.error(request, 'You do not have permission.')
        return redirect('documents:list')

    # Log view
    log_action(
        document, user, 'viewed',
        f'Document viewed by {user.username}'
    )

    audit_logs = DocumentAuditLog.objects.filter(
        document=document
    ).order_by('-performed_at')

    return render(request, 'documents/detail.html', {
        'document': document,
        'audit_logs': audit_logs,
    })


# ─────────────────────────────────────────
# Approve / Reject
# ─────────────────────────────────────────

@login_required
def document_approve(request, pk):
    if request.user.role not in ['broker', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'Only brokers can approve documents.')
        return redirect('documents:list')

    document = get_object_or_404(Document, pk=pk)

    if request.method == 'POST':
        document.status = 'approved'
        document.reviewed_by = request.user
        document.save()

        log_action(
            document, request.user, 'approved',
            f'Approved by {request.user.username}'
        )

        messages.success(request, f'"{document.title}" has been approved.')
        notify_document_approved(document, request.user)
        return redirect('documents:detail', pk=document.pk)

    return render(request, 'documents/approve.html', {
        'document': document
    })


@login_required
def document_reject(request, pk):
    if request.user.role not in ['broker', 'admin'] \
            and not request.user.is_superuser:
        messages.error(request, 'Only brokers can reject documents.')
        return redirect('documents:list')

    document = get_object_or_404(Document, pk=pk)

    if request.method == 'POST':
        feedback = request.POST.get('feedback', '')
        document.status = 'rejected'
        document.rejection_feedback = feedback
        document.reviewed_by = request.user
        document.save()

        log_action(
            document, request.user, 'rejected',
            f'Rejected by {request.user.username}. Reason: {feedback}'
        )

        messages.warning(request, f'"{document.title}" has been rejected.')
        notify_document_rejected(document, request.user, feedback)
        return redirect('documents:detail', pk=document.pk)

    return render(request, 'documents/reject.html', {
        'document': document
    })


# ─────────────────────────────────────────
# Update / Delete
# ─────────────────────────────────────────

@login_required
def document_update(request, pk):
    document = get_object_or_404(Document, pk=pk)

    # Only uploader or admin/broker can update
    if document.uploaded_by != request.user and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('documents:list')

    if request.method == 'POST':
        document.title = request.POST.get('title', document.title)
        document.document_type = request.POST.get(
            'document_type', document.document_type
        )
        document.remarks = request.POST.get('remarks', document.remarks)
        document.expiry_date = request.POST.get('expiry_date') or None
        document.is_confidential = 'is_confidential' in request.POST

        # New file version
        if request.FILES.get('file'):
            document.file = request.FILES['file']
            document.version += 1
            document.status = 'pending_approval'

        document.save()

        log_action(
            document, request.user, 'updated',
            f'Document updated by {request.user.username}'
        )

        messages.success(request, 'Document updated successfully.')
        return redirect('documents:detail', pk=document.pk)

    return render(request, 'documents/update.html', {
        'document': document,
        'type_choices': Document.DOCUMENT_TYPE_CHOICES,
        'format_choices': Document.FILE_FORMAT_CHOICES,
    })


# ─────────────────────────────────────────
# Search
# ─────────────────────────────────────────

@login_required
def document_search(request):
    query = request.GET.get('q', '')
    user = request.user
    documents = Document.objects.none()

    if query:
        # Start with role-based filtering
        if user.role == 'client':
            # Clients can only search their own documents
            base_documents = Document.objects.filter(uploaded_by=user)
        elif user.role == 'property_owner':
            # Property owners can only search their own documents
            base_documents = Document.objects.filter(uploaded_by=user)
        elif user.role == 'sale_assistant':
            # Sale assistants can search non-confidential documents
            base_documents = Document.objects.filter(is_confidential=False)
        else:
            # Brokers, admins, staff can search all documents
            base_documents = Document.objects.all()

        # Apply search filter
        documents = base_documents.filter(
            Q(title__icontains=query) |
            Q(document_type__icontains=query) |
            Q(uploaded_by__first_name__icontains=query) |
            Q(uploaded_by__last_name__icontains=query) |
            Q(property__title__icontains=query)
        )

    return render(request, 'documents/search.html', {
        'documents': documents,
        'query': query,
    })


# ─────────────────────────────────────────
# Checklist
# ─────────────────────────────────────────

@login_required
def document_checklist(request, sale_pk):
    sale = get_object_or_404(Sale, pk=sale_pk)
    checklists = DocumentChecklist.objects.filter(sale=sale)

    if request.method == 'POST':
        checklist_id = request.POST.get('checklist_id')
        checklist = get_object_or_404(DocumentChecklist, pk=checklist_id)
        checklist.is_submitted = not checklist.is_submitted
        if checklist.is_submitted:
            checklist.submitted_at = timezone.now()
        else:
            checklist.submitted_at = None
        checklist.save()
        messages.success(request, 'Checklist updated.')
        return redirect('documents:checklist', sale_pk=sale_pk)

    return render(request, 'documents/checklist.html', {
        'sale': sale,
        'checklists': checklists,
    })


# ─────────────────────────────────────────
# Client Document Tracking
# ─────────────────────────────────────────

@login_required
def client_documents(request):
    """Display all documents related to client's reservations"""
    if request.user.role != 'client':
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')

    # Get all documents uploaded by client
    documents = Document.objects.filter(uploaded_by=request.user).select_related(
        'reviewed_by', 'property', 'reservation'
    ).order_by('-created_at')

    # Statistics
    stats = {
        'total': documents.count(),
        'pending': documents.filter(status='pending_approval').count(),
        'approved': documents.filter(status='approved').count(),
        'rejected': documents.filter(status='rejected').count(),
    }

    # Filters
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    reservation_filter = request.GET.get('reservation', '')

    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(document_type__icontains=search)
        )
    if status_filter:
        documents = documents.filter(status=status_filter)
    if reservation_filter:
        documents = documents.filter(reservation_id=reservation_filter)

    # Get client's reservations for filter
    from apps.reservations.models import Reservation
    reservations = Reservation.objects.filter(client=request.user).order_by('-created_at')

    context = {
        'documents': documents,
        'stats': stats,
        'search': search,
        'status_filter': status_filter,
        'reservation_filter': reservation_filter,
        'reservations': reservations,
        'status_choices': Document.STATUS_CHOICES,
    }

    return render(request, 'documents/client_documents.html', context)


@login_required
def client_document_upload(request):
    """Allow client to upload documents for their reservations"""
    if request.user.role != 'client':
        messages.error(request, 'You do not have permission to upload documents.')
        return redirect('dashboard')

    # Get client's reservations (for dropdown and validation)
    from apps.reservations.models import Reservation
    client_reservations = Reservation.objects.filter(client=request.user).order_by('-created_at')

    if request.method == 'POST':
        title = request.POST.get('title')
        document_type = request.POST.get('document_type')
        file = request.FILES.get('file')
        file_format = request.POST.get('file_format', 'pdf')
        reservation_id = request.POST.get('reservation_id') or None
        remarks = request.POST.get('remarks', '')

        if not file:
            messages.error(request, 'Please select a file to upload.')
            return redirect('documents:client_upload')

        if not title or not document_type:
            messages.error(request, 'Please fill in all required fields.')
            return redirect('documents:client_upload')

        # Verify reservation belongs to client
        reservation_obj = None
        if reservation_id:
            try:
                reservation_obj = client_reservations.get(pk=reservation_id)
            except Reservation.DoesNotExist:
                messages.error(request, 'Invalid reservation selected.')
                return redirect('documents:client_upload')

        # Create document
        document = Document.objects.create(
            title=title,
            document_type=document_type,
            file=file,
            file_format=file_format,
            reservation=reservation_obj,
            uploaded_by=request.user,
            is_confidential=False,
            remarks=remarks,
            status='pending_approval',
        )

        log_action(
            document, request.user, 'uploaded',
            f'Document uploaded by client {request.user.username}'
        )
        notify_document_uploaded(document)
        messages.success(request, f'"{title}" uploaded successfully. It will be reviewed shortly.')
        return redirect('documents:client_documents')

    return render(request, 'documents/client_upload.html', {
        'type_choices': Document.DOCUMENT_TYPE_CHOICES,
        'format_choices': Document.FILE_FORMAT_CHOICES,
        'reservations': client_reservations,
    })


# ─────────────────────────────────────────
# Listing Document Tracking
# ─────────────────────────────────────────

@login_required
def listing_documents(request, property_pk):
    """
    Admin view for tracking and managing documents for a specific listing.
    Features:
    - View all documents for a property
    - Filter by status, document type
    - Search documents
    - Approve/reject documents inline
    - View document details and history
    """
    property = get_object_or_404(Property, pk=property_pk)
    
    # Permission check - only admin/broker/staff/owner can view
    user = request.user
    if user.role not in ['broker', 'admin', 'staff'] and not user.is_superuser:
        if user.role == 'property_owner' and property.owner != user:
            messages.error(request, 'You do not have permission to view these documents.')
            return redirect('listings:list')
        elif user.role != 'property_owner':
            messages.error(request, 'You do not have permission to view these documents.')
            return redirect('listings:list')
    
    # Get all documents for this property
    documents = Document.objects.filter(
        property=property
    ).select_related('uploaded_by', 'reviewed_by', 'reservation', 'sale')
    
    # Filters and Search
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('type', '')
    
    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(uploaded_by__first_name__icontains=search) |
            Q(uploaded_by__last_name__icontains=search) |
            Q(remarks__icontains=search)
        )
    
    if status_filter:
        documents = documents.filter(status=status_filter)
    
    if type_filter:
        documents = documents.filter(document_type=type_filter)
    
    # Order by newest first
    documents = documents.order_by('-created_at')
    
    # Get stats
    all_docs = Document.objects.filter(property=property)
    stats = {
        'total': all_docs.count(),
        'pending': all_docs.filter(status='pending_approval').count(),
        'approved': all_docs.filter(status='approved').count(),
        'rejected': all_docs.filter(status='rejected').count(),
    }
    
    context = {
        'property': property,
        'documents': documents,
        'stats': stats,
        'search': search,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'status_choices': Document.STATUS_CHOICES,
        'type_choices': Document.DOCUMENT_TYPE_CHOICES,
    }
    
    return render(request, 'documents/listing_tracking.html', context)