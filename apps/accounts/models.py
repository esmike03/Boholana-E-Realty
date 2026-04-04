from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('broker', 'Broker'),
        ('staff', 'Staff'),
        ('property_owner', 'Property Owner'),
        ('sale_assistant', 'Sale Assistant'),
        ('client', 'Client'),
    )

    SOCIAL_PROVIDER_CHOICES = (
        ('none', 'None'),
        ('google', 'Google'),
        ('facebook', 'Facebook'),
    )

    # Role
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')

    # Personal Info
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=(('male', 'Male'), ('female', 'Female'), ('other', 'Other')),
        blank=True, null=True
    )

    # Account Status
    is_verified = models.BooleanField(default=False)
    is_disabled = models.BooleanField(default=False)
    disabled_reason = models.TextField(blank=True, null=True)
    disabled_at = models.DateTimeField(blank=True, null=True)
    disabled_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='disabled_users'
    )

    # Social Login
    social_provider = models.CharField(
        max_length=10,
        choices=SOCIAL_PROVIDER_CHOICES,
        default='none'
    )
    social_uid = models.CharField(max_length=255, blank=True, null=True)

    # Company Info
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    assigned_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_users'
    )
    assigned_at = models.DateTimeField(blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_admin_user(self):
        return self.role == 'admin'

    @property
    def is_broker(self):
        return self.role == 'broker'

    @property
    def is_staff_member(self):
        return self.role == 'staff'

    @property
    def is_property_owner(self):
        return self.role == 'property_owner'

    @property
    def is_sale_assistant(self):
        return self.role == 'sale_assistant'

    @property
    def is_client(self):
        return self.role == 'client'

    @property
    def is_company_user(self):
        return self.role in ['admin', 'broker', 'staff', 'sale_assistant', 'property_owner']

    @property
    def full_name(self):
        return self.get_full_name() or self.username

    def get_initials(self):
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.username[0].upper()


class UserActivityLog(models.Model):
    ACTION_CHOICES = (
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('register', 'Register'),
        ('update_profile', 'Update Profile'),
        ('change_password', 'Change Password'),
        ('role_assigned', 'Role Assigned'),
        ('account_disabled', 'Account Disabled'),
        ('account_enabled', 'Account Enabled'),
    )

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='activity_logs'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    performed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='performed_actions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.get_action_display()}"


class UserPreference(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='preferences'
    )
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
    min_budget = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    max_budget = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    preferred_bedrooms = models.PositiveIntegerField(blank=True, null=True)
    preferred_bathrooms = models.PositiveIntegerField(blank=True, null=True)
    preferred_amenities = models.TextField(blank=True, null=True)
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Preferences of {self.user.username}"
    
class Notification(models.Model):

    TYPE_CHOICES = (
        ('listing_submitted', 'Listing Submitted for Approval'),
        ('listing_approved', 'Listing Approved'),
        ('listing_rejected', 'Listing Rejected'),
        ('listing_flagged', 'Listing Flagged for Review'),
        ('listing_sold', 'Listing Marked as Sold'),
        ('reservation_created', 'New Reservation'),
        ('reservation_approved', 'Reservation Approved'),
        ('reservation_rejected', 'Reservation Rejected'),
        ('reservation_cancelled', 'Reservation Cancelled'),
        ('appointment_created', 'New Appointment Request'),
        ('appointment_confirmed', 'Appointment Confirmed'),
        ('appointment_cancelled', 'Appointment Cancelled'),
        ('sale_created', 'New Sale Created'),
        ('sale_approved', 'Sale Approved'),
        ('sale_verified', 'Sale Verified'),
        ('disbursement_approved', 'Disbursement Approved'),
        ('disbursement_pending', 'Payment Ready for Receipt'),
        ('disbursement_completed', 'Disbursement Completed'),
        ('document_uploaded', 'Document Uploaded'),
        ('document_approved', 'Document Approved'),
        ('document_rejected', 'Document Rejected'),
        ('task_assigned', 'Task Assigned to You'),
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

    recipient = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    sender = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sent_notifications'
    )
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
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
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
            
class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    message = models.TextField()
    property = models.ForeignKey(
        'listings.Property',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='inquiries'
    )
    is_read = models.BooleanField(default=False)
    replied_by = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='replied_inquiries'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} — {self.created_at.strftime('%b %d, %Y')}"