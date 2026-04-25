from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.http import HttpResponse
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from .models import Report, ReportSchedule
from apps.listings.models import Property
from apps.sales.models import Sale, Disbursement
from apps.reservations.models import Reservation
from apps.documents.models import Document
from apps.accounts.models import ContactMessage, CustomUser


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def get_report_data(
    report_type,
    date_from=None,
    date_to=None,
    user=None,
    property_id=None,
    listing_status=None,
    sale_assistant_id=None,
    commission_user_id=None,
):
    data = {}
    from datetime import timedelta

    if report_type == 'sales_summary':
        sales = Sale.objects.all()
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
        if user and user.role == 'sale_assistant':
            sales = sales.filter(sale_assistant=user)
        if property_id:
            sales = sales.filter(property_id=property_id)
        if sale_assistant_id:
            sales = sales.filter(sale_assistant_id=sale_assistant_id)

        # --- Agent breakdown (same as sales_by_agent) ---
        # Only include sale assistants who have sales in the filtered queryset
        sale_assistants = CustomUser.objects.filter(
            role='sale_assistant',
            id__in=sales.values_list('sale_assistant_id', flat=True).distinct()
        )
        if sale_assistant_id:
            sale_assistants = sale_assistants.filter(id=sale_assistant_id)
        agent_data = []
        for sa in sale_assistants:
            sa_sales = sales.filter(sale_assistant=sa).select_related('property', 'client')
            total_commission = Disbursement.objects.filter(
                recipient=sa,
                disbursement_type='sale_assistant_commission'
            ).aggregate(total=Sum('amount'))['total'] or 0

            sales_details = []
            for sale in sa_sales.order_by('-sale_date'):
                disbursement = Disbursement.objects.filter(
                    sale=sale,
                    recipient=sa,
                    disbursement_type='sale_assistant_commission'
                ).first()
                if disbursement:
                    payment_status = disbursement.get_status_display()
                    paid_at = disbursement.disbursed_at.strftime('%b %d, %Y %I:%M %p') if disbursement.disbursed_at else 'N/A'
                else:
                    payment_status = 'No Disbursement'
                    paid_at = 'N/A'

                sales_details.append({
                    'property_title': sale.property.title,
                    'client_name': sale.client.get_full_name() or sale.client.username,
                    'net_price': float(sale.net_price),
                    'sale_status': sale.get_status_display(),
                    'sale_date': sale.sale_date.strftime('%b %d, %Y') if sale.sale_date else 'N/A',
                    'payment_status': payment_status,
                    'paid_at': paid_at,
                })

            agent_data.append({
                'agent': sa,
                'total_sales': sa_sales.count(),
                'total_revenue': sa_sales.aggregate(
                    total=Sum('net_price')
                )['total'] or 0,
                'total_commission': total_commission,
                'completion_rate': f"{(sa_sales.filter(status='completed').count() / sa_sales.count() * 100) if sa_sales.count() > 0 else 0:.1f}%",
                'sales_details': sales_details,
            })

        quarterly_data = []
        try:
            from django.db.models.functions import TruncQuarter
            quarterly_qs = sales.annotate(
                quarter=TruncQuarter('sale_date')
            ).values('quarter').annotate(
                count=Count('id'),
                revenue=Sum('net_price')
            ).order_by('quarter')
            for row in quarterly_qs:
                quarter_date = row['quarter']
                quarter_no = ((quarter_date.month - 1) // 3) + 1 if quarter_date else 0
                quarterly_data.append({
                    'label': f"{quarter_date.year} Q{quarter_no}" if quarter_date else 'N/A',
                    'count': row['count'],
                    'revenue': row['revenue'] or 0,
                })
        except Exception:
            quarterly_data = []

        turnaround_rows = []
        total_turnaround_days = 0
        for sale in sales.select_related('property', 'sale_assistant'):
            if sale.property and sale.property.created_at and sale.sale_date:
                turnaround_days = (sale.sale_date - sale.property.created_at.date()).days
                total_turnaround_days += turnaround_days
                turnaround_rows.append({
                    'property': sale.property.title,
                    'listed_date': sale.property.created_at.date(),
                    'sold_date': sale.sale_date,
                    'turnaround_days': turnaround_days,
                    'sale_assistant': sale.sale_assistant.get_full_name() if sale.sale_assistant else 'N/A',
                })

        avg_turnaround_days = round(
            total_turnaround_days / len(turnaround_rows), 1
        ) if turnaround_rows else 0

        data = {
            'sales': sales.select_related('property', 'client', 'sale_assistant'),
            'total_sales': sales.count(),
            'total_revenue': sales.aggregate(
                total=Sum('net_price')
            )['total'] or 0,
            'completed': sales.filter(status='completed').count(),
            'pending': sales.filter(status='pending_verification').count(),
            'agent_data': agent_data,
            'quarterly_data': quarterly_data,
            'turnaround_data': turnaround_rows,
            'avg_turnaround_days': avg_turnaround_days,
        }

    elif report_type == 'commission_report':
        disbursements = Disbursement.objects.all()
        if date_from:
            disbursements = disbursements.filter(created_at__date__gte=date_from)
        if date_to:
            disbursements = disbursements.filter(created_at__date__lte=date_to)
        if commission_user_id:
            disbursements = disbursements.filter(recipient_id=commission_user_id)
        if user and user.role == 'sale_assistant':
            disbursements = disbursements.filter(recipient=user)
        
        data = {
            'disbursements': disbursements.select_related('sale', 'recipient', 'sale__property'),
            'total_disbursed': disbursements.filter(
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'pending_amount': disbursements.filter(
                status='pending'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'total_commission': disbursements.aggregate(total=Sum('amount'))['total'] or 0,
        }

    elif report_type == 'property_inventory':
        properties = Property.objects.all()
        if user and user.role == 'property_owner':
            properties = properties.filter(owner=user)
        data = {
            'properties': properties.select_related('owner'),
            'total': properties.count(),
            'approved': properties.filter(listing_status='approved').count(),
            'sold': properties.filter(listing_status='sold').count(),
            'pending': properties.filter(listing_status='pending_approval').count(),
        }

    elif report_type == 'reservation_summary':
        reservations = Reservation.objects.all()
        if date_from:
            reservations = reservations.filter(reservation_date__gte=date_from)
        if date_to:
            reservations = reservations.filter(reservation_date__lte=date_to)
        data = {
            'reservations': reservations.select_related('property', 'client'),
            'total': reservations.count(),
            'approved': reservations.filter(status='approved').count(),
            'pending': reservations.filter(status='pending').count(),
            'cancelled': reservations.filter(status='cancelled').count(),
        }

    elif report_type == 'sales_turnaround':
        # Calculate turnaround time from listing to sale
        sales = Sale.objects.all()
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
        
        turnaround_data = []
        total_days = 0
        for sale in sales.select_related('property', 'sale_assistant'):
            if sale.property.created_at and sale.sale_date:
                days = (sale.sale_date - sale.property.created_at.date()).days
                turnaround_data.append({
                    'property': sale.property.title,
                    'property_id': sale.property.id,
                    'listed_date': sale.property.created_at.date(),
                    'sold_date': sale.sale_date,
                    'turnaround_days': days,
                    'sale_assistant': sale.sale_assistant.get_full_name() if sale.sale_assistant else 'N/A',
                    'price': sale.net_price,
                })
                total_days += days
        
        avg_turnaround = total_days / len(turnaround_data) if turnaround_data else 0
        data = {
            'turnaround_data': turnaround_data,
            'total_sales': len(turnaround_data),
            'avg_turnaround_days': round(avg_turnaround, 1),
            'min_turnaround': min([t['turnaround_days'] for t in turnaround_data]) if turnaround_data else 0,
            'max_turnaround': max([t['turnaround_days'] for t in turnaround_data]) if turnaround_data else 0,
        }

    elif report_type == 'disbursement_summary':
        disbursements = Disbursement.objects.all()
        if date_from:
            disbursements = disbursements.filter(created_at__date__gte=date_from)
        if date_to:
            disbursements = disbursements.filter(created_at__date__lte=date_to)
        data = {
            'disbursements': disbursements.select_related('sale', 'recipient'),
            'total': disbursements.count(),
            'in_review': disbursements.filter(status='in_review').count(),
            'pending': disbursements.filter(status='pending').count(),
            'completed': disbursements.filter(status='completed').count(),
            'total_amount': disbursements.aggregate(
                total=Sum('amount')
            )['total'] or 0,
        }

    elif report_type == 'total_listings':
        properties = Property.objects.all()
        if listing_status:
            properties = properties.filter(listing_status=listing_status)

        status_display_map = {
            'draft': 'Draft',
            'pending_approval': 'Pending Approval',
            'flagged': 'Flagged for Review',
            'approved': 'Approved / For Sale',
            'reserved': 'Reserved',
            'rejected': 'Rejected',
            'sold': 'Sold',
            'archived': 'Archived',
        }

        listings_list = []
        for p in properties.select_related('owner').order_by('-created_at'):
            listings_list.append({
                'title': p.title,
                'property_type': p.get_property_type_display() if hasattr(p, 'get_property_type_display') else p.property_type,
                'price': float(p.price) if p.price else 0,
                'status': status_display_map.get(p.listing_status, p.listing_status),
                'owner': p.owner.get_full_name() if p.owner else 'N/A',
                'location': p.city if hasattr(p, 'city') and p.city else 'N/A',
                'created_at': p.created_at.strftime('%b %d, %Y') if p.created_at else 'N/A',
            })

        # Merge sales by sale assistant data
        sale_assistants = CustomUser.objects.filter(role='sale_assistant')
        agent_data = []
        for sa in sale_assistants:
            sa_sales = Sale.objects.filter(sale_assistant=sa).select_related('property', 'client')
            total_commission = Disbursement.objects.filter(
                recipient=sa,
                disbursement_type='sale_assistant_commission'
            ).aggregate(total=Sum('amount'))['total'] or 0

            # Build per-sale details
            sales_details = []
            for sale in sa_sales.order_by('-sale_date'):
                disbursement = Disbursement.objects.filter(
                    sale=sale,
                    recipient=sa,
                    disbursement_type='sale_assistant_commission'
                ).first()
                if disbursement:
                    payment_status = disbursement.get_status_display()
                    paid_at = disbursement.disbursed_at.strftime('%b %d, %Y %I:%M %p') if disbursement.disbursed_at else 'N/A'
                else:
                    payment_status = 'No Disbursement'
                    paid_at = 'N/A'

                sales_details.append({
                    'property_title': sale.property.title,
                    'client_name': sale.client.get_full_name() or sale.client.username,
                    'net_price': float(sale.net_price),
                    'sale_status': sale.get_status_display(),
                    'sale_date': sale.sale_date.strftime('%b %d, %Y') if sale.sale_date else 'N/A',
                    'payment_status': payment_status,
                    'paid_at': paid_at,
                })

            agent_data.append({
                'agent': sa,
                'total_sales': sa_sales.count(),
                'total_revenue': sa_sales.aggregate(
                    total=Sum('net_price')
                )['total'] or 0,
                'total_commission': total_commission,
                'completion_rate': f"{(sa_sales.filter(status='completed').count() / sa_sales.count() * 100) if sa_sales.count() > 0 else 0:.1f}%",
                'sales_details': sales_details,
            })

        data = {
            'total_properties': properties.count(),
            'approved': Property.objects.filter(listing_status='approved').count(),
            'sold': Property.objects.filter(listing_status='sold').count(),
            'pending': Property.objects.filter(listing_status='pending_approval').count(),
            'flagged': Property.objects.filter(listing_status='flagged').count(),
            'archived': Property.objects.filter(listing_status='archived').count(),
            'total_users': CustomUser.objects.count(),
            'total_sales': Sale.objects.count(),
            'total_reservations': Reservation.objects.count(),
            'total_revenue': Sale.objects.aggregate(
                total=Sum('net_price')
            )['total'] or 0,
            'listing_status_filter': status_display_map.get(listing_status, 'All Statuses'),
            'listings': listings_list,
            'agent_data': agent_data,
        }

    elif report_type == 'user_summary':
        role_display = {
            'admin': 'Admin',
            'broker': 'Broker',
            'staff': 'Staff',
            'property_owner': 'Property Owner',
            'sale_assistant': 'Sale Assistant',
            'client': 'Client',
        }
        users_list = []
        for u in CustomUser.objects.all().order_by('role', 'last_name', 'first_name'):
            users_list.append({
                'name': u.get_full_name() or u.username,
                'username': u.username,
                'email': u.email or 'N/A',
                'phone': u.phone_number or 'N/A',
                'role': role_display.get(u.role, u.role),
                'status': 'Disabled' if u.is_disabled else ('Active' if u.is_active else 'Inactive'),
                'date_joined': u.date_joined.strftime('%b %d, %Y') if u.date_joined else 'N/A',
            })
        data = {
            'total_users': CustomUser.objects.count(),
            'admins': CustomUser.objects.filter(role='admin').count(),
            'brokers': CustomUser.objects.filter(role='broker').count(),
            'staff': CustomUser.objects.filter(role='staff').count(),
            'sale_assistants': CustomUser.objects.filter(role='sale_assistant').count(),
            'property_owners': CustomUser.objects.filter(role='property_owner').count(),
            'clients': CustomUser.objects.filter(role='client').count(),
            'users': users_list,
        }

    elif report_type == 'total_inquiries':
        inquiries = ContactMessage.objects.all()
        if date_from:
            inquiries = inquiries.filter(created_at__date__gte=date_from)
        if date_to:
            inquiries = inquiries.filter(created_at__date__lte=date_to)
        if user and user.role == 'property_owner':
            inquiries = inquiries.filter(property__owner=user)
        data = {
            'inquiries': inquiries.select_related('property'),
            'total': inquiries.count(),
            'unread': inquiries.filter(is_read=False).count(),
            'responded': inquiries.filter(is_read=True).count(),
        }

    elif report_type == 'sales_by_property':
        # For property owners to see inquiries, reservations, sales for their properties
        properties = Property.objects.all()
        if user and user.role == 'property_owner':
            properties = properties.filter(owner=user)

        property_data = []
        for prop in properties:
            inquiries = ContactMessage.objects.filter(property=prop).count()
            reservations = Reservation.objects.filter(property=prop).count()
            # Get all sales for this property
            sales_qs = Sale.objects.filter(property=prop)
            sales_count = sales_qs.count()
            # Build detailed sales info
            sales_details = []
            for sale in sales_qs.select_related('client').order_by('-sale_date'):
                sales_details.append({
                    'id': sale.id,
                    'client_name': sale.client.get_full_name() if sale.client else 'N/A',
                    'net_price': float(sale.net_price),
                    'sale_status': sale.get_status_display(),
                    'sale_date': sale.sale_date.strftime('%b %d, %Y') if sale.sale_date else 'N/A',
                })
            property_data.append({
                'property': prop,
                'inquiries': inquiries,
                'reservations': reservations,
                'sales': sales_count,
                'sales_details': sales_details,
            })

        data = {
            'property_data': property_data,
            'total_properties': len(property_data),
            'total_inquiries': sum(p['inquiries'] for p in property_data),
            'total_reservations': sum(p['reservations'] for p in property_data),
            'total_sales': sum(p['sales'] for p in property_data),
        }


    elif report_type == 'sales_by_agent':
        sale_assistants = CustomUser.objects.filter(role='sale_assistant')
        filter_property_id = property_id
        filter_sale_assistant_id = sale_assistant_id

        # If a specific sale assistant is selected, only show that one
        if filter_sale_assistant_id:
            sale_assistants = sale_assistants.filter(id=filter_sale_assistant_id)

        agent_data = []
        for sa in sale_assistants:
            sa_sales = Sale.objects.filter(sale_assistant=sa)
            if filter_property_id:
                sa_sales = sa_sales.filter(property_id=filter_property_id)
            sa_sales = sa_sales.select_related('property', 'client')
            total_commission = Disbursement.objects.filter(
                recipient=sa,
                disbursement_type='sale_assistant_commission'
            ).aggregate(total=Sum('amount'))['total'] or 0

            # Build per-sale details
            sales_details = []
            for sale in sa_sales.order_by('-sale_date'):
                # Check disbursement payment status for this sale
                disbursement = Disbursement.objects.filter(
                    sale=sale,
                    recipient=sa,
                    disbursement_type='sale_assistant_commission'
                ).first()
                if disbursement:
                    payment_status = disbursement.get_status_display()
                    paid_at = disbursement.disbursed_at.strftime('%b %d, %Y %I:%M %p') if disbursement.disbursed_at else 'N/A'
                else:
                    payment_status = 'No Disbursement'
                    paid_at = 'N/A'

                sales_details.append({
                    'property_title': sale.property.title,
                    'client_name': sale.client.get_full_name() or sale.client.username,
                    'net_price': float(sale.net_price),
                    'sale_status': sale.get_status_display(),
                    'sale_date': sale.sale_date.strftime('%b %d, %Y') if sale.sale_date else 'N/A',
                    'payment_status': payment_status,
                    'paid_at': paid_at,
                })

            agent_data.append({
                'agent': sa,
                'total_sales': sa_sales.count(),
                'total_revenue': sa_sales.aggregate(
                    total=Sum('net_price')
                )['total'] or 0,
                'total_commission': total_commission,
                'completion_rate': f"{(sa_sales.filter(status='completed').count() / sa_sales.count() * 100) if sa_sales.count() > 0 else 0:.1f}%",
                'sales_details': sales_details,
            })
        data = {'agent_data': agent_data}

    elif report_type == 'document_status':
        documents = Document.objects.all()
        data = {
            'documents': documents.select_related('uploaded_by'),
            'total': documents.count(),
            'pending': documents.filter(status='pending_approval').count(),
            'approved': documents.filter(status='approved').count(),
            'rejected': documents.filter(status='rejected').count(),
        }

    elif report_type == 'listing_documents':
        properties = Property.objects.all()
        if user and user.role == 'property_owner':
            properties = properties.filter(owner=user)
        if property_id:
            properties = properties.filter(id=property_id)
        properties = properties.prefetch_related('documents', 'documents__uploaded_by').select_related('owner')

        listing_data = []
        total_docs = 0
        total_pending = 0
        total_approved = 0
        total_rejected = 0
        for prop in properties:
            docs = prop.documents.all()
            if date_from:
                docs = docs.filter(created_at__date__gte=date_from)
            if date_to:
                docs = docs.filter(created_at__date__lte=date_to)
            doc_list = []
            for doc in docs:
                doc_list.append({
                    'id': doc.id,
                    'title': doc.title,
                    'document_type': doc.get_document_type_display(),
                    'status': doc.status,
                    'status_display': doc.get_status_display(),
                    'uploaded_by': doc.uploaded_by.get_full_name() if doc.uploaded_by else 'N/A',
                    'file_format': doc.get_file_format_display(),
                    'created_at': doc.created_at,
                    'rejection_feedback': doc.rejection_feedback or '',
                })
            pending = docs.filter(status='pending_approval').count()
            approved = docs.filter(status='approved').count()
            rejected = docs.filter(status='rejected').count()
            total_docs += docs.count()
            total_pending += pending
            total_approved += approved
            total_rejected += rejected
            listing_data.append({
                'property': prop,
                'documents': doc_list,
                'total': docs.count(),
                'pending': pending,
                'approved': approved,
                'rejected': rejected,
            })

        data = {
            'listing_data': listing_data,
            'total_listings': len(listing_data),
            'total_documents': total_docs,
            'total_pending': total_pending,
            'total_approved': total_approved,
            'total_rejected': total_rejected,
        }

    elif report_type == 'monthly_sales':
        from django.db.models.functions import TruncMonth
        sales = Sale.objects.all()
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
        if user and user.role == 'sale_assistant':
            sales = sales.filter(sale_assistant=user)

        monthly = sales.annotate(
            month=TruncMonth('sale_date')
        ).values('month').annotate(
            count=Count('id'),
            revenue=Sum('net_price'),
        ).order_by('month')

        data = {
            'sales': sales.select_related('property', 'client', 'sale_assistant').order_by('-sale_date'),
            'monthly_data': list(monthly),
            'total_sales': sales.count(),
            'total_revenue': sales.aggregate(total=Sum('net_price'))['total'] or 0,
            'completed': sales.filter(status='completed').count(),
            'pending': sales.filter(status='pending_verification').count(),
        }

    return data


def generate_pdf_report(report, data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    title = Paragraph(
        f"<b>{report.get_report_type_display()}</b>",
        styles['Title']
    )
    elements.append(title)
    elements.append(Spacer(1, 10))

    # Date range
    if report.date_from or report.date_to:
        date_text = f"Period: {report.date_from or 'N/A'} to {report.date_to or 'N/A'}"
        elements.append(Paragraph(date_text, styles['Normal']))

    elements.append(Paragraph(
        f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}",
        styles['Normal']
    ))
    elements.append(Spacer(1, 20))

    # Content based on type
    if report.report_type == 'sales_summary':
        sales = data.get('sales', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Sales', str(data.get('total_sales', 0))],
            ['Total Revenue', f"₱{data.get('total_revenue', 0):,.2f}"],
            ['Completed', str(data.get('completed', 0))],
            ['Pending', str(data.get('pending', 0))],
        ]
        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        # Sales table
        table_data = [['#', 'Property', 'Client', 'Net Price', 'Status', 'Date']]
        for sale in sales[:50]:
            table_data.append([
                str(sale.id),
                sale.property.title[:25],
                sale.client.get_full_name() or sale.client.username,
                f"₱{sale.net_price:,.2f}",
                sale.get_status_display(),
                str(sale.sale_date),
            ])
        if table_data:
            t = Table(table_data, colWidths=[30, 130, 100, 80, 80, 70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)

    elif report.report_type == 'property_inventory':
        properties = data.get('properties', [])
        summary_data = [
            ['Metric', 'Count'],
            ['Total Properties', str(data.get('total', 0))],
            ['Approved / For Sale', str(data.get('approved', 0))],
            ['Sold', str(data.get('sold', 0))],
            ['Pending Approval', str(data.get('pending', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        prop_data = [['Title', 'Type', 'City', 'Price', 'Status']]
        for prop in properties[:50]:
            prop_data.append([
                prop.title[:30],
                prop.get_property_type_display(),
                prop.city,
                f"₱{prop.price:,.2f}",
                prop.get_listing_status_display(),
            ])
        if len(prop_data) > 1:
            t2 = Table(prop_data, colWidths=[130, 80, 80, 90, 100])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)

    elif report.report_type == 'total_inquiries':
        inquiries = data.get('inquiries', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Inquiries', str(data.get('total', 0))],
            ['Unread', str(data.get('unread', 0))],
            ['Responded', str(data.get('responded', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        table_data = [['#', 'Name', 'Email', 'Phone', 'Property', 'Received', 'Status']]
        for inquiry in inquiries[:50]:
            table_data.append([
                str(inquiry.id),
                inquiry.name,
                inquiry.email or 'N/A',
                inquiry.phone or 'N/A',
                inquiry.property.title if inquiry.property else 'N/A',
                str(inquiry.created_at.date()),
                'Read' if inquiry.is_read else 'Unread',
            ])
        if len(table_data) > 1:
            t2 = Table(table_data, colWidths=[30, 100, 100, 80, 100, 80, 70])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)

    elif report.report_type == 'total_listings':
        # Show filter applied
        status_filter = data.get('listing_status_filter', 'All Statuses')
        elements.append(Paragraph(f"<b>Filter:</b> {status_filter}", styles['Normal']))
        elements.append(Spacer(1, 10))

        overview_data = [
            ['Overview', 'Count/Value'],
            ['Total Properties (filtered)', str(data.get('total_properties', 0))],
            ['Approved Listings', str(data.get('approved', 0))],
            ['Sold Properties', str(data.get('sold', 0))],
            ['Pending Approval', str(data.get('pending', 0))],
            ['Flagged', str(data.get('flagged', 0))],
            ['Archived', str(data.get('archived', 0))],
            ['Total Users', str(data.get('total_users', 0))],
            ['Total Sales', str(data.get('total_sales', 0))],
            ['Total Reservations', str(data.get('total_reservations', 0))],
            ['Total Revenue', f"₱{data.get('total_revenue', 0):,.2f}"],
        ]
        t = Table(overview_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Listings detail table
        listings = data.get('listings', [])
        if listings:
            elements.append(Paragraph("<b>Listings Details</b>", styles['Normal']))
            elements.append(Spacer(1, 8))
            listing_table_data = [['Property', 'Type', 'Price', 'Status', 'Owner', 'Date Listed']]
            for item in listings[:100]:
                listing_table_data.append([
                    item['title'][:30],
                    item['property_type'],
                    f"₱{item['price']:,.2f}",
                    item['status'],
                    item['owner'][:20],
                    item['created_at'],
                ])
            lt = Table(listing_table_data, colWidths=[110, 70, 80, 80, 90, 70])
            lt.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(lt)

    elif report.report_type == 'listing_documents':
        listing_data = data.get('listing_data', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Listings', str(data.get('total_listings', 0))],
            ['Total Documents', str(data.get('total_documents', 0))],
            ['Approved', str(data.get('total_approved', 0))],
            ['Pending Approval', str(data.get('total_pending', 0))],
            ['Rejected', str(data.get('total_rejected', 0))],
        ]
        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        for listing in listing_data:
            prop = listing['property']
            elements.append(Paragraph(
                f"<b>{prop.title}</b> — {prop.get_listing_status_display()} | Owner: {prop.owner.get_full_name()}",
                styles['Heading4']
            ))
            elements.append(Spacer(1, 5))

            if listing['documents']:
                doc_table_data = [['Document', 'Type', 'Format', 'Status', 'Uploaded By', 'Date']]
                for d in listing['documents']:
                    doc_table_data.append([
                        d['title'][:30],
                        d['document_type'][:20],
                        d['file_format'],
                        d['status_display'],
                        d['uploaded_by'][:20],
                        str(d['created_at'].date()) if d['created_at'] else 'N/A',
                    ])
                dt = Table(doc_table_data, colWidths=[100, 90, 50, 80, 80, 70])
                dt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                    ('PADDING', (0, 0), (-1, -1), 5),
                ]))
                elements.append(dt)
            else:
                elements.append(Paragraph('No documents uploaded for this listing.', styles['Normal']))
            elements.append(Spacer(1, 15))

    elif report.report_type == 'commission_report':
        disbursements = data.get('disbursements', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Commission', f"₱{data.get('total_commission', 0):,.2f}"],
            ['Disbursed', f"₱{data.get('total_disbursed', 0):,.2f}"],
            ['Pending', f"₱{data.get('pending_amount', 0):,.2f}"],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        table_data = [['#', 'Sale', 'Recipient', 'Type', 'Amount', '%', 'Status']]
        for d in disbursements[:50]:
            table_data.append([
                str(d.id),
                d.sale.property.title[:20] if d.sale else 'N/A',
                d.recipient.get_full_name() or d.recipient.username,
                d.get_disbursement_type_display()[:20],
                f"₱{d.amount:,.2f}",
                f"{d.percentage}%" if d.percentage else 'N/A',
                d.get_status_display(),
            ])
        if len(table_data) > 1:
            t2 = Table(table_data, colWidths=[30, 90, 90, 90, 80, 40, 70])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)

    elif report.report_type == 'monthly_sales':
        monthly_data = data.get('monthly_data', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Sales', str(data.get('total_sales', 0))],
            ['Total Revenue', f"₱{data.get('total_revenue', 0):,.2f}"],
            ['Completed', str(data.get('completed', 0))],
            ['Pending', str(data.get('pending', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        elements.append(Paragraph('<b>Monthly Breakdown</b>', styles['Heading3']))
        elements.append(Spacer(1, 10))
        monthly_table = [['Month', 'Sales Count', 'Revenue']]
        for m in monthly_data:
            monthly_table.append([
                m['month'].strftime('%B %Y') if m['month'] else 'N/A',
                str(m['count']),
                f"₱{m['revenue'] or 0:,.2f}",
            ])
        if len(monthly_table) > 1:
            t2 = Table(monthly_table, colWidths=[160, 120, 150])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 8),
            ]))
            elements.append(t2)
        elements.append(Spacer(1, 20))

        elements.append(Paragraph('<b>Sales Details</b>', styles['Heading3']))
        elements.append(Spacer(1, 10))
        detail_table = [['#', 'Property', 'Client', 'Net Price', 'Status', 'Date']]
        for sale in data.get('sales', [])[:50]:
            detail_table.append([
                str(sale.id),
                sale.property.title[:25],
                sale.client.get_full_name() or sale.client.username,
                f"₱{sale.net_price:,.2f}",
                sale.get_status_display(),
                str(sale.sale_date),
            ])
        if len(detail_table) > 1:
            t3 = Table(detail_table, colWidths=[30, 130, 100, 80, 80, 70])
            t3.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t3)

    elif report.report_type == 'disbursement_summary':
        disbursements = data.get('disbursements', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Disbursements', str(data.get('total', 0))],
            ['In Review', str(data.get('in_review', 0))],
            ['Pending', str(data.get('pending', 0))],
            ['Completed', str(data.get('completed', 0))],
            ['Total Amount', f"₱{data.get('total_amount', 0):,.2f}"],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        table_data = [['#', 'Sale', 'Recipient', 'Type', 'Amount', 'Status']]
        for d in disbursements[:50]:
            table_data.append([
                str(d.id),
                str(d.sale.id),
                d.recipient.get_full_name() or d.recipient.username,
                d.get_disbursement_type_display()[:20],
                f"₱{d.amount:,.2f}",
                d.get_status_display(),
            ])
        if len(table_data) > 1:
            t2 = Table(table_data, colWidths=[30, 50, 120, 100, 90, 80])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)


    elif report.report_type == 'sales_by_agent':
        agent_data = data.get('agent_data', [])
        # Summary table
        table_data = [['Sale Assistant', 'Total Sales', 'Revenue', 'Commission', 'Completion Rate']]
        for a in agent_data:
            table_data.append([
                a['agent'].get_full_name(),
                str(a['total_sales']),
                f"₱{a['total_revenue']:,.2f}",
                f"₱{a['total_commission']:,.2f}",
                a['completion_rate'],
            ])
        if len(table_data) > 1:
            t = Table(table_data, colWidths=[120, 70, 100, 100, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)

        # Per-agent sales details
        for a in agent_data:
            sales_details = a.get('sales_details', [])
            if sales_details:
                elements.append(Spacer(1, 16))
                elements.append(Paragraph(f"<b>{a['agent'].get_full_name()} — Sales Details</b>", styles['Normal']))
                elements.append(Spacer(1, 6))
                detail_data = [['Property', 'Client', 'Price', 'Sale Status', 'Sale Date', 'Payment', 'Paid At']]
                for s in sales_details:
                    detail_data.append([
                        s['property_title'][:25],
                        s['client_name'][:20],
                        f"₱{s['net_price']:,.2f}",
                        s['sale_status'],
                        s['sale_date'],
                        s['payment_status'],
                        s['paid_at'],
                    ])
                dt = Table(detail_data, colWidths=[85, 70, 70, 70, 65, 65, 75])
                dt.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#334155')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f4f8')]),
                    ('PADDING', (0, 0), (-1, -1), 5),
                ]))
                elements.append(dt)

    elif report.report_type == 'sales_by_property':
        property_data = data.get('property_data', [])
        table_data = [['Property', 'Inquiries', 'Reservations', 'Sales']]
        for p in property_data:
            table_data.append([
                p['property'].title[:30],
                str(p['inquiries']),
                str(p['reservations']),
                str(p['sales']),
            ])
        if len(table_data) > 1:
            t = Table(table_data, colWidths=[200, 80, 80, 80])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)

    elif report.report_type == 'reservation_summary':
        reservations = data.get('reservations', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Reservations', str(data.get('total', 0))],
            ['Approved', str(data.get('approved', 0))],
            ['Pending', str(data.get('pending', 0))],
            ['Cancelled', str(data.get('cancelled', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        table_data = [['#', 'Property', 'Client', 'Date', 'Fee', 'Status']]
        for r in reservations[:50]:
            table_data.append([
                str(r.id),
                r.property.title[:25],
                r.client.get_full_name() or r.client.username,
                str(r.reservation_date),
                f"₱{r.reservation_fee:,.2f}",
                r.get_status_display(),
            ])
        if len(table_data) > 1:
            t2 = Table(table_data, colWidths=[30, 130, 100, 80, 80, 70])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)

    elif report.report_type == 'document_status':
        documents = data.get('documents', [])
        summary_data = [
            ['Metric', 'Value'],
            ['Total Documents', str(data.get('total', 0))],
            ['Approved', str(data.get('approved', 0))],
            ['Pending', str(data.get('pending', 0))],
            ['Rejected', str(data.get('rejected', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        table_data = [['#', 'Title', 'Type', 'Uploaded By', 'Status', 'Date']]
        for doc in documents[:50]:
            table_data.append([
                str(doc.id),
                doc.title[:25],
                doc.get_document_type_display()[:20],
                doc.uploaded_by.get_full_name() if doc.uploaded_by else 'N/A',
                doc.get_status_display(),
                str(doc.created_at.date()),
            ])
        if len(table_data) > 1:
            t2 = Table(table_data, colWidths=[30, 120, 100, 100, 70, 70])
            t2.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(t2)

    elif report.report_type == 'user_summary':
        summary_data = [
            ['Role', 'Count'],
            ['Total Users', str(data.get('total_users', 0))],
            ['Admins', str(data.get('admins', 0))],
            ['Brokers', str(data.get('brokers', 0))],
            ['Staff', str(data.get('staff', 0))],
            ['Sale Assistants', str(data.get('sale_assistants', 0))],
            ['Property Owners', str(data.get('property_owners', 0))],
            ['Clients', str(data.get('clients', 0))],
        ]
        t = Table(summary_data, colWidths=[200, 200])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 20))

        # Users detail table
        users = data.get('users', [])
        if users:
            elements.append(Paragraph("<b>Users List</b>", styles['Normal']))
            elements.append(Spacer(1, 8))
            users_table_data = [['Name', 'Username', 'Email', 'Phone', 'Role', 'Status', 'Joined']]
            for u in users:
                users_table_data.append([
                    u['name'][:25],
                    u['username'][:15],
                    u['email'][:25],
                    u['phone'],
                    u['role'],
                    u['status'],
                    u['date_joined'],
                ])
            ut = Table(users_table_data, colWidths=[80, 60, 100, 70, 70, 50, 70])
            ut.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a4a7a')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
                ('PADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(ut)

    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_excel_report(report, data):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report.get_report_type_display()[:30]

    # Header style
    header_fill = PatternFill(
        start_color="1a4a7a",
        end_color="1a4a7a",
        fill_type="solid"
    )
    header_font = Font(color="FFFFFF", bold=True)

    # Title
    ws['A1'] = report.get_report_type_display()
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}"
    if report.date_from:
        ws['A3'] = f"From: {report.date_from} To: {report.date_to or 'N/A'}"
    ws.append([])

    if report.report_type == 'sales_summary':
        headers = ['Sale #', 'Property', 'Client', 'Sale Assistant',
                   'Net Price', 'Payment Scheme', 'Status', 'Sale Date']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for sale in data.get('sales', []):
            ws.append([
                sale.id,
                sale.property.title,
                sale.client.get_full_name() or sale.client.username,
                sale.sale_assistant.get_full_name() if sale.sale_assistant else 'N/A',
                float(sale.net_price),
                sale.get_payment_scheme_display(),
                sale.get_status_display(),
                str(sale.sale_date),
            ])

        ws.append([])
        ws.append(['Summary'])
        ws.append(['Total Sales', data.get('total_sales', 0)])
        ws.append(['Total Revenue', float(data.get('total_revenue', 0))])

    elif report.report_type == 'commission_report':
        headers = ['Disbursement #', 'Sale #', 'Recipient', 'Role',
                   'Type', 'Amount', 'Percentage', 'Status']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for d in data.get('disbursements', []):
            ws.append([
                d.id,
                d.sale.id,
                d.recipient.get_full_name() or d.recipient.username,
                d.recipient.get_role_display(),
                d.get_disbursement_type_display(),
                float(d.amount),
                float(d.percentage) if d.percentage else 'N/A',
                d.get_status_display(),
            ])

    elif report.report_type == 'property_inventory':
        headers = ['Property', 'Type', 'City', 'Province',
                   'Price', 'Status', 'Owner', 'Date Listed']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for prop in data.get('properties', []):
            ws.append([
                prop.title,
                prop.get_property_type_display(),
                prop.city,
                prop.province,
                float(prop.price),
                prop.get_listing_status_display(),
                prop.owner.get_full_name(),
                str(prop.created_at.date()),
            ])

    elif report.report_type == 'reservation_summary':
        headers = ['Reservation #', 'Property', 'Client',
                   'Date', 'Fee', 'Status']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for r in data.get('reservations', []):
            ws.append([
                r.id,
                r.property.title,
                r.client.get_full_name() or r.client.username,
                str(r.reservation_date),
                float(r.reservation_fee),
                r.get_status_display(),
            ])

    elif report.report_type == 'sales_by_agent':
        headers = ['Sale Assistant', 'Total Sales',
                   'Total Revenue', 'Total Commission', 'Completion Rate']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for agent in data.get('agent_data', []):
            ws.append([
                agent['agent'].get_full_name(),
                agent['total_sales'],
                float(agent['total_revenue']),
                float(agent['total_commission']),
                agent['completion_rate'],
            ])

        # Per-agent sales details
        for agent in data.get('agent_data', []):
            sales_details = agent.get('sales_details', [])
            if sales_details:
                ws.append([])
                ws.append([f"{agent['agent'].get_full_name()} — Sales Details"])
                detail_headers = ['Property', 'Client', 'Price', 'Sale Status', 'Sale Date', 'Payment Status', 'Paid At']
                ws.append(detail_headers)
                for cell in ws[ws.max_row]:
                    cell.fill = header_fill
                    cell.font = header_font
                for s in sales_details:
                    ws.append([
                        s['property_title'],
                        s['client_name'],
                        s['net_price'],
                        s['sale_status'],
                        s['sale_date'],
                        s['payment_status'],
                        s['paid_at'],
                    ])

    elif report.report_type == 'total_inquiries':
        headers = ['Inquiry #', 'Name', 'Email', 'Phone', 'Property', 'Received', 'Status']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for inquiry in data.get('inquiries', []):
            ws.append([
                inquiry.id,
                inquiry.name,
                inquiry.email or 'N/A',
                inquiry.phone or 'N/A',
                inquiry.property.title if inquiry.property else 'N/A',
                str(inquiry.created_at.date()),
                'Read' if inquiry.is_read else 'Unread',
            ])

        ws.append([])
        ws.append(['Summary'])
        ws.append(['Total Inquiries', data.get('total', 0)])
        ws.append(['Unread', data.get('unread', 0)])
        ws.append(['Responded', data.get('responded', 0)])

    elif report.report_type == 'listing_documents':
        # Summary sheet
        ws.append(['Summary'])
        ws.append(['Total Listings', data.get('total_listings', 0)])
        ws.append(['Total Documents', data.get('total_documents', 0)])
        ws.append(['Approved', data.get('total_approved', 0)])
        ws.append(['Pending Approval', data.get('total_pending', 0)])
        ws.append(['Rejected', data.get('total_rejected', 0)])
        ws.append([])

        headers = ['Listing', 'Listing Status', 'Owner', 'Document', 'Doc Type',
                   'Format', 'Doc Status', 'Uploaded By', 'Date', 'Feedback']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for listing in data.get('listing_data', []):
            prop = listing['property']
            if listing['documents']:
                for doc in listing['documents']:
                    ws.append([
                        prop.title,
                        prop.get_listing_status_display(),
                        prop.owner.get_full_name(),
                        doc['title'],
                        doc['document_type'],
                        doc['file_format'],
                        doc['status_display'],
                        doc['uploaded_by'],
                        str(doc['created_at'].date()) if doc['created_at'] else 'N/A',
                        doc['rejection_feedback'],
                    ])
            else:
                ws.append([
                    prop.title,
                    prop.get_listing_status_display(),
                    prop.owner.get_full_name(),
                    'No documents', '', '', '', '', '', '',
                ])

    elif report.report_type == 'monthly_sales':
        # Monthly breakdown
        ws.append(['Monthly Breakdown'])
        headers = ['Month', 'Sales Count', 'Revenue']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for m in data.get('monthly_data', []):
            ws.append([
                m['month'].strftime('%B %Y') if m['month'] else 'N/A',
                m['count'],
                float(m['revenue'] or 0),
            ])

        ws.append([])
        ws.append(['Sales Details'])
        headers2 = ['Sale #', 'Property', 'Client', 'Sale Assistant',
                     'Net Price', 'Status', 'Sale Date']
        ws.append(headers2)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font

        for sale in data.get('sales', []):
            ws.append([
                sale.id,
                sale.property.title,
                sale.client.get_full_name() or sale.client.username,
                sale.sale_assistant.get_full_name() if sale.sale_assistant else 'N/A',
                float(sale.net_price),
                sale.get_status_display(),
                str(sale.sale_date),
            ])

        ws.append([])
        ws.append(['Summary'])
        ws.append(['Total Sales', data.get('total_sales', 0)])
        ws.append(['Total Revenue', float(data.get('total_revenue', 0))])
        ws.append(['Completed', data.get('completed', 0)])
        ws.append(['Pending', data.get('pending', 0)])

    elif report.report_type == 'total_listings':
        ws.append([f"Filter: {data.get('listing_status_filter', 'All Statuses')}"])
        ws.append([])
        ws.append(['Overview'])
        headers = ['Metric', 'Value']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        ws.append(['Total Properties (filtered)', data.get('total_properties', 0)])
        ws.append(['Approved Listings', data.get('approved', 0)])
        ws.append(['Sold Properties', data.get('sold', 0)])
        ws.append(['Pending Approval', data.get('pending', 0)])
        ws.append(['Flagged', data.get('flagged', 0)])
        ws.append(['Archived', data.get('archived', 0)])
        ws.append(['Total Users', data.get('total_users', 0)])
        ws.append(['Total Sales', data.get('total_sales', 0)])
        ws.append(['Total Reservations', data.get('total_reservations', 0)])
        ws.append(['Total Revenue', float(data.get('total_revenue', 0))])
        ws.append([])

        # Listings details
        ws.append(['Listings Details'])
        detail_headers = ['Property', 'Type', 'Price', 'Status', 'Owner', 'Date Listed']
        ws.append(detail_headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        for item in data.get('listings', []):
            ws.append([
                item['title'],
                item['property_type'],
                item['price'],
                item['status'],
                item['owner'],
                item['created_at'],
            ])

    elif report.report_type == 'disbursement_summary':
        headers = ['Disbursement #', 'Sale #', 'Recipient', 'Type', 'Amount', 'Status']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        for d in data.get('disbursements', []):
            ws.append([
                d.id,
                d.sale.id,
                d.recipient.get_full_name() or d.recipient.username,
                d.get_disbursement_type_display(),
                float(d.amount),
                d.get_status_display(),
            ])
        ws.append([])
        ws.append(['Summary'])
        ws.append(['Total', data.get('total', 0)])
        ws.append(['Total Amount', float(data.get('total_amount', 0))])


    elif report.report_type == 'sales_by_property':
        headers = ['Property', 'Inquiries', 'Reservations', 'Sales']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        for p in data.get('property_data', []):
            ws.append([
                p['property'].title,
                p['inquiries'],
                p['reservations'],
                p['sales'],
            ])

    elif report.report_type == 'document_status':
        headers = ['Doc #', 'Title', 'Type', 'Uploaded By', 'Status', 'Date']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        for doc in data.get('documents', []):
            ws.append([
                doc.id,
                doc.title,
                doc.get_document_type_display(),
                doc.uploaded_by.get_full_name() if doc.uploaded_by else 'N/A',
                doc.get_status_display(),
                str(doc.created_at.date()),
            ])
        ws.append([])
        ws.append(['Summary'])
        ws.append(['Total', data.get('total', 0)])
        ws.append(['Approved', data.get('approved', 0)])
        ws.append(['Pending', data.get('pending', 0)])
        ws.append(['Rejected', data.get('rejected', 0)])

    elif report.report_type == 'user_summary':
        headers = ['Role', 'Count']
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        ws.append(['Total Users', data.get('total_users', 0)])
        ws.append(['Admins', data.get('admins', 0)])
        ws.append(['Brokers', data.get('brokers', 0)])
        ws.append(['Staff', data.get('staff', 0)])
        ws.append(['Sale Assistants', data.get('sale_assistants', 0)])
        ws.append(['Property Owners', data.get('property_owners', 0)])
        ws.append(['Clients', data.get('clients', 0)])
        ws.append([])

        # Users details
        ws.append(['Users List'])
        detail_headers = ['Name', 'Username', 'Email', 'Phone', 'Role', 'Status', 'Date Joined']
        ws.append(detail_headers)
        for cell in ws[ws.max_row]:
            cell.fill = header_fill
            cell.font = header_font
        for u in data.get('users', []):
            ws.append([
                u['name'],
                u['username'],
                u['email'],
                u['phone'],
                u['role'],
                u['status'],
                u['date_joined'],
            ])

    # Auto-width columns
    for column in ws.columns:
        max_length = 0
        col_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_length + 4, 40)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────
# Views
# ─────────────────────────────────────────

@login_required
def report_list(request):
    user = request.user

    # Role-based access
    allowed_roles = ['broker', 'admin', 'staff', 'sale_assistant', 'property_owner']
    if user.role not in allowed_roles and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    if user.role == 'sale_assistant':
        reports = Report.objects.filter(generated_by=user)
    elif user.role == 'property_owner':
        reports = Report.objects.filter(generated_by=user)
    else:
        reports = Report.objects.all()

    reports = reports.order_by('-created_at')

    return render(request, 'reports/list.html', {
        'reports': reports,
        'report_type_choices': Report.REPORT_TYPE_CHOICES,
        'total': reports.count(),
        'completed': reports.filter(status='completed').count(),
    })


@login_required
def report_create(request):
    user = request.user

    allowed_roles = ['broker', 'admin', 'staff', 'sale_assistant', 'property_owner']
    if user.role not in allowed_roles and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        format_type = request.POST.get('format', 'pdf')

        # Handle period selection
        from datetime import date
        period_type = request.POST.get('period_type', 'custom')
        date_from = None
        date_to = None
        today = date.today()
        if period_type == 'monthly':
            month_val = request.POST.get('month')
            year_val = request.POST.get('year_monthly')
            month = int(month_val) if month_val and month_val.isdigit() else today.month
            year = int(year_val) if year_val and year_val.isdigit() else today.year
            date_from = date(year, month, 1)
            # Calculate last day of month
            from calendar import monthrange
            last_day = monthrange(year, month)[1]
            date_to = date(year, month, last_day)
        elif period_type == 'quarterly':
            quarter_val = request.POST.get('quarter')
            year_val = request.POST.get('year_quarterly')
            quarter = int(quarter_val) if quarter_val and quarter_val.isdigit() else 1
            year = int(year_val) if year_val and year_val.isdigit() else today.year
            if quarter == 1:
                date_from = date(year, 1, 1)
                date_to = date(year, 3, 31)
            elif quarter == 2:
                date_from = date(year, 4, 1)
                date_to = date(year, 6, 30)
            elif quarter == 3:
                date_from = date(year, 7, 1)
                date_to = date(year, 9, 30)
            elif quarter == 4:
                date_from = date(year, 10, 1)
                date_to = date(year, 12, 31)
        elif period_type == 'semiannual':
            half_val = request.POST.get('half')
            year_val = request.POST.get('year_semiannual')
            half = int(half_val) if half_val and half_val.isdigit() else 1
            year = int(year_val) if year_val and year_val.isdigit() else today.year
            if half == 1:
                date_from = date(year, 1, 1)
                date_to = date(year, 6, 30)
            else:
                date_from = date(year, 7, 1)
                date_to = date(year, 12, 31)
        elif period_type == 'yearly':
            year_val = request.POST.get('year_yearly')
            year = int(year_val) if year_val and year_val.isdigit() else today.year
            date_from = date(year, 1, 1)
            date_to = date(year, 12, 31)
        else:  # custom
            date_from = request.POST.get('date_from') or None
            date_to = request.POST.get('date_to') or None
            # Convert to date if not None
            if date_from:
                date_from = date.fromisoformat(date_from)
            if date_to:
                date_to = date.fromisoformat(date_to)

        # Restrict sale_assistant to their own reports
        if user.role == 'sale_assistant' and report_type not in [
            'commission_report',
        ]:
            messages.error(request, 'You can only generate commission reports.')
            return redirect('reports:create')

        # Restrict property_owner to their own reports
        if user.role == 'property_owner' and report_type not in [
            'sales_by_property',
        ]:
            messages.error(request, 'You can only generate property sales reports.')
            return redirect('reports:create')

        # Restrict to admin/broker/staff
        if user.role not in ['admin', 'broker', 'staff', 'sale_assistant', 'property_owner'] \
                and not user.is_superuser:
            messages.error(request, 'You do not have permission to generate reports.')
            return redirect('reports:list')


        # Get optional property filter for listing_documents and sales_by_agent
        property_id = request.POST.get('property_id') or None
        if property_id:
            property_id = int(property_id)

        # Get optional sale assistant filter for sales_by_agent
        sale_assistant_id = request.POST.get('sale_assistant_id') or None
        if sale_assistant_id:
            sale_assistant_id = int(sale_assistant_id)

        # Get optional listing status filter for total_listings
        listing_status = request.POST.get('listing_status') or None

        # Optional commission user filter
        commission_user_id = request.POST.get('commission_user') or None
        if commission_user_id:
            commission_user_id = int(commission_user_id)

        params = {}
        if property_id:
            params['property_id'] = property_id
        if sale_assistant_id:
            params['sale_assistant_id'] = sale_assistant_id
        if listing_status:
            params['listing_status'] = listing_status
        if commission_user_id:
            params['commission_user'] = commission_user_id
        if period_type:
            params['period_type'] = period_type

        report = Report.objects.create(
            report_type=report_type,
            title=title,
            description=description,
            format=format_type,
            date_from=date_from,
            date_to=date_to,
            generated_by=user,
            status='generating',
            parameters=params,
        )

        # Get data
        data = get_report_data(
            report_type,
            date_from,
            date_to,
            user,
            property_id=property_id,
            listing_status=listing_status,
            sale_assistant_id=sale_assistant_id,
            commission_user_id=commission_user_id,
        )

        try:
            if format_type == 'pdf':
                buffer = generate_pdf_report(report, data)
                filename = f"report_{report.id}.pdf"
                from django.core.files.base import ContentFile
                report.file.save(filename, ContentFile(buffer.read()))

            elif format_type in ['excel', 'csv']:
                buffer = generate_excel_report(report, data)
                filename = f"report_{report.id}.xlsx"
                from django.core.files.base import ContentFile
                report.file.save(filename, ContentFile(buffer.read()))

            report.status = 'completed'
            report.completed_at = timezone.now()
            report.save()

            messages.success(request, f'Report "{title}" generated successfully.')

        except Exception as e:
            report.status = 'failed'
            report.save()
            messages.error(request, f'Report generation failed: {str(e)}')

        return redirect('reports:detail', pk=report.pk)

    # Available report types based on role

    if user.role == 'sale_assistant':
        available_types = [
            ('commission_report', 'My Commission Report'),
        ]
    elif user.role == 'property_owner':
        available_types = [
            ('sales_by_property', 'Property Sales Report'),
        ]
    elif user.role in ['admin', 'broker', 'staff'] or user.is_superuser:
        available_types = [
            ('total_listings', 'Total Listings Overview'),
            ('commission_report', 'Commission Report'),
            ('sales_summary', 'Sales Summary'),
            ('listing_documents', 'Document Tracking Report'),
        ]
    else:
        available_types = []


    # Always provide all properties and sale assistants for filters
    all_properties = Property.objects.filter(listing_status__in=['approved', 'sold', 'reserved']).order_by('title')
    all_sale_assistants = CustomUser.objects.filter(role='sale_assistant', is_active=True).order_by('first_name', 'last_name')

    # Commission roles and users for commission report filter
    commission_users = CustomUser.objects.filter(id__in=Disbursement.objects.values_list('recipient', flat=True).distinct())
    commission_roles = commission_users.values_list('role', flat=True).distinct()
    commission_users_by_role = {}
    for role in commission_roles:
        commission_users_by_role[role] = commission_users.filter(role=role)

    return render(request, 'reports/create.html', {
        'report_type_choices': available_types,
        'format_choices': Report.FORMAT_CHOICES,
        'properties': all_properties,
        'sale_assistants': all_sale_assistants,
        'commission_roles': commission_roles,
        'commission_users_by_role': commission_users_by_role,
    })


@login_required
def report_detail(request, pk):
    report = get_object_or_404(Report, pk=pk)

    # Permission check
    if report.generated_by != request.user and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reports:list')

    # Get preview data
    params = report.parameters or {}
    property_id = request.GET.get('property_id') or params.get('property_id')
    sale_assistant_id = request.GET.get('sale_assistant_id') or params.get('sale_assistant_id')
    commission_user_id = request.GET.get('commission_user') or params.get('commission_user')
    listing_status = params.get('listing_status')

    try:
        property_id = int(property_id) if property_id else None
    except (TypeError, ValueError):
        property_id = None
    try:
        sale_assistant_id = int(sale_assistant_id) if sale_assistant_id else None
    except (TypeError, ValueError):
        sale_assistant_id = None
    try:
        commission_user_id = int(commission_user_id) if commission_user_id else None
    except (TypeError, ValueError):
        commission_user_id = None

    date_from = report.date_from
    date_to = report.date_to
    if request.GET.get('date_from'):
        try:
            from datetime import date
            date_from = date.fromisoformat(request.GET.get('date_from'))
        except (TypeError, ValueError):
            pass
    if request.GET.get('date_to'):
        try:
            from datetime import date
            date_to = date.fromisoformat(request.GET.get('date_to'))
        except (TypeError, ValueError):
            pass

    data = get_report_data(
        report.report_type,
        date_from,
        date_to,
        request.user,
        property_id=property_id,
        listing_status=listing_status,
        sale_assistant_id=sale_assistant_id,
        commission_user_id=commission_user_id,
    )

    # Add filter dropdown context for sales_summary
    context = {
        'report': report,
        'data': data,
    }
    if report.report_type == 'sales_summary':
        context['properties'] = Property.objects.filter(listing_status__in=['approved', 'sold', 'reserved']).order_by('title')
        context['sale_assistants'] = CustomUser.objects.filter(role='sale_assistant', is_active=True).order_by('first_name', 'last_name')
    if report.report_type == 'commission_report':
        context['commission_users'] = CustomUser.objects.filter(
            id__in=Disbursement.objects.values_list('recipient', flat=True).distinct()
        ).order_by('first_name', 'last_name')

    return render(request, 'reports/detail.html', context)


@login_required
def report_download(request, pk):
    report = get_object_or_404(Report, pk=pk)

    if report.generated_by != request.user and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reports:list')

    # Regenerate the report file with current data
    params = report.parameters or {}
    property_id = params.get('property_id')
    sale_assistant_id = params.get('sale_assistant_id')
    commission_user_id = params.get('commission_user')
    listing_status = params.get('listing_status')
    data = get_report_data(
        report.report_type,
        report.date_from,
        report.date_to,
        request.user,
        property_id=property_id,
        listing_status=listing_status,
        sale_assistant_id=sale_assistant_id,
        commission_user_id=commission_user_id,
    )

    try:
        if report.format == 'pdf':
            buffer = generate_pdf_report(report, data)
            response = HttpResponse(buffer.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{report.title}.pdf"'
            return response
        elif report.format in ['excel', 'csv']:
            buffer = generate_excel_report(report, data)
            response = HttpResponse(
                buffer.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{report.title}.xlsx"'
            return response
    except Exception as e:
        messages.error(request, f'Error generating report: {str(e)}')
        return redirect('reports:detail', pk=report.pk)

    # Fallback to saved file
    if not report.file:
        messages.error(request, 'No file available for this report.')
        return redirect('reports:detail', pk=report.pk)

    response = HttpResponse(
        report.file.read(),
        content_type='application/octet-stream'
    )
    response['Content-Disposition'] = f'attachment; filename="{report.file.name}"'
    return response


@login_required
def report_preview(request, pk):
    report = get_object_or_404(Report, pk=pk)
    data = get_report_data(
        report.report_type,
        report.date_from,
        report.date_to,
        request.user
    )
    return render(request, 'reports/preview.html', {
        'report': report,
        'data': data,
    })