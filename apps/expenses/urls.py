from django.urls import path
from . import views

urlpatterns = [
    path('expenses/', views.expenses, name='expenses'),
    path('expenses/add/', views.expense_add, name='expense_add'),
    path('expenses/<int:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    # TRASH
    path('expenses/trash/', views.expense_trash, name='expense_trash'),
    path('expenses/<int:pk>/restore/', views.expense_restore, name='expense_restore'),
    path('expenses/<int:pk>/delete-permanent/', views.expense_delete_permanent, name='expense_delete_permanent'),
]