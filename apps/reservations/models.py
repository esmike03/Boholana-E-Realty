from django.db import models
from django.conf import settings
from apps.listings.models import Property


class Appointment(models.Model):

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    )

    # Relations
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='appointments'
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='appointments',
        limit_choices_to={'role': 'client'}
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='handled_appointments'
    )

    # Schedule
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    confirmed_date = models.DateField(null=True, blank=True)
    confirmed_time = models.TimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Appointment #{self.id} - {self.client} on {self.preferred_date}"


class PropertyPreferenceForm(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preference_forms'
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.CASCADE,
        related_name='preference_form',
        null=True, blank=True
    )

    # Preferences
    preferred_property_type = models.CharField(
        max_length=20,
        choices=(
            ('house', 'House'),
            ('lot', 'Lot'),
            ('condo', 'Condominium'),
            ('commercial', 'Commercial'),
            ('apartment', 'Apartment'),
        ),
        blank=True, null=True
    )
    preferred_location = models.CharField(max_length=255, blank=True, null=True)
    min_budget = models.DecimalField(
        max_digits=15, decimal_places=2,
        blank=True, null=True
    )
    max_budget = models.DecimalField(
        max_digits=15, decimal_places=2,
        blank=True, null=True
    )
    preferred_size = models.DecimalField(
        max_digits=10, decimal_places=2,
        blank=True, null=True,
        help_text="in sqm"
    )
    desired_amenities = models.TextField(blank=True, null=True)
    additional_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Preference Form - {self.client.username}"


class Reservation(models.Model):

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('online', 'Online Payment'),
    )

    # Relations
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='reservations'
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
        limit_choices_to={'role': 'client'}
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='handled_reservations'
    )
    appointment = models.OneToOneField(
        Appointment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='reservation'
    )

    # Reservation Details
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    reservation_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    reservation_fee = models.DecimalField(
        max_digits=15, decimal_places=2,
        default=0
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash'
    )
    notes = models.TextField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Reservation #{self.id} - {self.client} on {self.property}"


class ReservationStatusLog(models.Model):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='status_logs'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    remarks = models.TextField(blank=True, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reservation #{self.reservation.id}: {self.old_status} → {self.new_status}"


class ChatMessage(models.Model):
    # Relations
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_messages'
    )
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='chat_messages',
        null=True, blank=True
    )

    # Message
    message = models.TextField()
    is_predefined = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username} → {self.receiver.username}"


class ChatAvailability(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_availability'
    )
    is_available = models.BooleanField(default=True)
    unavailable_message = models.CharField(
        max_length=255,
        default="I am currently unavailable. Please leave a message.",
        blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {'Available' if self.is_available else 'Unavailable'}"