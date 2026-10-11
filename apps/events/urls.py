from django.urls import path
from . import views

app_name = 'events'

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('create/', views.create_event, name='create_event'),
    path('registrations/', views.all_event_registrations, name='all_event_registrations'),
    path('<int:event_id>/edit/', views.edit_event, name='edit_event'),
    path('<int:event_id>/cancel/', views.cancel_event, name='cancel_event'),
    path('<int:event_id>/notify/', views.notify_members, name='notify_members'),
    path('<int:event_id>/register/', views.event_registration, name='event_registration'),
    path('update_payment_status/<int:registration_id>/', views.update_payment_status, name='update_payment_status'),
]