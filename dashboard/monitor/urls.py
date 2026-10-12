"""URL routing cho ứng dụng monitor."""

from django.urls import path
from . import views

app_name = 'monitor'

urlpatterns = [
    # Template views
    path('', views.dashboard_view, name='dashboard'),
    path('clients/', views.clients_view, name='clients'),
    path('clients/<str:mac>/', views.client_detail_view, name='client_detail'),
    path('events/', views.events_view, name='events'),

    # JSON API
    path('api/clients/', views.api_clients, name='api_clients'),
    path('api/events/', views.api_events, name='api_events'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/scan-history/', views.api_scan_history, name='api_scan_history'),
]

