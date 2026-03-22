from django.urls import path
from . import views

app_name = 'listings'

urlpatterns = [
    # Management
    path('', views.listing_list, name='list'),
    path('create/', views.listing_create, name='create'),
    path('<int:pk>/', views.listing_detail, name='detail'),
    path('<int:pk>/update/', views.listing_update, name='update'),
    path('<int:pk>/approve/', views.listing_approve, name='approve'),
    path('<int:pk>/reject/', views.listing_reject, name='reject'),
    path('<int:pk>/flag/', views.listing_flag, name='flag'),
    path('<int:pk>/archive/', views.listing_archive, name='archive'),
    path('<int:pk>/sold/', views.listing_mark_sold, name='mark_sold'),
    path('<int:pk>/favorite/', views.toggle_favorite, name='favorite'),
    
     # Tags
    path('tags/', views.tag_list, name='tags'),
    path('tags/create/', views.tag_create, name='tag_create'),
    path('tags/<int:pk>/', views.tag_detail, name='tag_detail'),
    path('tags/<int:pk>/update/', views.tag_update, name='tag_update'),
    path('tags/<int:pk>/delete/', views.tag_delete, name='tag_delete'),
]