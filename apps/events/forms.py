from django import forms
from .models import Event, EventParticipant

class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = '__all__'
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'registration_deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class EventParticipantForm(forms.ModelForm):
    GENDER_CHOICES = [
        ('Male', 'Male'),
        ('Female', 'Female'),
        ('Other', 'Other'),
    ]
    gender = forms.ChoiceField(
        choices=GENDER_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'radio radio-primary'}),
        required=False
    )
    IS_GYM_MEMBER_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]
    is_gym_member = forms.ChoiceField(
        choices=IS_GYM_MEMBER_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'radio radio-secondary'}),
        required=True
    )

    class Meta:
        model = EventParticipant
        exclude = ['event', 'registered_at', 'ip_address', 'status', 'payment_status', 'registration_source']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Enter your full name'}),
            'mobile_number': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': '+1 (555) 123-4567'}),
            'email': forms.EmailInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'your.email@example.com'}),
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'input input-bordered w-full'}),
            'current_gym_name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Gym or fitness center name'}),
            'fitness_level': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'years_of_training': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'placeholder': '0'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Contact person name'}),
            'emergency_contact_number': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Emergency phone number'}),
            'medical_conditions': forms.Textarea(attrs={'rows': 3, 'class': 'textarea textarea-bordered w-full', 'placeholder': 'List any medical conditions or allergies...'}),
            'injuries': forms.Textarea(attrs={'rows': 3, 'class': 'textarea textarea-bordered w-full', 'placeholder': 'List any recent or recurring injuries...'}),
            'payment_method': forms.Select(attrs={'class': 'select select-bordered w-full'}),
            'transaction_id': forms.TextInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Enter transaction ID or reference number'}),
            'payment_amount': forms.NumberInput(attrs={'class': 'input input-bordered w-full', 'placeholder': 'Amount paid'}),
            'payment_screenshot': forms.FileInput(attrs={'class': 'input input-bordered w-full'}),
        }

    def clean_payment_screenshot(self):
        payment_screenshot = self.cleaned_data.get('payment_screenshot')
        if payment_screenshot:
            if payment_screenshot.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image size must be no more than 2 MB.")
            allowed_types = ['image/jpeg', 'image/png']
            if payment_screenshot.content_type not in allowed_types:
                raise forms.ValidationError("Only JPEG and PNG images are allowed.")
        return payment_screenshot