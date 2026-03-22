from django.db import models
from django.conf import settings


class PropertyTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Property(models.Model):

    PROPERTY_TYPE_CHOICES = (
        ('house', 'House'),
        ('lot', 'Lot'),
        ('condo', 'Condominium'),
        ('commercial', 'Commercial'),
        ('apartment', 'Apartment'),
        ('warehouse', 'Warehouse'),
    )

    LISTING_STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('flagged', 'Flagged for Review'),
        ('approved', 'Approved / For Sale'),
        ('rejected', 'Rejected'),
        ('sold', 'Sold'),
        ('archived', 'Archived'),
    )

    LISTING_TYPE_CHOICES = (
        ('sale', 'For Sale'),
    )

    # Basic Info
    title = models.CharField(max_length=255)
    description = models.TextField()
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES)
    listing_type = models.CharField(
        max_length=10,
        choices=LISTING_TYPE_CHOICES,
        default='sale'
    )
    listing_status = models.CharField(
        max_length=20,
        choices=LISTING_STATUS_CHOICES,
        default='draft'
    )

    # Ownership
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='properties',
        limit_choices_to={'role': 'property_owner'}
    )
    broker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='brokered_properties',
        limit_choices_to={'role': 'broker'}
    )

    # Approval Workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_properties'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.TextField(blank=True, null=True)
    flagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='flagged_properties'
    )
    flagged_reason = models.TextField(blank=True, null=True)
    flagged_at = models.DateTimeField(null=True, blank=True)

    # Location
    address = models.TextField()
    city = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=10)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6,
        null=True, blank=True
    )

    # Property Details
    lot_area = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="in sqm"
    )
    floor_area = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        help_text="in sqm"
    )
    bedrooms = models.PositiveIntegerField(default=0)
    bathrooms = models.PositiveIntegerField(default=0)
    garage = models.PositiveIntegerField(default=0)
    amenities = models.TextField(blank=True, null=True)
    building_specs = models.TextField(blank=True, null=True)

    # Pricing
    price = models.DecimalField(max_digits=15, decimal_places=2)
    is_negotiable = models.BooleanField(default=False)

    # Tags & Favorites
    tags = models.ManyToManyField(
        PropertyTag,
        blank=True,
        related_name='properties'
    )
    favorited_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='favorite_properties'
    )

    # Blocked Dates (for viewing)
    blocked_dates = models.JSONField(default=list, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Property'
        verbose_name_plural = 'Properties'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_listing_status_display()}"


class PropertyImage(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(upload_to='properties/')
    caption = models.CharField(max_length=255, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Image for {self.property.title}"


class PropertyStatusLog(models.Model):
    property = models.ForeignKey(
        Property,
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

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.property.title}: {self.old_status} → {self.new_status}"