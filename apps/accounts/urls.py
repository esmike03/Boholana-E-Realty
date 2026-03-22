from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Auth
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),

    # Profile
    path('profile/', views.profile_view, name='profile'),

    # User Management
    path('users/', views.users_list_view, name='users'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<int:pk>/', views.user_detail_view, name='user_detail'),
    path('users/<int:pk>/update/', views.user_update_view, name='user_update'),
    path('users/<int:pk>/disable/', views.user_disable_view, name='user_disable'),
    path('users/<int:pk>/assign-role/', views.assign_role_view, name='assign_role'),

    # Notifications
    path('notifications/', views.notifications_view, name='notifications'),
    path('notifications/<int:pk>/read/', views.notification_read, name='notification_read'),
    path('notifications/count/', views.notification_count, name='notification_count'),
    path('notifications/json/', views.notifications_json, name='notifications_json'),

    # Search
    path('search/', views.global_search, name='search'),
]