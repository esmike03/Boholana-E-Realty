from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Sales
    path('', views.sale_list, name='list'),
    path('create/', views.sale_create, name='create'),
    path('<int:pk>/', views.sale_detail, name='detail'),
    path('<int:pk>/verify/', views.sale_verify, name='verify'),
    path('<int:pk>/status/', views.sale_update_status, name='update_status'),
    path('<int:pk>/task/', views.assign_task, name='assign_task'),

    # Disbursements
    path('disbursements/', views.disbursement_list, name='disbursements'),
    path('disbursements/<int:pk>/approve/', views.disbursement_approve, name='disbursement_approve'),
    path('disbursements/<int:pk>/receive/', views.disbursement_receive, name='disbursement_receive'),
]