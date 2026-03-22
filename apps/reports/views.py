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
from apps.accounts.models import CustomUser


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def get_report_data(report_type, date_from=None, date_to=None, user=None):
    data = {}

    if report_type == 'sales_summary':
        sales = Sale.objects.all()
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
        if user and user.role == 'sale_assistant':
            sales = sales.filter(sale_assistant=user)
        data = {
            'sales': sales.select_related('property', 'client'),
            'total_sales': sales.count(),
            'total_revenue': sales.aggregate(
                total=Sum('net_price')
            )['total'] or 0,
            'completed': sales.filter(status='completed').count(),
            'pending': sales.filter(status='pending_verification').count(),
        }

    elif report_type == 'commission_report':
        disbursements = Disbursement.objects.all()
        if date_from:
            disbursements = disbursements.filter(created_at__date__gte=date_from)
        if date_to:
            disbursements = disbursements.filter(created_at__date__lte=date_to)
        if user and user.role == 'sale_assistant':
            disbursements = disbursements.filter(recipient=user)
        data = {
            'disbursements': disbursements.select_related('sale', 'recipient'),
            'total_disbursed': disbursements.filter(
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'pending_amount': disbursements.filter(
                status='pending'
            ).aggregate(total=Sum('amount'))['total'] or 0,
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
        data = {
            'total_properties': Property.objects.count(),
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
        }

    elif report_type == 'sales_by_agent':
        sale_assistants = CustomUser.objects.filter(role='sale_assistant')
        agent_data = []
        for sa in sale_assistants:
            sa_sales = Sale.objects.filter(sale_assistant=sa)
            total_commission = Disbursement.objects.filter(
                recipient=sa,
                disbursement_type='sale_assistant_commission'
            ).aggregate(total=Sum('amount'))['total'] or 0
            agent_data.append({
                'agent': sa,
                'total_sales': sa_sales.count(),
                'total_revenue': sa_sales.aggregate(
                    total=Sum('net_price')
                )['total'] or 0,
                'total_commission': total_commission,
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

    elif report.report_type == 'total_listings':
        overview_data = [
            ['Overview', 'Count/Value'],
            ['Total Properties', str(data.get('total_properties', 0))],
            ['Approved Listings', str(data.get('approved', 0))],
            ['Sold Properties', str(data.get('sold', 0))],
            ['Pending Approval', str(data.get('pending', 0))],
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
                   'Total Revenue', 'Total Commission']
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
        date_from = request.POST.get('date_from') or None
        date_to = request.POST.get('date_to') or None

        # Restrict sale_assistant to their own reports
        if user.role == 'sale_assistant' and report_type not in [
            'commission_report', 'sales_summary'
        ]:
            messages.error(request, 'You can only generate commission and sales reports.')
            return redirect('reports:create')

        if user.role == 'property_owner' and report_type not in [
            'property_inventory', 'sales_summary'
        ]:
            messages.error(request, 'You can only generate property reports.')
            return redirect('reports:create')

        report = Report.objects.create(
            report_type=report_type,
            title=title,
            description=description,
            format=format_type,
            date_from=date_from,
            date_to=date_to,
            generated_by=user,
            status='generating',
        )

        # Get data
        data = get_report_data(report_type, date_from, date_to, user)

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
            ('commission_report', 'Commission Report'),
            ('sales_summary', 'Sales Summary Report'),
        ]
    elif user.role == 'property_owner':
        available_types = [
            ('property_inventory', 'Property Inventory Report'),
            ('sales_summary', 'Sales Summary Report'),
        ]
    else:
        available_types = Report.REPORT_TYPE_CHOICES

    return render(request, 'reports/create.html', {
        'report_type_choices': available_types,
        'format_choices': Report.FORMAT_CHOICES,
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