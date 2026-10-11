from django.db import models
from django.contrib.auth.models import User
from apps.superadmin.models import Gym


class Expense(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    PAYMENT_MODES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('net_banking', 'Net Banking'),
        ('other', 'Other'),
    ]

    EXPENSE_CATEGORIES = [
        ("equipment", "Gym Equipment"),
        ("maintenance", "Maintenance & Repair"),
        ("salary", "Staff Salary"),
        ("rent", "Gym Rent"),
        ("electricity", "Electricity Bill"),
        ("water", "Water Bill"),
        ("internet", "Internet Bill"),
        ("cleaning", "Cleaning Supplies"),
        ("marketing", "Marketing & Ads"),
        ("software", "Software / Subscription"),
        ("tax", "Taxes"),
        ("other", "Other"),
    ]

    date = models.DateField()
    category = models.CharField(max_length=50, choices=EXPENSE_CATEGORIES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    vendor_name = models.CharField(max_length=200, blank=True, null=True)
    vendor_phone = models.CharField(max_length=20, blank=True, null=True)
    vendor_bill_number = models.CharField(max_length=100, blank=True, null=True)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES, default='cash')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    receipt_image = models.ImageField(upload_to="expense_receipts/", blank=True, null=True)


    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="expenses_added")
    is_deleted = models.BooleanField(default=False)  # For Trash Page

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.date} - {self.category} - {self.amount}"