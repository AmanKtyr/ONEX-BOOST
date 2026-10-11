from django import forms
from .models import Expense
from django.utils import timezone
from django.core.exceptions import ValidationError

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        exclude = ['added_by', 'is_deleted', 'gym']
        widgets = {
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'category': forms.Select(attrs={'class': 'form-control ', 'placeholder': 'Select category'}),        
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter amount'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter description'}),
            'vendor_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter vendor name', 'style': 'text-transform: capitalize;'}),
            'vendor_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter vendor phone', 'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57'}),
            'vendor_bill_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter vendor bill number'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select payment mode'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter transaction ID'}),
            'receipt_image': forms.FileInput(attrs={'class': 'form-control', 'placeholder': 'Upload receipt image'}),
        }

    def clean_date(self):
        date = self.cleaned_data.get('date')
        if date and date > timezone.now().date():
            raise ValidationError("Date cannot be in the future.")
        return date

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount and amount <= 0:
            raise ValidationError("Amount must be a positive number.")
        return amount

    def clean_vendor_name(self):
        vendor_name = self.cleaned_data.get('vendor_name')
        if vendor_name:
            return vendor_name.title()
        return vendor_name

    def clean_vendor_phone(self):
        vendor_phone = self.cleaned_data.get('vendor_phone')
        if vendor_phone and (not vendor_phone.isdigit() or len(vendor_phone) != 10):
            raise ValidationError("Enter a valid 10-digit mobile number.")
        return vendor_phone

    def clean(self):
        cleaned_data = super().clean()
        payment_mode = cleaned_data.get('payment_mode')
        transaction_id = cleaned_data.get('transaction_id')

        if payment_mode != 'cash' and not transaction_id:
            self.add_error('transaction_id', "Transaction ID is required for non-cash payments.")
        
        return cleaned_data