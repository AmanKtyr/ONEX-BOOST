from django.urls import path
from . import views

urlpatterns = [
    path('list/', views.trainer_list, name='trainer_list'),
    path('profile/<int:trainer_id>/', views.trainer_profile, name='trainer_profile'),
    path('add/', views.add_trainer, name='add_trainer'),
    path('edit/<int:trainer_id>/', views.edit_trainer, name='edit_trainer'),
    path('delete/<int:trainer_id>/', views.delete_trainer, name='delete_trainer'),
    path('toggle_status/<int:trainer_id>/', views.toggle_trainer_status, name='toggle_trainer_status'),
    path('reset-password/<int:trainer_id>/', views.reset_trainer_password, name='reset_trainer_password'),
    path('salaries/', views.trainer_salary_list, name='trainer_salary_list'),
    path('salaries/recalculate/', views.recalculate_trainer_salaries, name='recalculate_trainer_salaries'),
    path('salaries/adjust/<int:salary_id>/', views.update_trainer_salary_adjustment, name='update_trainer_salary_adjustment'),
    path('salaries/approve/<int:salary_id>/', views.approve_trainer_salary, name='approve_trainer_salary'),
    path('salaries/pay/<int:salary_id>/', views.pay_trainer_salary, name='pay_trainer_salary'),
    path('salaries/payslip/<int:salary_id>/', views.trainer_payslip, name='trainer_payslip'),
]