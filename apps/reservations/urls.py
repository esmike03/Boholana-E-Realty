from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    # Reservations
    path('', views.reservation_list, name='list'),
    path('create/<int:property_pk>/', views.reservation_create, name='create'),
    path('<int:pk>/', views.reservation_detail, name='detail'),
    path('<int:pk>/status/', views.reservation_update_status, name='update_status'),
    path('<int:pk>/cancel/', views.reservation_cancel, name='cancel'),

    # Appointments
    path('appointments/', views.appointment_list, name='appointments'),
    path('appointments/create/<int:property_pk>/', views.appointment_create, name='appointment_create'),
    path('appointments/<int:pk>/update/', views.appointment_update, name='appointment_update'),

    # Block Dates
    path('block-dates/<int:property_pk>/', views.block_dates, name='block_dates'),

    # Chat
    path('chat/<int:property_pk>/', views.chat_view, name='chat'),
    path('chat/<int:property_pk>/messages/', views.get_chat_messages, name='chat_messages'),
    path('chat/toggle-availability/', views.toggle_chat_availability, name='toggle_availability'),
]