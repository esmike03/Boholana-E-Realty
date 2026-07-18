from django.db import models
from django.conf import settings
from apps.listings.models import Property
from apps.reservations.models import Reservation


class Sale(models.Model):

    PAYMENT_SCHEME_CHOICES = (
        ('spot_cash', 'Spot Cash'),
        ('installment', 'Installment'),
    )

    STATUS_CHOICES = (
        ('pending_verification', 'Pending Verification'),
        ('ready_for_approval', 'Ready for Approval'),
        ('approved', 'Approved'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('defaulted', 'Defaulted'),
    )

    # Relations
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='sales'
    )
    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sale'
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='purchases',
        limit_choices_to={'role': 'client'}
    )
    sale_assistant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assisted_sales',
        limit_choices_to={'role': 'sale_assistant'}
    )
    broker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='brokered_sales',
        limit_choices_to={'role': 'broker'}
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='verified_sales'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_sales'
    )

    # Sale Details
    status = models.CharField(
        max_length=25,
        choices=STATUS_CHOICES,
        default='pending_verification'
    )
    payment_scheme = models.CharField(max_length=25, choices=PAYMENT_SCHEME_CHOICES)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    net_price = models.DecimalField(max_digits=15, decimal_places=2)
    sale_date = models.DateField()
    verified_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Sale #{self.id} - {self.property.title}"

    def save(self, *args, **kwargs):
        self.net_price = self.selling_price - self.discount
        super().save(*args, **kwargs)


class PaymentSchedule(models.Model):

    STATUS_CHOICES = (
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
        ('partial', 'Partial'),
    )

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='payment_schedules'
    )
    due_date = models.DateField()
    amount_due = models.DecimalField(max_digits=15, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='unpaid')
    paid_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['due_date']

    def __str__(self):
        return f"Payment for Sale #{self.sale.id} due {self.due_date}"


class Disbursement(models.Model):

    DISBURSEMENT_TYPE_CHOICES = (
        ('broker_commission', 'Broker Commission'),
        ('sale_assistant_commission', 'Sale Assistant Commission'),
        ('owner_proceeds', 'Owner Proceeds'),
        ('company_share', 'Company Share'),
        ('referral_fee', 'Referral Fee'),
    )

    STATUS_CHOICES = (
        ('in_review', 'In Review'),
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    # Relations
    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='disbursements'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='disbursements'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_disbursements'
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='received_disbursements'
    )

    # Disbursement Details
    disbursement_type = models.CharField(
        max_length=30,
        choices=DISBURSEMENT_TYPE_CHOICES
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='in_review'
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True
    )
    disbursed_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_disbursement_type_display()} - {self.recipient} (Sale #{self.sale.id})"


class SaleTask(models.Model):

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    )

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name='tasks'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_tasks'
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tasks'
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )
    status = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default='pending'
    )
    due_date = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - Sale #{self.sale.id}"