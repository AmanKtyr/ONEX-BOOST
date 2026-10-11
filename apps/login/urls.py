from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('superadmin/login/', views.superadmin_login, name='superadmin_login'),
    path('logout/', views.user_logout, name='logout'),
    path('add_subadmin/', views.add_gym_subadmin, name='add_gym_subadmin'),
    path('view_subadmins/', views.view_subadmins, name='view_subadmins'),
    path('delete_subadmin/<int:sub_admin_id>/', views.delete_subadmin, name='delete_subadmin'),
    path('edit_subadmin/<int:sub_admin_id>/', views.edit_subadmin, name='edit_subadmin'),
    path('password_reset/', views.password_reset_page, name='password_reset_page'),
    path('forgot-password/', views.forgot_password_request_api, name='forgot_password_api'),
]