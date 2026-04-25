from django.db import models
from django.conf import settings


class Report(models.Model):

    REPORT_TYPE_CHOICES = (
        ('sales_summary', 'Sales Summary Report'),
        ('sales_by_property', 'Sales by Property Report'),
        # ('sales_by_agent', 'Sales by Agent/Sale Assistant Report'),  # Removed for merged report
        ('monthly_sales', 'Monthly Sales Report'),
        ('reservation_summary', 'Reservation Summary Report'),
        ('property_inventory', 'Property Inventory Report'),
        ('property_status', 'Property Status Report'),
        ('disbursement_summary', 'Disbursement Summary Report'),
        ('commission_report', 'Commission Report'),
        ('payment_collection', 'Payment Collection Report'),
        ('document_status', 'Document Status Report'),
        ('listing_documents', 'Listing Documents Report'),
        ('total_listings', 'Total Listings Overview'),
        ('total_inquiries', 'Total Inquiries Report'),
        ('user_summary', 'User Summary Report'),
        ('custom', 'Custom Report'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    FORMAT_CHOICES = (
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
    )

    # Relations
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_reports'
    )

    # Report Details
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        default='pdf'
    )
    file = models.FileField(
        upload_to='reports/%Y/%m/',
        null=True, blank=True
    )
    parameters = models.JSONField(default=dict, blank=True)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)

    # Turnaround tracking
    turnaround_days = models.PositiveIntegerField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_report_type_display()} - {self.created_at.strftime('%Y-%m-%d')}"


class ReportSchedule(models.Model):

    FREQUENCY_CHOICES = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('annually', 'Annually'),
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scheduled_reports'
    )
    report_type = models.CharField(
        max_length=30,
        choices=Report.REPORT_TYPE_CHOICES
    )
    title = models.CharField(max_length=255)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    format = models.CharField(
        max_length=10,
        choices=Report.FORMAT_CHOICES,
        default='pdf'
    )
    parameters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='report_subscriptions',
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.get_frequency_display()})"