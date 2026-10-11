from django import forms
from .models import Payment
from datetime import date

class PaymentForm(forms.ModelForm):
    invoice_type = forms.CharField(widget=forms.HiddenInput())
    invoice_id = forms.IntegerField(widget=forms.HiddenInput())

    class Meta:
        model = Payment
        fields = ['invoice_type', 'invoice_id', 'amount', 'payment_mode', 'transaction_id', 'comment', 'follow_up_date']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter amount paid', 'step': '0.01'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter transaction ID'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter any comments'}),
            'follow_up_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.due_amount = kwargs.pop('due_amount', None)
        super().__init__(*args, **kwargs)
        self.fields['follow_up_date'].required = False
        self.fields['transaction_id'].required = False

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount is not None:
            if amount < 1:
                raise forms.ValidationError('Amount paid must be at least 1 rupee.')
            if self.due_amount is not None and amount > self.due_amount:
                raise forms.ValidationError(f'Amount paid cannot be greater than the due amount of {self.due_amount}.')
        return amount

    def clean_follow_up_date(self):
        follow_up_date = self.cleaned_data.get('follow_up_date')
        if follow_up_date and follow_up_date < date.today():
            raise forms.ValidationError("Follow-up date cannot be in the past.")
        return follow_up_date

    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        follow_up_date = cleaned_data.get('follow_up_date')

        if amount is not None and self.due_amount is not None and amount < self.due_amount and not follow_up_date:
            self.add_error('follow_up_date', 'This field is required when the paid amount is less than the due amount.')
        
        return cleaned_data