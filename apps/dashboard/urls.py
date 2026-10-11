from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard_slash'),
    path('member-growth-chart-data/', views.member_growth_chart_data, name='member_growth_chart_data'),
]