from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('submit_due/', views.submit_due, name='submit_due'),
    path('pay_due_payment/<int:member_id>/', views.pay_due_payment, name='pay_due_payment'),
    path('invoice/<int:member_id>/<int:history_id>/', views.invoice, name='invoice'),
    path('pt_invoice/<int:member_id>/<int:pt_invoice_id>/', views.pt_invoice, name='pt_invoice'),
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('trash/', views.trash_invoices, name='trash_invoices'),
    path('update_follow_up/<int:member_id>/', views.update_follow_up, name='update_follow_up'),
    path('delete_invoice/<str:invoice_type>/<int:invoice_id>/', views.delete_invoice, name='delete_invoice'),
    path('restore_invoice/<str:invoice_type>/<int:invoice_id>/', views.restore_invoice, name='restore_invoice'),
    path('delete_permanently/<str:invoice_type>/<int:invoice_id>/', views.delete_permanently, name='delete_permanently'),
]