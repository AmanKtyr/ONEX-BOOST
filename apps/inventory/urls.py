from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('inventory/', views.inventory_dashboard, name='dashboard'),

    # Items CRUD
    path('all-items/', views.all_items, name='all_items'),
    path('add-item/', views.add_edit_item, name='add_item'),
    path('edit-item/<int:id>/', views.add_edit_item, name='edit_item'),
    path('delete-item/<int:id>/', views.delete_item, name='delete_item'),

    # Stock Management
    path('stock-out/', views.stock_out_view, name='stock_out'),
    path('stock-out/<int:item_id>/', views.stock_out_view, name='stock_out_item'),

    # Stock Log
    path('item/<int:item_id>/log/', views.stock_log_view, name='stock_log'),

    # Equipment
    path('all-equipment/', views.all_equipment, name='all_equipment'),
    path('add-equipment/', views.add_edit_equipment, name='add_equipment'),
    path('edit-equipment/<int:id>/', views.add_edit_equipment, name='edit_equipment'),
    path('delete-equipment/<int:id>/', views.delete_equipment, name='delete_equipment'),
    path('maintenance-log/', views.maintenance_log, name='maintenance_log'),
]