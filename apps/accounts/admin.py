from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import models
from django.utils.html import format_html
from .models import CustomUser, UserActivityLog, UserPreference, Notification
from .models import ContactMessage


class UserPreferenceInline(admin.StackedInline):
    model = UserPreference
    extra = 0
    can_delete = False
    verbose_name_plural = 'Preferences'


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'avatar_display', 'username', 'full_name',
        'email', 'role_badge', 'commission_evaluation_label',
        'is_verified', 'is_disabled', 'is_active', 'date_joined'
    )

    def commission_evaluation_label(self, obj):
        from apps.reports.models import Report
        # SQLite does not support JSONField `contains`, so check the user relation in SQL first
        # and fall back to scanning JSON parameters in Python.
        if Report.objects.filter(report_type='commission_report', generated_by=obj).exists():
            return format_html('<span style="background:#f59e0b; color:white; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:600;">Commission Evaluation</span>')

        for report in Report.objects.filter(report_type='commission_report').only('parameters'):
            parameters = report.parameters or {}
            if str(parameters.get('user_id')) == str(obj.id):
                return format_html('<span style="background:#f59e0b; color:white; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:600;">Commission Evaluation</span>')
        return ''
    commission_evaluation_label.short_description = 'Commission Report?'
    list_display_links = ('username', 'full_name')
    list_filter = ('role', 'is_verified', 'is_disabled', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    list_per_page = 20

    readonly_fields = (
        'disabled_at', 'assigned_at',
        'created_at', 'updated_at'
    )

    fieldsets = UserAdmin.fieldsets + (
        ('Role & Company Info', {
            'fields': (
                'role', 'employee_id', 'department',
                'assigned_by', 'assigned_at'
            )
        }),
        ('Personal Info', {
            'fields': (
                'phone_number', 'address', 'profile_picture',
                'birth_date', 'gender'
            )
        }),
        ('Account Status', {
            'fields': (
                'is_verified', 'is_disabled',
                'disabled_reason', 'disabled_at', 'disabled_by'
            )
        }),
        ('Social Login', {
            'fields': ('social_provider', 'social_uid')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role & Company Info', {
            'fields': ('role', 'employee_id', 'department')
        }),
        ('Personal Info', {
            'fields': (
                'first_name', 'last_name',
                'email', 'phone_number', 'address'
            )
        }),
    )

    inlines = [UserPreferenceInline]

    def avatar_display(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" width="35" height="35" '
                'style="border-radius:50%; object-fit:cover;">',
                obj.profile_picture.url
            )
        initials = obj.get_initials()
        return format_html(
            '<div style="width:35px; height:35px; border-radius:50%; '
            'background:#3b82f6; color:white; display:flex; '
            'align-items:center; justify-content:center; '
            'font-weight:bold; font-size:12px;">{}</div>',
            initials
        )
    avatar_display.short_description = ''

    def full_name(self, obj):
        return obj.get_full_name() or '—'
    full_name.short_description = 'Full Name'

    def role_badge(self, obj):
        colors = {
            'admin': '#ef4444',
            'broker': '#8b5cf6',
            'staff': '#3b82f6',
            'sale_assistant': '#10b981',
            'property_owner': '#f59e0b',
            'client': '#6b7280',
        }
        color = colors.get(obj.role, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:3px 10px; '
            'border-radius:20px; font-size:11px; font-weight:600;">{}</span>',
            color, obj.get_role_display()
        )
    role_badge.short_description = 'Role'


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'action_badge', 'description',
        'ip_address', 'performed_by', 'created_at'
    )
    list_filter = ('action',)
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)
    list_per_page = 30

    def action_badge(self, obj):
        colors = {
            'login': '#10b981',
            'logout': '#6b7280',
            'register': '#3b82f6',
            'update_profile': '#f59e0b',
            'change_password': '#ef4444',
            'role_assigned': '#8b5cf6',
            'account_disabled': '#ef4444',
            'account_enabled': '#10b981',
        }
        color = colors.get(obj.action, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_action_display()
        )
    action_badge.short_description = 'Action'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        'recipient', 'title', 'notification_type',
        'priority_badge', 'is_read', 'created_at'
    )
    list_filter = ('notification_type', 'priority', 'is_read')
    search_fields = ('recipient__username', 'title', 'message')
    readonly_fields = ('created_at', 'read_at')
    list_per_page = 30

    def priority_badge(self, obj):
        colors = {
            'low': '#6b7280',
            'medium': '#3b82f6',
            'high': '#f59e0b',
            'urgent': '#ef4444',
        }
        color = colors.get(obj.priority, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Priority'
    

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'email', 'phone',
        'property_type', 'listing_type',
        'city', 'preferred_contact',
        'property', 'is_read', 'created_at'
    )
    list_filter = (
        'is_read', 'property_type',
        'listing_type', 'preferred_contact'
    )
    search_fields = ('name', 'email', 'phone', 'message', 'city')
    readonly_fields = ('created_at',)