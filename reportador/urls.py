from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('form/', views.DashboardIndexView.as_view(), name='form_servicios'),
    path('api/clientes/', views.api_buscar_clientes, name='api_buscar_clientes'),
    path('api/inspecciones/guardar/', views.guardar_inspeccion, name='guardar_inspeccion'),
    path('api/corregir-texto/', views.corregir_texto_view, name='corregir_texto'),
]