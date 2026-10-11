from django import forms
from .models import PaymentSetting

class PaymentSettingForm(forms.ModelForm):
    class Meta:
        model = PaymentSetting
        fields = ['bank_name', 'account_holder_name', 'account_number', 'ifsc_code', 'qr_code']
        widgets = {
            'qr_code': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.required = False
            if field_name != 'qr_code':
                field.widget.attrs.update({'class': 'form-control'})
        
        if 'bank_name' in self.fields:
            self.fields['bank_name'].widget.attrs['placeholder'] = 'e.g. HDFC Bank, State Bank of India'
        if 'account_holder_name' in self.fields:
            self.fields['account_holder_name'].widget.attrs['placeholder'] = 'e.g. ONEXIVA Fitness Hub / John Doe'
        if 'account_number' in self.fields:
            self.fields['account_number'].widget.attrs['placeholder'] = 'e.g. 50100234567890'
        if 'ifsc_code' in self.fields:
            self.fields['ifsc_code'].widget.attrs['placeholder'] = 'e.g. HDFC0001234'