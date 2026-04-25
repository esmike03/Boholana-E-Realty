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
    actions = ['autogenerate_featured']

    def autogenerate_featured(self, request, queryset):
        """
        Set the latest 6 approved properties as featured, un-feature the rest.
        Only available to admin and broker.
        """
        if not (request.user.is_superuser or getattr(request.user, 'role', None) in ['admin', 'broker']):
            self.message_user(request, "You do not have permission to auto-generate featured properties.", level='error')
            return
        # Un-feature all properties
        Property.objects.filter(is_featured=True).update(is_featured=False)
        # Feature the latest 6 approved properties
        featured = Property.objects.filter(listing_status='approved').order_by('-created_at')[:6]
        count = featured.update(is_featured=True)
        self.message_user(request, f"{count} properties set as featured.")
    autogenerate_featured.short_description = "Auto-generate featured properties (latest 6 approved)"
    list_display = (
        'image_preview', 'title', 'property_type',
        'city', 'price_display', 'status_badge',
        'is_featured', 'owner', 'broker', 'sale_assistant', 'created_at'
    )
    list_display_links = ('title',)
    list_filter = (
        'property_type', 'listing_type',
        'listing_status', 'is_featured', 'city', 'broker', 'sale_assistant'
    )
    # list_editable for is_featured will be set dynamically
    def get_list_editable(self, request):
        if request.user.is_superuser or getattr(request.user, 'role', None) in ['admin', 'broker']:
            return ('is_featured',)
        return ()

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if not (request.user.is_superuser or getattr(request.user, 'role', None) in ['admin', 'broker']):
            ro.append('is_featured')
        return ro

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        # Ensure is_featured is present
        if 'is_featured' not in fields:
            fields.append('is_featured')
        return fields

    def get_list_display(self, request):
        return self.list_display

    def get_changelist_instance(self, request):
        # Patch list_editable dynamically
        self.list_editable = self.get_list_editable(request)
        return super().get_changelist_instance(request)
    search_fields = ('title', 'address', 'city', 'broker__username', 'sale_assistant__username')
    inlines = [PropertyImageInline, PropertyStatusLogInline]
    readonly_fields = (
        'created_at', 'updated_at',
        'approved_at', 'flagged_at'
    )
    fields = (
        'title', 'description', 'property_type', 'listing_type', 'listing_status',
        'owner', 'broker', 'sale_assistant', 'price', 'address', 'city', 'province',
        'approved_by', 'approved_at', 'flagged_by', 'flagged_at', 'rejected_reason',
        'is_featured', 'tags', 'favorited_by', 'created_at', 'updated_at'
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