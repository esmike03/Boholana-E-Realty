from django.contrib import admin
from django.utils.html import format_html
from .models import Report, ReportSchedule


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'type_badge', 'format_badge',
        'status_badge', 'generated_by',
        'date_range', 'created_at'
    )
    list_filter = ('report_type', 'status', 'format')
    search_fields = ('title', 'generated_by__username')
    readonly_fields = ('created_at', 'completed_at')
    list_per_page = 20

    def type_badge(self, obj):
        return format_html(
            '<span style="background:#ede9fe; color:#7c3aed; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            obj.get_report_type_display()
        )
    type_badge.short_description = 'Type'

    def format_badge(self, obj):
        colors = {
            'pdf': '#ef4444',
            'excel': '#10b981',
            'csv': '#3b82f6',
        }
        color = colors.get(obj.format, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:2px 8px; '
            'border-radius:20px; font-size:11px; font-weight:700;">{}</span>',
            color, color, obj.format.upper()
        )
    format_badge.short_description = 'Format'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'generating': '#3b82f6',
            'completed': '#10b981',
            'failed': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def date_range(self, obj):
        if obj.date_from:
            return format_html(
                '<span style="color:#6b7280; font-size:11px;">{} → {}</span>',
                obj.date_from,
                obj.date_to or 'Present'
            )
        return format_html(
            '<span style="color:#9ca3af; font-size:11px;">All Time</span>'
        )
    date_range.short_description = 'Date Range'


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'report_type', 'frequency_badge',
        'format', 'is_active', 'last_run', 'next_run'
    )
    list_filter = ('frequency', 'is_active', 'report_type')
    search_fields = ('title',)
    filter_horizontal = ('recipients',)

    def frequency_badge(self, obj):
        return format_html(
            '<span style="background:#dbeafe; color:#1d4ed8; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            obj.get_frequency_display()
        )
    frequency_badge.short_description = 'Frequency'