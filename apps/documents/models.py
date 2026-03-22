from django.db import models
from django.conf import settings
from apps.listings.models import Property
from apps.sales.models import Sale
from apps.reservations.models import Reservation


class Document(models.Model):

    DOCUMENT_TYPE_CHOICES = (
        ('title', 'Transfer Certificate of Title (TCT)'),
        ('tax_declaration', 'Tax Declaration'),
        ('deed_of_sale', 'Deed of Sale'),
        ('contract_to_sell', 'Contract to Sell'),
        ('special_power_of_attorney', 'Special Power of Attorney'),
        ('reservation_agreement', 'Reservation Agreement'),
        ('payment_receipt', 'Payment Receipt'),
        ('official_receipt', 'Official Receipt'),
        ('acknowledgement_receipt', 'Acknowledgement Receipt'),
        ('valid_id', 'Valid ID'),
        ('proof_of_income', 'Proof of Income'),
        ('bank_statement', 'Bank Statement'),
        ('marriage_certificate', 'Marriage Certificate'),
        ('birth_certificate', 'Birth Certificate'),
        ('other', 'Other'),
    )

    STATUS_CHOICES = (
        ('pending_approval', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    FILE_FORMAT_CHOICES = (
        ('pdf', 'PDF'),
        ('word', 'Word Document'),
        ('image', 'Image'),
        ('other', 'Other'),
    )

    # Relations
    property = models.ForeignKey(
        Property,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents'
    )
    sale = models.ForeignKey(
        Sale,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents'
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents'
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_documents'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reviewed_documents'
    )

    # Document Details
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/%Y/%m/')
    file_format = models.CharField(
        max_length=10,
        choices=FILE_FORMAT_CHOICES,
        default='pdf'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending_approval'
    )
    rejection_feedback = models.TextField(blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    expiry_date = models.DateField(null=True, blank=True)
    is_confidential = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.title}"


class DocumentAuditLog(models.Model):

    ACTION_CHOICES = (
        ('uploaded', 'Uploaded'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
        ('viewed', 'Viewed'),
    )

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-performed_at']

    def __str__(self):
        return f"{self.document.title} — {self.get_action_display()}"


class DocumentChecklist(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='document_checklists'
    )
    document_type = models.CharField(
        max_length=30,
        choices=Document.DOCUMENT_TYPE_CHOICES
    )
    is_required = models.BooleanField(default=True)
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.get_document_type_display()} - Sale #{self.sale.id}"