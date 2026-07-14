from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('form/', views.DashboardIndexView.as_view(), name='form_clientes'),
    path('api/clientes/guardar/', views.guardar_cliente, name='guardar_cliente'),
    path('api/graficas/consolidado/', views.dashboard_analytics, name='dashboard_admin'),
    
    path('consolidado/', views.consolidado_selector, name='consolidado_selector'),
    path('api/consolidado/preview/', views.api_consolidado_preview, name='api_consolidado_preview'),
    path('consolidado/generar/', views.generar_consolidado, name='generar_consolidado'),
]