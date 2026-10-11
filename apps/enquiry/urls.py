from django.urls import path
from . import views

urlpatterns = [
    path('add-enquiry/', views.add_new_enquiry, name='add_new_enquiry'),
    path('list/', views.enquiry_list, name='enquiry_list'),
    path('edit/<int:enquiry_id>/', views.edit_enquiry, name='edit_enquiry'),
    path('delete/<int:enquiry_id>/', views.delete_enquiry, name='delete_enquiry'),
    path('update_status/<int:enquiry_id>/', views.update_enquiry_status, name='update_enquiry_status'),
]