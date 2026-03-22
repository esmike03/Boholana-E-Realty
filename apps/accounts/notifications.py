from django.db import models
from django.conf import settings


class Notification(models.Model):

    TYPE_CHOICES = (
        # Listings
        ('listing_submitted', 'Listing Submitted for Approval'),
        ('listing_approved', 'Listing Approved'),
        ('listing_rejected', 'Listing Rejected'),
        ('listing_flagged', 'Listing Flagged for Review'),
        ('listing_sold', 'Listing Marked as Sold'),

        # Reservations
        ('reservation_created', 'New Reservation'),
        ('reservation_approved', 'Reservation Approved'),
        ('reservation_rejected', 'Reservation Rejected'),
        ('reservation_cancelled', 'Reservation Cancelled'),

        # Appointments
        ('appointment_created', 'New Appointment Request'),
        ('appointment_confirmed', 'Appointment Confirmed'),
        ('appointment_cancelled', 'Appointment Cancelled'),

        # Sales
        ('sale_created', 'New Sale Created'),
        ('sale_approved', 'Sale Approved'),
        ('sale_verified', 'Sale Verified'),

        # Disbursements
        ('disbursement_approved', 'Disbursement Approved'),
        ('disbursement_pending', 'Payment Ready for Receipt'),
        ('disbursement_completed', 'Disbursement Completed'),

        # Documents
        ('document_uploaded', 'Document Uploaded'),
        ('document_approved', 'Document Approved'),
        ('document_rejected', 'Document Rejected'),

        # Tasks
        ('task_assigned', 'Task Assigned to You'),

        # System
        ('account_disabled', 'Account Disabled'),
        ('account_enabled', 'Account Enabled'),
        ('role_assigned', 'Role Assigned'),
        ('general', 'General Notification'),
    )

    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )

    # Relations
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_notifications'
    )

    # Content
    notification_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default='general'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='medium'
    )

    # Link (optional — where to redirect when clicked)
    link = models.CharField(max_length=500, blank=True, null=True)

    # Status
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient.username} — {self.title}"

    def mark_as_read(self):
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()