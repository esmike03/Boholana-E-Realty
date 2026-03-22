from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Property, PropertyImage,
    PropertyTag, PropertyStatusLog
)


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 1
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="80" height="60" '
                'style="object-fit:cover; border-radius:6px;">',
                obj.image.url
            )
        return '—'
    image_preview.short_description = 'Preview'


class PropertyStatusLogInline(admin.TabularInline):
    model = PropertyStatusLog
    extra = 0
    readonly_fields = (
        'changed_by', 'old_status',
        'new_status', 'changed_at', 'remarks'
    )
    can_delete = False


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'image_preview', 'title', 'property_type',
        'city', 'price_display', 'status_badge',
        'owner', 'created_at'
    )
    list_display_links = ('title',)
    list_filter = (
        'property_type', 'listing_type',
        'listing_status', 'city'
    )
    search_fields = ('title', 'address', 'city')
    inlines = [PropertyImageInline, PropertyStatusLogInline]
    readonly_fields = (
        'created_at', 'updated_at',
        'approved_at', 'flagged_at'
    )
    list_per_page = 20
    filter_horizontal = ('tags', 'favorited_by')

    def image_preview(self, obj):
        first_image = obj.images.first()
        if first_image:
            return format_html(
                '<img src="{}" width="50" height="40" '
                'style="object-fit:cover; border-radius:6px;">',
                first_image.image.url
            )
        return format_html(
            '<div style="width:50px; height:40px; background:#e5e7eb; '
            'border-radius:6px; display:flex; align-items:center; '
            'justify-content:center; color:#9ca3af; font-size:18px;">'
            '🏠</div>'
        )
    image_preview.short_description = ''

    def price_display(self, obj):
        return format_html(
            '<span style="font-weight:600; color:#1d4ed8;">₱{}</span>',
            f'{obj.price:,.0f}'
        )
    price_display.short_description = 'Price'

    def status_badge(self, obj):
        colors = {
            'draft': '#6b7280',
            'pending_approval': '#f59e0b',
            'flagged': '#ef4444',
            'approved': '#10b981',
            'rejected': '#ef4444',
            'sold': '#3b82f6',
            'archived': '#9ca3af',
        }
        color = colors.get(obj.listing_status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 10px; '
            'border-radius:20px; font-size:11px; font-weight:600;">{}</span>',
            color, color, obj.get_listing_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = (
        'image_preview', 'property',
        'caption', 'is_primary', 'uploaded_at'
    )
    list_filter = ('is_primary',)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" width="60" height="45" '
                'style="object-fit:cover; border-radius:4px;">',
                obj.image.url
            )
        return '—'
    image_preview.short_description = 'Image'


@admin.register(PropertyTag)
class PropertyTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'property_count', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

    def property_count(self, obj):
        count = obj.properties.count()
        return format_html(
            '<span style="font-weight:600; color:#3b82f6;">{}</span>',
            count
        )
    property_count.short_description = 'Properties'


@admin.register(PropertyStatusLog)
class PropertyStatusLogAdmin(admin.ModelAdmin):
    list_display = (
        'property', 'old_status', 'arrow',
        'new_status', 'changed_by', 'changed_at'
    )
    readonly_fields = ('changed_at',)
    list_filter = ('new_status',)

    def arrow(self, obj):
        return format_html('<span style="color:#6b7280;">→</span>')
    arrow.short_description = ''