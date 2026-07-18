from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_list, name='list'),
    path('transactions/', views.transaction_list, name='transactions'),
    path('create/', views.report_create, name='create'),
    path('<int:pk>/', views.report_detail, name='detail'),
    path('<int:pk>/download/', views.report_download, name='download'),
    path('<int:pk>/preview/', views.report_preview, name='preview'),
]