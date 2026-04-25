from django.urls import path
from . import views

app_name = 'reservations'

urlpatterns = [
    # Reservation Management Dashboard
    path('manage/', views.manage_reservation, name='manage'),

    # Reservations
    path('', views.reservation_list, name='list'),
    path('create/<int:property_pk>/', views.reservation_create, name='create'),
    path('staff/create/', views.staff_reservation_create, name='staff_create'),
    path('<int:pk>/', views.reservation_detail, name='detail'),
    path('<int:pk>/status/', views.reservation_update_status, name='update_status'),
    path('<int:pk>/update/', views.reservation_update, name='update'),
    path('<int:pk>/inquiry/', views.reservation_inquiry, name='inquiry'),
    path('<int:pk>/cancel/', views.reservation_cancel, name='cancel'),
    path('reservation/<int:pk>/inquiry/', views.reservation_inquiry, name='reservation_inquiry'),

    # Appointments
    path('appointments/', views.appointment_list, name='appointments'),
    path('appointments/staff/create/', views.staff_appointment_create, name='staff_appointment_create'),
    path('appointments/create/<int:property_pk>/', views.appointment_create, name='appointment_create'),
    path('appointments/<int:pk>/update/', views.appointment_update, name='appointment_update'),

    # Block Dates
    path('block-dates/<int:property_pk>/', views.block_dates, name='block_dates'),

    # Chat
    path('chat/', views.chat_inbox, name='chat_inbox'),
    path('chat/<int:property_pk>/', views.chat_view, name='chat'),
    path('chat/<int:property_pk>/messages/', views.get_chat_messages, name='chat_messages'),
    path('chat/toggle-availability/', views.toggle_chat_availability, name='toggle_availability'),

]