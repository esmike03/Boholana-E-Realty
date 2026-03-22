from django.contrib import admin
from django.utils.html import format_html
from .models import Document, DocumentAuditLog, DocumentChecklist


class DocumentAuditLogInline(admin.TabularInline):
    model = DocumentAuditLog
    extra = 0
    readonly_fields = (
        'performed_by', 'action',
        'description', 'performed_at'
    )
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'file_icon', 'title', 'type_badge',
        'uploaded_by', 'status_badge',
        'is_confidential', 'version', 'created_at'
    )
    list_filter = ('document_type', 'status', 'is_confidential', 'file_format')
    search_fields = ('title', 'uploaded_by__username')
    inlines = [DocumentAuditLogInline]
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20

    def file_icon(self, obj):
        icons = {
            'pdf': '📄',
            'word': '📝',
            'image': '🖼️',
            'other': '📎',
        }
        icon = icons.get(obj.file_format, '📎')
        return format_html('<span style="font-size:18px;">{}</span>', icon)
    file_icon.short_description = ''

    def type_badge(self, obj):
        return format_html(
            '<span style="background:#dbeafe; color:#1d4ed8; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            obj.get_document_type_display()
        )
    type_badge.short_description = 'Type'

    def status_badge(self, obj):
        colors = {
            'pending_approval': '#f59e0b',
            'approved': '#10b981',
            'rejected': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(DocumentAuditLog)
class DocumentAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        'document', 'action_badge',
        'performed_by', 'performed_at'
    )
    readonly_fields = ('performed_at',)
    list_filter = ('action',)

    def action_badge(self, obj):
        colors = {
            'uploaded': '#3b82f6',
            'approved': '#10b981',
            'rejected': '#ef4444',
            'updated': '#f59e0b',
            'deleted': '#7f1d1d',
            'viewed': '#6b7280',
        }
        color = colors.get(obj.action, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:2px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_action_display()
        )
    action_badge.short_description = 'Action'


@admin.register(DocumentChecklist)
class DocumentChecklistAdmin(admin.ModelAdmin):
    list_display = (
        'sale', 'type_display', 'is_required',
        'submitted_badge', 'submitted_at'
    )
    list_filter = ('is_required', 'is_submitted')

    def type_display(self, obj):
        return obj.get_document_type_display()
    type_display.short_description = 'Document Type'

    def submitted_badge(self, obj):
        if obj.is_submitted:
            return format_html(
                '<span style="background:#dcfce7; color:#16a34a; '
                'padding:2px 8px; border-radius:20px; font-size:11px;">✓ Submitted</span>'
            )
        return format_html(
            '<span style="background:#fee2e2; color:#dc2626; '
            'padding:2px 8px; border-radius:20px; font-size:11px;">✗ Pending</span>'
        )
    submitted_badge.short_description = 'Submitted'