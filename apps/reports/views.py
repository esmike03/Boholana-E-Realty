from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, Sum, Count, Avg
from django.http import HttpResponse
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer, HRFlowable
)
from .models import Report, ReportSchedule
from apps.listings.models import Property
from apps.sales.models import Sale, Disbursement
from apps.reservations.models import Reservation
from apps.documents.models import Document
from apps.accounts.models import CustomUser, ContactMessage


# ─────────────────────────────────────────
# Data Helpers
# ─────────────────────────────────────────

def get_inquiry_data(date_from=None, date_to=None):
    inquiries = ContactMessage.objects.all()
    if date_from:
        inquiries = inquiries.filter(created_at__date__gte=date_from)
    if date_to:
        inquiries = inquiries.filter(created_at__date__lte=date_to)
    return {
        'inquiries': inquiries.order_by('-created_at'),
        'total': inquiries.count(),
        'read': inquiries.filter(is_read=True).count(),
        'unread': inquiries.filter(is_read=False).count(),
        'by_property_type': inquiries.values(
            'property_type'
        ).annotate(count=Count('id')).order_by('-count'),
        'by_preferred_contact': inquiries.values(
            'preferred_contact'
        ).annotate(count=Count('id')).order_by('-count'),
    }


def get_property_data(user=None, date_from=None, date_to=None):
    properties = Property.objects.all()
    if user and user.role == 'property_owner':
        properties = properties.filter(owner=user)
    if date_from:
        properties = properties.filter(created_at__date__gte=date_from)
    if date_to:
        properties = properties.filter(created_at__date__lte=date_to)

    total_value = properties.aggregate(
        total=Sum('price')
    )['total'] or 0
    avg_value = properties.aggregate(
        avg=Avg('price')
    )['avg'] or 0

    return {
        'properties': properties.select_related('owner', 'broker'),
        'total': properties.count(),
        'approved': properties.filter(listing_status='approved').count(),
        'sold': properties.filter(listing_status='sold').count(),
        'pending': properties.filter(listing_status='pending_approval').count(),
        'flagged': properties.filter(listing_status='flagged').count(),
        'archived': properties.filter(listing_status='archived').count(),
        'total_value': total_value,
        'avg_value': avg_value,
        'projected_value': properties.filter(
            listing_status='approved'
        ).aggregate(total=Sum('price'))['total'] or 0,
        'by_type': properties.values(
            'property_type'
        ).annotate(
            count=Count('id'),
            total_value=Sum('price')
        ).order_by('-count'),
    }


def get_sales_data(user=None, date_from=None, date_to=None):
    sales = Sale.objects.all()
    if user and user.role == 'sale_assistant':
        sales = sales.filter(sale_assistant=user)
    if user and user.role == 'property_owner':
        sales = sales.filter(property__owner=user)
    if date_from:
        sales = sales.filter(sale_date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__lte=date_to)

    total_revenue = sales.aggregate(
        total=Sum('net_price')
    )['total'] or 0
    avg_sale = sales.aggregate(
        avg=Avg('net_price')
    )['avg'] or 0

    # Projected (approved but not yet completed)
    projected = sales.filter(
        status__in=['approved', 'ready_for_approval']
    ).aggregate(total=Sum('net_price'))['total'] or 0

    # Commissions
    total_commission = Disbursement.objects.filter(
        sale__in=sales,
        disbursement_type__in=[
            'sale_assistant_commission', 'broker_commission'
        ],
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or 0

    return {
        'sales': sales.select_related('property', 'client', 'sale_assistant'),
        'total': sales.count(),
        'total_revenue': total_revenue,
        'avg_sale': avg_sale,
        'projected': projected,
        'total_commission': total_commission,
        'completed': sales.filter(status='completed').count(),
        'pending': sales.filter(status='pending_verification').count(),
        'approved': sales.filter(status='approved').count(),
        'cancelled': sales.filter(status='cancelled').count(),
        'by_payment_scheme': sales.values(
            'payment_scheme'
        ).annotate(
            count=Count('id'),
            total=Sum('net_price')
        ).order_by('-total'),
    }


def get_overview_data():
    """System-wide overview for total listings report"""
    total_property_value = Property.objects.aggregate(
        total=Sum('price')
    )['total'] or 0

    approved_value = Property.objects.filter(
        listing_status='approved'
    ).aggregate(total=Sum('price'))['total'] or 0

    return {
        'total_properties': Property.objects.count(),
        'approved': Property.objects.filter(
            listing_status='approved'
        ).count(),
        'sold': Property.objects.filter(
            listing_status='sold'
        ).count(),
        'pending': Property.objects.filter(
            listing_status='pending_approval'
        ).count(),
        'total_users': CustomUser.objects.count(),
        'total_clients': CustomUser.objects.filter(
            role='client'
        ).count(),
        'total_sales': Sale.objects.count(),
        'total_revenue': Sale.objects.aggregate(
            total=Sum('net_price')
        )['total'] or 0,
        'total_reservations': Reservation.objects.count(),
        'total_inquiries': ContactMessage.objects.count(),
        'unread_inquiries': ContactMessage.objects.filter(
            is_read=False
        ).count(),
        'total_property_value': total_property_value,
        'approved_value': approved_value,
        'projected_revenue': Sale.objects.filter(
            status__in=['approved', 'ready_for_approval']
        ).aggregate(total=Sum('net_price'))['total'] or 0,
    }


def get_report_data(report_type, date_from=None, date_to=None, user=None):
    if report_type == 'total_inquiries':
        return get_inquiry_data(date_from, date_to)
    elif report_type == 'property_inventory':
        return get_property_data(user, date_from, date_to)
    elif report_type == 'active_properties':
        data = get_property_data(user, date_from, date_to)
        data['properties'] = data['properties'].filter(
            listing_status='approved'
        )
        return data
    elif report_type == 'sales_summary':
        return get_sales_data(user, date_from, date_to)
    elif report_type == 'total_listings':
        return get_overview_data()
    elif report_type == 'commission_report':
        disbursements = Disbursement.objects.all()
        if user and user.role == 'sale_assistant':
            disbursements = disbursements.filter(recipient=user)
        if date_from:
            disbursements = disbursements.filter(
                created_at__date__gte=date_from
            )
        if date_to:
            disbursements = disbursements.filter(
                created_at__date__lte=date_to
            )
        return {
            'disbursements': disbursements.select_related(
                'sale', 'recipient'
            ),
            'total_disbursed': disbursements.filter(
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'pending_amount': disbursements.filter(
                status='pending'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'in_review': disbursements.filter(
                status='in_review'
            ).aggregate(total=Sum('amount'))['total'] or 0,
        }
    elif report_type == 'reservation_summary':
        reservations = Reservation.objects.all()
        if date_from:
            reservations = reservations.filter(
                reservation_date__gte=date_from
            )
        if date_to:
            reservations = reservations.filter(
                reservation_date__lte=date_to
            )
        return {
            'reservations': reservations.select_related(
                'property', 'client'
            ),
            'total': reservations.count(),
            'approved': reservations.filter(status='approved').count(),
            'pending': reservations.filter(status='pending').count(),
            'cancelled': reservations.filter(status='cancelled').count(),
        }
    elif report_type == 'sales_by_agent':
        sale_assistants = CustomUser.objects.filter(
            role='sale_assistant'
        )
        agent_data = []
        for sa in sale_assistants:
            sa_sales = Sale.objects.filter(sale_assistant=sa)
            if date_from:
                sa_sales = sa_sales.filter(sale_date__gte=date_from)
            if date_to:
                sa_sales = sa_sales.filter(sale_date__lte=date_to)
            commission = Disbursement.objects.filter(
                recipient=sa,
                disbursement_type='sale_assistant_commission',
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            agent_data.append({
                'agent': sa,
                'total_sales': sa_sales.count(),
                'total_revenue': sa_sales.aggregate(
                    total=Sum('net_price')
                )['total'] or 0,
                'total_commission': commission,
            })
        return {'agent_data': agent_data}
    return {}


# ─────────────────────────────────────────
# PDF Generator
# ─────────────────────────────────────────

def generate_pdf_report(report, data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=40, leftMargin=40,
        topMargin=40, bottomMargin=40
    )
    styles = getSampleStyleSheet()
    elements = []

    # Header style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=18,
        textColor=colors.HexColor('#0f2942'),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#6b7280'),
        spaceAfter=2,
    )

    # Title
    elements.append(Paragraph('Boholana E-Realty', title_style))
    elements.append(Paragraph(
        report.get_report_type_display(),
        subtitle_style
    ))

    date_range = f"Period: {report.date_from} — {report.date_to}" \
        if report.date_from else "All Time"
    elements.append(Paragraph(date_range, subtitle_style))
    elements.append(Paragraph(
        f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}",
        subtitle_style
    ))
    elements.append(HRFlowable(
        width="100%", thickness=2,
        color=colors.HexColor('#f0a500'),
        spaceAfter=16
    ))

    # Header style for tables
    header_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0f2942')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [
            colors.white, colors.HexColor('#f9fafb')
        ]),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
    ])

    # ── Inquiry Report ──
    if report.report_type == 'total_inquiries':
        # Summary
        summary = [
            ['Total Inquiries', 'Read', 'Unread'],
            [
                str(data.get('total', 0)),
                str(data.get('read', 0)),
                str(data.get('unread', 0)),
            ]
        ]
        t = Table(summary, colWidths=[180, 180, 180])
        t.setStyle(header_style)
        elements.append(t)
        elements.append(Spacer(1, 16))

        # Inquiry list
        elements.append(Paragraph(
            'Inquiry List',
            ParagraphStyle('H2', fontSize=12, textColor=colors.HexColor('#0f2942'), spaceAfter=8)
        ))
        table_data = [[
            '#', 'Name', 'Email', 'Phone',
            'Property Type', 'City', 'Preferred Contact', 'Date'
        ]]
        for i, inq in enumerate(data.get('inquiries', [])[:100], 1):
            table_data.append([
                str(i),
                inq.name[:20],
                inq.email or '—',
                inq.phone or '—',
                inq.get_property_type_display() if inq.property_type else '—',
                inq.city or '—',
                inq.get_preferred_contact_display() if inq.preferred_contact else '—',
                inq.created_at.strftime('%b %d, %Y'),
            ])
        t2 = Table(table_data, colWidths=[20, 90, 110, 80, 80, 80, 90, 80])
        t2.setStyle(header_style)
        elements.append(t2)

    # ── Property Report ──
    elif report.report_type in ['property_inventory', 'active_properties']:
        summary = [
            ['Total', 'Approved', 'Sold', 'Pending', 'Total Value', 'Projected Value'],
            [
                str(data.get('total', 0)),
                str(data.get('approved', 0)),
                str(data.get('sold', 0)),
                str(data.get('pending', 0)),
                f"₱{data.get('total_value', 0):,.2f}",
                f"₱{data.get('projected_value', 0):,.2f}",
            ]
        ]
        t = Table(summary, colWidths=[80, 80, 80, 80, 140, 140])
        t.setStyle(header_style)
        elements.append(t)
        elements.append(Spacer(1, 16))

        table_data = [['#', 'Property', 'Type', 'City', 'Price', 'Status', 'Owner']]
        for i, prop in enumerate(data.get('properties', [])[:100], 1):
            table_data.append([
                str(i),
                prop.title[:30],
                prop.get_property_type_display(),
                prop.city,
                f"₱{prop.price:,.0f}",
                prop.get_listing_status_display(),
                prop.owner.get_full_name()[:20],
            ])
        t2 = Table(table_data, colWidths=[25, 150, 80, 90, 90, 80, 100])
        t2.setStyle(header_style)
        elements.append(t2)

    # ── Sales Report ──
    elif report.report_type == 'sales_summary':
        summary = [
            ['Total Sales', 'Revenue', 'Avg Sale', 'Projected', 'Commission', 'Completed'],
            [
                str(data.get('total', 0)),
                f"₱{data.get('total_revenue', 0):,.2f}",
                f"₱{data.get('avg_sale', 0):,.2f}",
                f"₱{data.get('projected', 0):,.2f}",
                f"₱{data.get('total_commission', 0):,.2f}",
                str(data.get('completed', 0)),
            ]
        ]
        t = Table(summary, colWidths=[80, 110, 110, 110, 110, 80])
        t.setStyle(header_style)
        elements.append(t)
        elements.append(Spacer(1, 16))

        table_data = [[
            '#', 'Property', 'Client', 'Sale Assistant',
            'Net Price', 'Payment', 'Status', 'Date'
        ]]
        for i, sale in enumerate(data.get('sales', [])[:100], 1):
            table_data.append([
                str(i),
                sale.property.title[:25],
                sale.client.get_full_name()[:20],
                sale.sale_assistant.get_full_name()[:20]
                    if sale.sale_assistant else '—',
                f"₱{sale.net_price:,.2f}",
                sale.get_payment_scheme_display(),
                sale.get_status_display(),
                str(sale.sale_date),
            ])
        t2 = Table(table_data, colWidths=[20, 120, 100, 100, 90, 70, 80, 75])
        t2.setStyle(header_style)
        elements.append(t2)

    # ── Overview Report ──
    elif report.report_type == 'total_listings':
        overview = [
            ['Metric', 'Value'],
            ['Total Properties', str(data.get('total_properties', 0))],
            ['Approved / For Sale', str(data.get('approved', 0))],
            ['Sold Properties', str(data.get('sold', 0))],
            ['Total Property Value', f"₱{data.get('total_property_value', 0):,.2f}"],
            ['Approved Property Value', f"₱{data.get('approved_value', 0):,.2f}"],
            ['Projected Revenue', f"₱{data.get('projected_revenue', 0):,.2f}"],
            ['Total Sales', str(data.get('total_sales', 0))],
            ['Total Revenue', f"₱{data.get('total_revenue', 0):,.2f}"],
            ['Total Reservations', str(data.get('total_reservations', 0))],
            ['Total Inquiries', str(data.get('total_inquiries', 0))],
            ['Unread Inquiries', str(data.get('unread_inquiries', 0))],
            ['Total Users', str(data.get('total_users', 0))],
            ['Total Clients', str(data.get('total_clients', 0))],
        ]
        t = Table(overview, colWidths=[250, 250])
        t.setStyle(header_style)
        elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ─────────────────────────────────────────
# Excel Generator
# ─────────────────────────────────────────

def generate_excel_report(report, data):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = report.get_report_type_display()[:30]

    # Styles
    header_fill = PatternFill('solid', fgColor='0F2942')
    header_font = Font(color='FFFFFF', bold=True, size=10)
    gold_fill = PatternFill('solid', fgColor='F0A500')
    gold_font = Font(color='0F2942', bold=True, size=14)
    label_font = Font(bold=True, size=10)
    alt_fill = PatternFill('solid', fgColor='F9FAFB')
    border = Border(
        left=Side(style='thin', color='E5E7EB'),
        right=Side(style='thin', color='E5E7EB'),
        top=Side(style='thin', color='E5E7EB'),
        bottom=Side(style='thin', color='E5E7EB'),
    )

    def style_header_row(ws, row_num, col_count):
        for col in range(1, col_count + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(
                horizontal='left', vertical='center'
            )

    def style_data_row(ws, row_num, col_count, alt=False):
        for col in range(1, col_count + 1):
            cell = ws.cell(row=row_num, column=col)
            cell.border = border
            cell.alignment = Alignment(vertical='center')
            if alt:
                cell.fill = alt_fill

    # Title
    ws['A1'] = 'Boholana E-Realty'
    ws['A1'].font = gold_font
    ws['A1'].fill = PatternFill('solid', fgColor='0F2942')
    ws['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[1].height = 30

    ws['A2'] = report.get_report_type_display()
    ws['A2'].font = Font(bold=True, size=12, color='0F2942')

    date_range = f"Period: {report.date_from} — {report.date_to}" \
        if report.date_from else "All Time"
    ws['A3'] = date_range
    ws['A3'].font = Font(size=9, color='6B7280')

    ws['A4'] = f"Generated: {timezone.now().strftime('%B %d, %Y %I:%M %p')}"
    ws['A4'].font = Font(size=9, color='6B7280')
    ws.append([])

    # ── Inquiry Report ──
    if report.report_type == 'total_inquiries':
        # Summary
        ws.append(['SUMMARY'])
        ws[ws.max_row][0].font = label_font
        ws.append(['Total Inquiries', 'Read', 'Unread'])
        style_header_row(ws, ws.max_row, 3)
        ws.append([
            data.get('total', 0),
            data.get('read', 0),
            data.get('unread', 0),
        ])
        style_data_row(ws, ws.max_row, 3)
        ws.append([])

        # By property type
        ws.append(['BY PROPERTY TYPE'])
        ws[ws.max_row][0].font = label_font
        ws.append(['Property Type', 'Count'])
        style_header_row(ws, ws.max_row, 2)
        for item in data.get('by_property_type', []):
            ws.append([
                item['property_type'] or 'Not Specified',
                item['count']
            ])
        ws.append([])

        # Full inquiry list
        ws.append(['INQUIRY LIST'])
        ws[ws.max_row][0].font = label_font
        headers = [
            '#', 'Name', 'Email', 'Phone',
            'Property Type', 'Listing Type',
            'City', 'Preferred Contact', 'Message', 'Date'
        ]
        ws.append(headers)
        style_header_row(ws, ws.max_row, len(headers))

        for i, inq in enumerate(data.get('inquiries', []), 1):
            ws.append([
                i,
                inq.name,
                inq.email or '—',
                inq.phone or '—',
                inq.get_property_type_display()
                    if inq.property_type else '—',
                inq.get_listing_type_display()
                    if inq.listing_type else '—',
                inq.city or '—',
                inq.get_preferred_contact_display()
                    if inq.preferred_contact else '—',
                inq.message[:100],
                inq.created_at.strftime('%b %d, %Y %I:%M %p'),
            ])
            style_data_row(ws, ws.max_row, len(headers), alt=(i % 2 == 0))

    # ── Property Report ──
    elif report.report_type in ['property_inventory', 'active_properties']:
        ws.append(['SUMMARY'])
        ws[ws.max_row][0].font = label_font
        headers = [
            'Total', 'Approved', 'Sold',
            'Pending', 'Total Value', 'Projected Value', 'Avg Value'
        ]
        ws.append(headers)
        style_header_row(ws, ws.max_row, len(headers))
        ws.append([
            data.get('total', 0),
            data.get('approved', 0),
            data.get('sold', 0),
            data.get('pending', 0),
            float(data.get('total_value', 0)),
            float(data.get('projected_value', 0)),
            float(data.get('avg_value', 0)),
        ])
        style_data_row(ws, ws.max_row, len(headers))
        ws.append([])

        ws.append(['PROPERTY LIST'])
        ws[ws.max_row][0].font = label_font
        headers2 = [
            '#', 'Title', 'Type', 'City', 'Province',
            'Price', 'Status', 'Owner', 'Date Listed'
        ]
        ws.append(headers2)
        style_header_row(ws, ws.max_row, len(headers2))
        for i, prop in enumerate(data.get('properties', []), 1):
            ws.append([
                i,
                prop.title,
                prop.get_property_type_display(),
                prop.city,
                prop.province,
                float(prop.price),
                prop.get_listing_status_display(),
                prop.owner.get_full_name(),
                prop.created_at.strftime('%b %d, %Y'),
            ])
            style_data_row(
                ws, ws.max_row, len(headers2), alt=(i % 2 == 0)
            )

    # ── Sales Report ──
    elif report.report_type == 'sales_summary':
        ws.append(['SALES SUMMARY'])
        ws[ws.max_row][0].font = label_font
        headers = [
            'Total Sales', 'Total Revenue', 'Avg Sale Value',
            'Projected Revenue', 'Total Commission', 'Completed'
        ]
        ws.append(headers)
        style_header_row(ws, ws.max_row, len(headers))
        ws.append([
            data.get('total', 0),
            float(data.get('total_revenue', 0)),
            float(data.get('avg_sale', 0)),
            float(data.get('projected', 0)),
            float(data.get('total_commission', 0)),
            data.get('completed', 0),
        ])
        style_data_row(ws, ws.max_row, len(headers))
        ws.append([])

        ws.append(['SALES LIST'])
        ws[ws.max_row][0].font = label_font
        headers2 = [
            '#', 'Property', 'Client', 'Sale Assistant', 'Broker',
            'Selling Price', 'Discount', 'Net Price',
            'Payment Scheme', 'Status', 'Date'
        ]
        ws.append(headers2)
        style_header_row(ws, ws.max_row, len(headers2))
        for i, sale in enumerate(data.get('sales', []), 1):
            ws.append([
                i,
                sale.property.title,
                sale.client.get_full_name(),
                sale.sale_assistant.get_full_name()
                    if sale.sale_assistant else '—',
                sale.broker.get_full_name() if sale.broker else '—',
                float(sale.selling_price),
                float(sale.discount),
                float(sale.net_price),
                sale.get_payment_scheme_display(),
                sale.get_status_display(),
                str(sale.sale_date),
            ])
            style_data_row(
                ws, ws.max_row, len(headers2), alt=(i % 2 == 0)
            )

    # ── Overview ──
    elif report.report_type == 'total_listings':
        ws.append(['SYSTEM OVERVIEW'])
        ws[ws.max_row][0].font = label_font
        overview_items = [
            ('Total Properties', data.get('total_properties', 0)),
            ('Approved / For Sale', data.get('approved', 0)),
            ('Sold Properties', data.get('sold', 0)),
            ('Total Property Value', float(data.get('total_property_value', 0))),
            ('Approved Property Value', float(data.get('approved_value', 0))),
            ('Projected Revenue', float(data.get('projected_revenue', 0))),
            ('Total Sales', data.get('total_sales', 0)),
            ('Total Revenue', float(data.get('total_revenue', 0))),
            ('Total Reservations', data.get('total_reservations', 0)),
            ('Total Inquiries', data.get('total_inquiries', 0)),
            ('Unread Inquiries', data.get('unread_inquiries', 0)),
            ('Total Users', data.get('total_users', 0)),
            ('Total Clients', data.get('total_clients', 0)),
        ]
        ws.append(['Metric', 'Value'])
        style_header_row(ws, ws.max_row, 2)
        for i, (label, value) in enumerate(overview_items):
            ws.append([label, value])
            style_data_row(ws, ws.max_row, 2, alt=(i % 2 == 0))

    # Auto-width
    for column in ws.columns:
        max_length = 0
        col_letter = column[0].column_letter
        for cell in column:
            try:
                if cell.value and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(
            max_length + 4, 45
        )

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
    allowed = ['broker', 'admin', 'property_owner', 'sale_assistant']
    if user.role not in allowed and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    if user.role in ['sale_assistant', 'property_owner']:
        reports = Report.objects.filter(generated_by=user)
    else:
        reports = Report.objects.all()

    reports = reports.order_by('-created_at')
    return render(request, 'reports/list.html', {
        'reports': reports,
        'total': reports.count(),
        'completed': reports.filter(status='completed').count(),
    })


@login_required
def report_create(request):
    user = request.user
    allowed = ['broker', 'admin', 'property_owner', 'sale_assistant']
    if user.role not in allowed and not user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('dashboard')

    # Role-based available types
    if user.role == 'admin':
        available_types = [
            ('active_properties', 'Active Properties'),
            ('sales_summary', 'Sales Report'),
            ('total_inquiries', 'Total Inquiries'),
            ('total_listings', 'Total Listings Overview'),
            ('reservation_summary', 'Reservation Summary'),
        ]
    elif user.role == 'broker':
        available_types = [
            ('active_properties', 'Active Properties'),
            ('commission_report', 'Commission Report'),
            ('sales_summary', 'Sales Report'),
            ('total_inquiries', 'Total Inquiries'),
            ('total_listings', 'Total Listings Overview'),
            ('property_inventory', 'Property Inventory'),
            ('reservation_summary', 'Reservation Summary'),
            ('sales_by_agent', 'Sales by Agent'),
        ]
    elif user.role == 'property_owner':
        available_types = [
            ('sales_summary', 'Sales Report'),
            ('property_inventory', 'My Property Inventory'),
            ('total_inquiries', 'Total Inquiries'),
            ('total_listings', 'Total Listings Overview'),
        ]
    elif user.role == 'sale_assistant':
        available_types = [
            ('active_properties', 'Active Properties'),
            ('commission_report', 'My Commission Report'),
            ('sales_summary', 'Sales Report'),
            ('total_inquiries', 'Total Inquiries'),
            ('total_listings', 'Total Listings Overview'),
        ]
    else:
        available_types = []

    if request.method == 'POST':
        report_type = request.POST.get('report_type')
        title = request.POST.get('title')
        format_type = request.POST.get('format', 'pdf')
        date_from = request.POST.get('date_from') or None
        date_to = request.POST.get('date_to') or None

        report = Report.objects.create(
            report_type=report_type,
            title=title,
            format=format_type,
            date_from=date_from,
            date_to=date_to,
            generated_by=user,
            status='generating',
        )

        data = get_report_data(report_type, date_from, date_to, user)

        try:
            if format_type == 'pdf':
                buffer = generate_pdf_report(report, data)
                filename = f"report_{report.id}.pdf"
            else:
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

    return render(request, 'reports/create.html', {
        'report_type_choices': available_types,
        'format_choices': Report.FORMAT_CHOICES,
    })


@login_required
def report_detail(request, pk):
    report = get_object_or_404(Report, pk=pk)

    if report.generated_by != request.user and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reports:list')

    data = get_report_data(
        report.report_type,
        report.date_from,
        report.date_to,
        request.user
    )
    return render(request, 'reports/detail.html', {
        'report': report,
        'data': data,
    })


@login_required
def report_download(request, pk):
    report = get_object_or_404(Report, pk=pk)

    if report.generated_by != request.user and \
            request.user.role not in ['broker', 'admin'] and \
            not request.user.is_superuser:
        messages.error(request, 'You do not have permission.')
        return redirect('reports:list')

    if not report.file:
        messages.error(request, 'No file available.')
        return redirect('reports:detail', pk=report.pk)

    ext = 'pdf' if report.format == 'pdf' else 'xlsx'
    content_type = 'application/pdf' if report.format == 'pdf' \
        else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    response = HttpResponse(report.file.read(), content_type=content_type)
    response['Content-Disposition'] = \
        f'attachment; filename="boholana_report_{report.id}.{ext}"'
    return response