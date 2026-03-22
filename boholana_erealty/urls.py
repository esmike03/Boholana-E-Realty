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

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# ✅ Error handlers OUTSIDE urlpatterns list
handler404 = 'apps.accounts.views.error_404'
handler500 = 'apps.accounts.views.error_500'