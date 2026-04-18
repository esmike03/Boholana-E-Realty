# Role-based feature access matrix

ROLE_PERMISSIONS = {
    'admin': {
        'manage_account': ['create', 'update', 'view', 'disable', 'assign_role'],
        'manage_listing': ['view', 'browse'],
        'manage_sales': ['track', 'policies'],
        'document_tracking': ['view', 'approve', 'search'],
        'generate_report': [
            'active_properties', 'sales_report',
            'total_inquiries', 'total_listings'
        ],
    },
    'broker': {
        'manage_account': ['update', 'view', 'disable'],
        'manage_listing': [
            'view', 'update', 'browse', 'filter',
            'approve', 'tag'
        ],
        'manage_reservation': [
            'schedule', 'check_status', 'update',
            'cancel', 'approve_appointments',
            'live_chat', 'toggle_support'
        ],
        'manage_sales': ['track', 'verify', 'update_status'],
        'disburse_sale': ['view', 'calculate', 'approve'],
        'document_tracking': ['view', 'approve', 'search'],
        'generate_report': [
            'active_properties', 'commission',
            'sales_report', 'total_inquiries', 'total_listings'
        ],
    },
    'property_owner': {
        'manage_account': ['view', 'disable'],
        'manage_listing': [
            'view', 'add', 'add_details',
            'update', 'browse'
        ],
        'manage_reservation': [
            'schedule', 'approve_appointments', 'block_dates'
        ],
        'manage_sales': ['track'],
        'document_tracking': ['view', 'upload', 'categorize', 'search'],
        'generate_report': [
            'sales_report', 'total_inquiries', 'total_listings'
        ],
    },
    'staff': {
        'manage_account': ['update', 'view', 'disable'],
        'manage_listing': [
            'view', 'update', 'browse', 'approve', 'tag'
        ],
        'manage_sales': ['track', 'verify', 'update_status'],
        'document_tracking': ['view', 'approve', 'search'],
    },
    'sale_assistant': {
        'manage_account': ['update', 'view', 'disable'],
        'manage_reservation': [
            'schedule', 'check_status', 'update', 'cancel',
            'approve_appointments', 'live_chat', 'toggle_support'
        ],
        'manage_sales': ['track'],
        'disburse_sale': ['view', 'calculate'],
        'document_tracking': ['view', 'search'],
        'generate_report': [
            'active_properties', 'commission',
            'sales_report', 'total_inquiries', 'total_listings'
        ],
    },
    'client': {
        'manage_account': ['create', 'update', 'view', 'google'],
        'manage_listing': ['browse', 'mortgage', 'filter'],
        'manage_reservation': [
            'send_inquiry', 'schedule', 'check_status',
            'update', 'cancel', 'preference_form', 'live_chat'
        ],
        'document_tracking': ['view', 'search'],
    },
}


def has_permission(user, module, action):
    """Check if user has permission for a specific action."""
    if user.is_superuser:
        return True
    role_perms = ROLE_PERMISSIONS.get(user.role, {})
    module_perms = role_perms.get(module, [])
    return action in module_perms


def get_allowed_modules(user):
    """Get list of modules user has access to."""
    if user.is_superuser:
        return list(ROLE_PERMISSIONS['broker'].keys())
    return list(ROLE_PERMISSIONS.get(user.role, {}).keys())