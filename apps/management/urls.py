from django.urls import path
from . import views

urlpatterns = [
    path('membership-plans/', views.membership_plans, name='membership_plans'),
    path('membership-plans/edit/<int:pk>/', views.edit_membership_plan, name='edit_membership_plan'),
    path('membership-plans/delete/<int:pk>/', views.delete_membership_plan, name='delete_membership_plan'),
    path('diet-plans/', views.diet_plans, name='diet_plans'),
    path('diet-plans/edit/<int:pk>/', views.edit_diet_plan, name='edit_diet_plan'),
    path('diet-plans/delete/<int:pk>/', views.delete_diet_plan, name='delete_diet_plan'),
    path('workout-plans/edit/<int:pk>/', views.edit_workout_plan, name='edit_workout_plan'),
    path('workout-plans/delete/<int:pk>/', views.delete_workout_plan, name='delete_workout_plan'),
    path('workout-plans/', views.workout_plans, name='workout_plans'),
    path('public/diet-plan/<int:pk>/', views.public_diet_plan, name='public_diet_plan'),
    path('public/workout-plan/<int:pk>/', views.public_workout_plan, name='public_workout_plan'),
]