from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.accounts import views as account_views
from apps.listings import views as listing_views
from apps.reservations import views as reservation_views

# Customize admin
admin.site.site_header = 'Boholana E-Realty Administration'
admin.site.site_title = 'Boholana E-Realty Admin'
admin.site.index_title = 'System Administration Panel'

urlpatterns = [
    path('boholana-admin/', admin.site.urls),
    path('__reload__/', include('django_browser_reload.urls')),

    # Public Side
    path('', listing_views.home_view, name='home'),
    path('properties/', listing_views.properties_view, name='properties'),
    path('properties/<int:pk>/', listing_views.property_detail_view, name='property_detail'),
    path('contact/', listing_views.contact_view, name='contact'),
    path('mortgage-calculator/', listing_views.mortgage_calculator_view, name='mortgage_calculator'),
    path('favorites/', listing_views.favorites_view, name='favorites'),

    # Auth
    path('auth/', include('apps.accounts.urls')),

    # Dashboard
    path('dashboard/', account_views.dashboard_view, name='dashboard'),

    # Client
    path('my-reservations/', reservation_views.my_reservations, name='my_reservations'),

    # Management
    path('manage/listings/', include('apps.listings.urls')),
    path('manage/reservations/', include('apps.reservations.urls')),
    path('manage/sales/', include('apps.sales.urls')),
    path('manage/documents/', include('apps.documents.urls')),
    path('manage/reports/', include('apps.reports.urls')),
    
    # ✅ Public appointment create URL
    path('appointment/<int:property_pk>/', reservation_views.appointment_create, name='appointment_create'),
    
    # Client Side
    path('my-reservations/', reservation_views.my_reservations, name='my_reservations'),
    path('reserve/<int:property_pk>/', reservation_views.reservation_create, name='reservation_create'),
    path('appointment/<int:property_pk>/', reservation_views.appointment_create, name='appointment_create'),

    # ✅ Add these cancel URLs
    path('my-reservations/reservation/<int:pk>/cancel/', reservation_views.reservation_cancel, name='reservation_cancel'),
    path('my-reservations/appointment/<int:pk>/cancel/', reservation_views.appointment_cancel, name='appointment_cancel'),
    
    # ✅ Client chat inbox
    path('my-messages/', reservation_views.client_chat_inbox, name='client_chat_inbox'),

    # Chat
    path('chat/<int:property_pk>/', reservation_views.chat_view, name='chat'),
    path('chat/toggle-availability/', reservation_views.toggle_chat_availability, name='toggle_chat_availability'),
    path('chat/messages/<int:property_pk>/', reservation_views.get_chat_messages, name='get_chat_messages'),

    path('chat/unread-count/', reservation_views.client_unread_count, name='client_unread_count'),
    
     # ✅ Allauth URLs
    path('accounts/', include('allauth.urls')),

    # Public Side
    path('', listing_views.home_view, name='home'),
    
    # Auth
    path('auth/', include('apps.accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ✅ Error handlers OUTSIDE urlpatterns list
handler404 = 'apps.accounts.views.error_404'
handler500 = 'apps.accounts.views.error_500'