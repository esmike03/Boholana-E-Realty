from django.contrib import admin
from .models import PropertyPreference


@admin.register(PropertyPreference)
class PropertyPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'updated_at', 'min_price', 'max_price']
    list_filter = ['created_at', 'updated_at', 'negotiable_only']
    search_fields = ['user__email', 'user__first_name', 'user__last_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('Property Type', {
            'fields': ('preferred_property_types',)
        }),
        ('Location', {
            'fields': ('preferred_cities', 'preferred_provinces')
        }),
        ('Price', {
            'fields': ('min_price', 'max_price')
        }),
        ('Bedrooms & Bathrooms', {
            'fields': ('min_bedrooms', 'max_bedrooms', 'min_bathrooms', 'max_bathrooms', 'min_garage')
        }),
        ('Areas', {
            'fields': ('min_lot_area', 'max_lot_area', 'min_floor_area', 'max_floor_area')
        }),
        ('Tags & Amenities', {
            'fields': ('preferred_tags',)
        }),
        ('Other', {
            'fields': ('negotiable_only',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
