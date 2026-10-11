from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('member-attendance/', views.member_attendance, name='member_attendance'),
    path('qr-code/', views.qr_code_view, name='qr_code'),
    path('scan-attendance/<str:gym_id>/', views.scan_attendance, name='scan_attendance'),
    path('trainer-attendance/', views.trainer_attendance, name='trainer_attendance'),
    path('attendance-report/', views.attendance_report, name='attendance_report'),
    path('leave-management/', views.leave_management, name='leave_management'),
    path('add-trainer-leave/', views.add_trainer_leave, name='add_trainer_leave'),
    path('add-member-leave/', views.add_member_leave, name='add_member_leave'),
    path('update-leave-status/<str:leave_type>/<int:leave_id>/<str:status>/', views.update_leave_status, name='update_leave_status'),
    path('edit-leave/<str:leave_type>/<int:leave_id>/', views.edit_leave, name='edit_leave'),
    path('delete-leave/<str:leave_type>/<int:leave_id>/', views.delete_leave, name='delete_leave'),
]