from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('form/', views.DashboardIndexView.as_view(), name='form_reuniones'),
    path('api/reuniones/guardar/', views.guardar_reunion, name='guardar_reunion'),
]