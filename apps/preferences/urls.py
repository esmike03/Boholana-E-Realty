from django.urls import path
from . import views

urlpatterns = [
    path('preferences/', views.preference_form, name='preference_form'),
    path('preferences/clients/', views.client_preferences_list, name='client_preferences'),
    path('search/', views.search_with_preferences, name='search_with_preferences'),
]
