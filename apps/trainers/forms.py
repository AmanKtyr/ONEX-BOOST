from django import forms
from .models import Trainer

class TrainerForm(forms.ModelForm):
    class Meta:
        model = Trainer
        fields = ['name', 'email', 'phone', 'address', 'joining_date', 'salary', 'personal_training_monthly_amount', 'specialization', 'photo', 'time_slot']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter full name', 'style': 'text-transform: capitalize;'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter email address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter phone number', 'required': True, 'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter address', 'rows': 3}),
            'joining_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'salary': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter salary'}),
            'personal_training_monthly_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter personal training monthly amount'}),
            'specialization': forms.Select(attrs={'class': 'form-control'}, choices=Trainer.SPECIALIZATION_CHOICES),
            'time_slot': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 9:00 AM - 11:00 AM'}),
            'photo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            return name.title()
        return name

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and (not phone.isdigit() or len(phone) != 10):
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        return phone