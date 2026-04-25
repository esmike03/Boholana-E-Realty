from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='list'),
    path('upload/', views.document_upload, name='upload'),
    path('<int:pk>/', views.document_detail, name='detail'),
    path('<int:pk>/update/', views.document_update, name='update'),
    path('<int:pk>/approve/', views.document_approve, name='approve'),
    path('<int:pk>/reject/', views.document_reject, name='reject'),
    path('search/', views.document_search, name='search'),
    path('checklist/<int:sale_pk>/', views.document_checklist, name='checklist'),
    
    # Listing Document Tracking
    path('listing/<int:property_pk>/', views.listing_documents, name='listing_documents'),
    
    # Client Document Tracking
    path('my-documents/', views.client_documents, name='client_documents'),
    path('my-documents/upload/', views.client_document_upload, name='client_upload'),
]