from django.urls import path
from . import views

urlpatterns = [
    path('', views.member_dashboard, name='dashboard'),
    path('dashboard/', views.member_dashboard, name='dashboard_alias'),
    path('attendance/', views.member_attendance_view, name='attendance'),
    path('attendance/action/', views.member_attendance_action, name='attendance_action'),
    path('leave/apply/', views.member_apply_leave, name='apply_leave'),
    path('workout/', views.member_workout_view, name='workout_plan'),
    path('progress/', views.member_progress_view, name='progress'),
    path('progress/log-workout/', views.member_log_workout_action, name='log_workout'),
    path('progress/log-metrics/', views.member_log_metrics_action, name='log_metrics'),
    path('progress/set-goal/', views.member_set_goal_action, name='set_goal'),
    path('progress/delete-workout/<int:log_id>/', views.member_delete_workout_log, name='delete_workout_log'),
    path('progress/delete-metric/<int:metric_id>/', views.member_delete_metric, name='delete_metric'),
    path('diet/', views.member_diet_view, name='diet_plan'),
    path('billing/', views.member_billing_view, name='billing'),
    path('personal-training/', views.member_pt_view, name='personal_training'),
    path('profile/', views.member_profile_view, name='profile'),
    path('verify-pass/<str:member_id>/', views.member_verify_pass_view, name='verify_pass'),
]
