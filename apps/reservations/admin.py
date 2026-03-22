from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Reservation, ReservationStatusLog,
    Appointment, PropertyPreferenceForm,
    ChatMessage, ChatAvailability
)


class ReservationStatusLogInline(admin.TabularInline):
    model = ReservationStatusLog
    extra = 0
    readonly_fields = (
        'changed_by', 'old_status',
        'new_status', 'changed_at'
    )
    can_delete = False


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'property_link', 'client',
        'status_badge', 'reservation_date',
        'fee_display', 'payment_method', 'created_at'
    )
    list_filter = ('status', 'payment_method')
    search_fields = ('client__username', 'property__title')
    inlines = [ReservationStatusLogInline]
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20

    def property_link(self, obj):
        return format_html(
            '<a href="/manage/listings/{}/" style="color:#3b82f6;">{}</a>',
            obj.property.pk, obj.property.title[:30]
        )
    property_link.short_description = 'Property'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'approved': '#10b981',
            'rejected': '#ef4444',
            'cancelled': '#6b7280',
            'completed': '#3b82f6',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 10px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def fee_display(self, obj):
        return format_html(
            '<span style="font-weight:600;">₱{}</span>',
            f'{obj.reservation_fee:,.2f}'
        )
    fee_display.short_description = 'Fee'


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'property', 'client',
        'preferred_date', 'preferred_time',
        'status_badge', 'handled_by'
    )
    list_filter = ('status',)
    search_fields = ('client__username', 'property__title')
    readonly_fields = ('created_at', 'updated_at')

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'confirmed': '#10b981',
            'cancelled': '#ef4444',
            'completed': '#3b82f6',
            'no_show': '#6b7280',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 10px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PropertyPreferenceForm)
class PropertyPreferenceFormAdmin(admin.ModelAdmin):
    list_display = (
        'client', 'preferred_property_type',
        'preferred_location', 'min_budget',
        'max_budget', 'created_at'
    )
    search_fields = ('client__username',)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        'sender', 'receiver', 'property',
        'message_preview', 'is_read', 'created_at'
    )
    list_filter = ('is_read',)
    search_fields = ('sender__username', 'receiver__username')
    readonly_fields = ('created_at',)

    def message_preview(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_preview.short_description = 'Message'


@admin.register(ChatAvailability)
class ChatAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('user', 'availability_badge', 'updated_at')

    def availability_badge(self, obj):
        if obj.is_available:
            return format_html(
                '<span style="background:#dcfce7; color:#16a34a; '
                'padding:3px 10px; border-radius:20px; font-size:11px;">● Online</span>'
            )
        return format_html(
            '<span style="background:#fee2e2; color:#dc2626; '
            'padding:3px 10px; border-radius:20px; font-size:11px;">● Offline</span>'
        )
    availability_badge.short_description = 'Status'