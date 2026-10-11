from django.urls import path
from . import views

urlpatterns = [
    path('', views.business_report, name='business_report'),
]