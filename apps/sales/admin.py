from django.contrib import admin
from django.utils.html import format_html
from .models import Sale, PaymentSchedule, Disbursement, SaleTask


class PaymentScheduleInline(admin.TabularInline):
    model = PaymentSchedule
    extra = 0


class DisbursementInline(admin.TabularInline):
    model = Disbursement
    extra = 0
    readonly_fields = ('created_at',)


class SaleTaskInline(admin.TabularInline):
    model = SaleTask
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'property_display', 'client',
        'sale_assistant', 'net_price_display',
        'payment_scheme', 'status_badge', 'sale_date'
    )
    list_filter = ('status', 'payment_scheme')
    search_fields = ('property__title', 'client__username')
    inlines = [PaymentScheduleInline, DisbursementInline, SaleTaskInline]
    readonly_fields = ('created_at', 'updated_at', 'verified_at', 'approved_at')
    list_per_page = 20

    def property_display(self, obj):
        return format_html(
            '<strong style="color:#111827;">{}</strong>'
            '<br><span style="color:#6b7280; font-size:11px;">{}</span>',
            obj.property.title[:25],
            obj.property.city
        )
    property_display.short_description = 'Property'

    def net_price_display(self, obj):
        return format_html(
            '<span style="font-weight:700; color:#1d4ed8;">₱{}</span>',
            f'{obj.net_price:,.2f}'
        )
    net_price_display.short_description = 'Net Price'

    def status_badge(self, obj):
        colors = {
            'pending_verification': '#f59e0b',
            'ready_for_approval': '#3b82f6',
            'approved': '#10b981',
            'completed': '#059669',
            'cancelled': '#ef4444',
            'defaulted': '#7f1d1d',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 10px; '
            'border-radius:20px; font-size:11px; font-weight:600;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PaymentSchedule)
class PaymentScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'sale', 'due_date', 'amount_due_display',
        'amount_paid_display', 'status_badge'
    )
    list_filter = ('status',)
    list_per_page = 30

    def amount_due_display(self, obj):
        return format_html(
            '<span style="color:#dc2626;">₱{}</span>',
            f'{obj.amount_due:,.2f}'
        )
    amount_due_display.short_description = 'Amount Due'

    def amount_paid_display(self, obj):
        return format_html(
            '<span style="color:#16a34a;">₱{}</span>',
            f'{obj.amount_paid:,.2f}'
        )
    amount_paid_display.short_description = 'Amount Paid'

    def status_badge(self, obj):
        colors = {
            'unpaid': '#f59e0b',
            'paid': '#10b981',
            'overdue': '#ef4444',
            'partial': '#3b82f6',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(Disbursement)
class DisbursementAdmin(admin.ModelAdmin):
    list_display = (
        'sale', 'recipient', 'type_badge',
        'amount_display', 'percentage',
        'status_badge', 'disbursed_at'
    )
    list_filter = ('status', 'disbursement_type')
    search_fields = ('recipient__username', 'sale__id')
    list_per_page = 20

    def type_badge(self, obj):
        colors = {
            'broker_commission': '#8b5cf6',
            'sale_assistant_commission': '#10b981',
            'owner_proceeds': '#f59e0b',
            'company_share': '#3b82f6',
            'referral_fee': '#6b7280',
        }
        color = colors.get(obj.disbursement_type, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_disbursement_type_display()
        )
    type_badge.short_description = 'Type'

    def amount_display(self, obj):
        return format_html(
            '<span style="font-weight:700; color:#1d4ed8;">₱{}</span>',
            f'{obj.amount:,.2f}'
        )
    amount_display.short_description = 'Amount'

    def status_badge(self, obj):
        colors = {
            'in_review': '#f59e0b',
            'pending': '#3b82f6',
            'completed': '#10b981',
            'cancelled': '#ef4444',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(SaleTask)
class SaleTaskAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'sale', 'assigned_to',
        'priority_badge', 'status_badge',
        'due_date', 'created_at'
    )
    list_filter = ('priority', 'status')
    search_fields = ('title', 'assigned_to__username')

    def priority_badge(self, obj):
        colors = {
            'low': '#6b7280',
            'medium': '#3b82f6',
            'high': '#ef4444',
        }
        color = colors.get(obj.priority, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_priority_display()
        )
    priority_badge.short_description = 'Priority'

    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'in_progress': '#3b82f6',
            'completed': '#10b981',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{}20; color:{}; padding:3px 8px; '
            'border-radius:20px; font-size:11px;">{}</span>',
            color, color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'