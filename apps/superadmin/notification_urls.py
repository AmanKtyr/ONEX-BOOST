from django.urls import path
from . import views

urlpatterns = [
    path('', views.user_notifications_inbox, name='inbox'),
    path('active-popup/', views.get_active_popup_api, name='active_popup'),
    path('<int:notification_id>/acknowledge-popup/', views.acknowledge_popup_api, name='acknowledge_popup'),
    path('<int:notification_id>/mark-read/', views.mark_notification_read_api, name='mark_read'),
    path('mark-all-read/', views.mark_all_notifications_read_api, name='mark_all_read'),
]
