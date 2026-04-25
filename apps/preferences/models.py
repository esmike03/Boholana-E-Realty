from django.db import models
from django.conf import settings
from apps.listings.models import PropertyTag


class PropertyPreference(models.Model):
    PROPERTY_TYPE_CHOICES = (
        ('house', 'House'),
        ('lot', 'Lot'),
        ('house_and_lot', 'House and Lot'),
        ('condo', 'Condominium'),
        ('commercial', 'Commercial'),
        ('apartment', 'Apartment'),
        ('warehouse', 'Warehouse'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='property_preference'
    )
    
    # Property Type Preferences
    preferred_property_types = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated property types (e.g., 'house,condo')"
    )
    
    # Location Preferences
    preferred_cities = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated city names"
    )
    preferred_provinces = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated province names"
    )
    
    # Price Preferences
    min_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    max_price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # Property Size Preferences
    min_bedrooms = models.PositiveIntegerField(null=True, blank=True)
    max_bedrooms = models.PositiveIntegerField(null=True, blank=True)
    min_bathrooms = models.PositiveIntegerField(null=True, blank=True)
    max_bathrooms = models.PositiveIntegerField(null=True, blank=True)
    min_garage = models.PositiveIntegerField(null=True, blank=True)
    
    # Area Preferences
    min_lot_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="in sqm"
    )
    max_lot_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="in sqm"
    )
    min_floor_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="in sqm"
    )
    max_floor_area = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="in sqm"
    )
    
    # Tags/Amenities Preferences
    preferred_tags = models.ManyToManyField(
        PropertyTag,
        blank=True,
        related_name='preferred_by_users'
    )

    # Free-form amenities text
    preferred_amenities = models.TextField(
        blank=True,
        default='',
        help_text="Free-form desired amenities (e.g., Swimming Pool, Garden, Garage)"
    )

    # Preferences Flags
    negotiable_only = models.BooleanField(
        default=False,
        help_text="Only show negotiable properties"
    )

    # Office submission tracking
    submitted_to_office = models.BooleanField(
        default=False,
        help_text="Whether preferences were formally submitted to the office"
    )
    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the preferences were submitted to the office"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Property Preference'
        verbose_name_plural = 'Property Preferences'

    def __str__(self):
        return f"Property Preferences for {self.user.email}"
