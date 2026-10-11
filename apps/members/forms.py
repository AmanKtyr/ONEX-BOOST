from django import forms
from .models import Member, MedicalHistory, EmergencyContact, MembershipHistory, PersonalTrainer, AssignDietPlan, AssignWorkoutPlan
from apps.management.models import MembershipPlan, DietPlan, WorkoutPlan
from apps.trainers.models import Trainer
import re
from datetime import date
from django.utils import timezone

class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = [
            'first_name', 'last_name', 'mobile_number', 'relation', 'email', 'age', 'gender',
            'date_of_birth', 'profile_picture', 'address', 'state', 'city',
            'pincode', 'profession', 'sign', 'identity_type', 'identity_no',
            'identity_document_image'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your first name', 'style': 'text-transform: capitalize;'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your last name', 'style': 'text-transform: capitalize;'}),
            'mobile_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your mobile number', 'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57'}),
            'relation': forms.Select(attrs={'class': 'form-control', 'disabled': 'disabled'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'}),
            'age': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your age'}),
            'gender': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select your gender'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your date of birth'}),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control', 'placeholder': 'Upload your profile picture'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your address'}),
            'area': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your area'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your state'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your city'}),
            'pincode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your pincode'}),
            'profession': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your profession'}),
            'sign': forms.FileInput(attrs={'class': 'form-control'}),
            'identity_type': forms.Select(attrs={'class': 'form-control'}),
            'identity_no': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your identity number'}),
            'identity_document_image': forms.FileInput(attrs={'class': 'form-control'}),
        }
    def __init__(self, *args, **kwargs):
        super(MemberForm, self).__init__(*args, **kwargs)
        self.fields['profile_picture'].required = False
        self.fields['sign'].required = False
        self.fields['identity_type'].required = False
        self.fields['identity_no'].required = False
        self.fields['identity_document_image'].required = False
        self.fields['date_of_birth'].required = False


        required_fields = [
            'first_name',
            'last_name',
            'mobile_number',
            'gender',
        ]
        for field in required_fields:
            self.fields[field].required = True
            self.fields[field].label = f"{self.fields[field].label} *"

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if first_name:
            return first_name.title()
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if last_name:
            return last_name.title()
        return last_name

    def clean_mobile_number(self):
        mobile_number = self.cleaned_data.get('mobile_number')
        if mobile_number and (not mobile_number.isdigit() or len(mobile_number) != 10):
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        return mobile_number

    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture and 'profile_picture' in self.changed_data:
            if profile_picture.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image size must be no more than 2 MB.")
            allowed_types = ['image/jpeg', 'image/png']
            if profile_picture.content_type not in allowed_types:
                raise forms.ValidationError("Only JPEG and PNG images are allowed.")
        return profile_picture

    def clean_sign(self):
        sign = self.cleaned_data.get('sign')
        if sign and 'sign' in self.changed_data:
            if sign.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Image size must be no more than 2 MB.")
            allowed_types = ['image/jpeg', 'image/png']
            if sign.content_type not in allowed_types:
                raise forms.ValidationError("Only JPEG and PNG images are allowed.")
        return sign

    def clean_identity_document_image(self):
        identity_document_image = self.cleaned_data.get('identity_document_image')
        if identity_document_image and 'identity_document_image' in self.changed_data:
            # Validate file size (e.g., 2 MB limit)
            if identity_document_image.size > 2 * 1024 * 1024:
                raise forms.ValidationError("File size must be no more than 2 MB.")
            
            # Validate file type
            allowed_types = ['image/jpeg', 'image/png', 'application/pdf']
            if identity_document_image.content_type not in allowed_types:
                raise forms.ValidationError("Only JPEG, PNG, and PDF files are allowed.")
        return identity_document_image

    def clean_identity_no(self):
        identity_no = self.cleaned_data.get('identity_no')
        identity_type = self.cleaned_data.get('identity_type')

        if identity_type == 'aadhar_card':
            if not re.match(r'^\d{12}$', identity_no):
                raise forms.ValidationError("Aadhar Card number must be 12 digits.")
        elif identity_type == 'pan_card':
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', identity_no):
                raise forms.ValidationError("Invalid PAN Card number format.")
        elif identity_type == 'driving_license':
            if not re.match(r'^[A-Z]{2}[0-9]{2}[0-9]{4}[0-9]{7}$', identity_no):
                raise forms.ValidationError("Invalid Driving License number format.")
        return identity_no

    def clean_follow_up_date(self):
        follow_up_date = self.cleaned_data.get('follow_up_date')
        if follow_up_date and follow_up_date < date.today():
            raise forms.ValidationError("Follow-up date cannot be in the past.")
        return follow_up_date

    def clean(self):
        cleaned_data = super().clean()
        date_of_birth = cleaned_data.get("date_of_birth")
        if date_of_birth:
            today = date.today()
            age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
            cleaned_data["age"] = age
        return cleaned_data

class MedicalHistoryForm(forms.ModelForm):
    class Meta:
        model = MedicalHistory
        fields = ['condition', 'type', 'since']
        widgets = {
            'condition': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your condition'}),
            'type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your type'}),
            'since': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your since date'}),
        }
    def __init__(self, *args, **kwargs):
        super(MedicalHistoryForm, self).__init__(*args, **kwargs)
        self.fields['condition'].required = False
        self.fields['type'].required = False
        self.fields['since'].required = False

class EmergencyContactForm(forms.ModelForm):
    class Meta:
        model = EmergencyContact
        fields = ['name', 'mobile', 'relation']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your name' , 'style': 'text-transform: capitalize;'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your mobile number' , 'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57'}),
            'relation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your relation'}),
        }
    def __init__(self, *args, **kwargs):
        super(EmergencyContactForm, self).__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['mobile'].required = False
        self.fields['relation'].required = False


class MembershipHistoryForm(forms.ModelForm):
    class Meta:
        model = MembershipHistory
        fields = ['plan', 'registration_fee', 'membership_start_date', 'payment_date', 'add_on_days', 'discount', 'total_amount', 'paid_amount', 'payment_mode', 'comment', 'follow_up_date', 'transaction_id']
        widgets = {
            'plan': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select your plan'}),
            'registration_fee': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your registration fee'}),
            'membership_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your membership start date'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your payment date'}),
            'add_on_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your add on days'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your discount'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True, 'placeholder': 'Total amount'}),
            'paid_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your paid amount'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select your payment mode'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Enter your comment'}),
            'follow_up_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your follow up date'}),
            'transaction_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your transaction ID'}),
        }

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super(MembershipHistoryForm, self).__init__(*args, **kwargs)
        if gym:
            self.fields['plan'].queryset = MembershipPlan.objects.filter(gym=gym)
        
        # Set initial dates to local today if new instance
        if not self.instance.pk:
            self.fields['membership_start_date'].initial = timezone.localdate()
            self.fields['payment_date'].initial = timezone.localdate()

        self.fields['follow_up_date'].required = False
        self.fields['transaction_id'].required = False

    def clean(self):
        cleaned_data = super().clean()
        paid_amount = cleaned_data.get('paid_amount')
        total_amount = cleaned_data.get('total_amount')
        follow_up_date = cleaned_data.get('follow_up_date')

        if paid_amount is not None and total_amount is not None:
            if paid_amount < total_amount and not follow_up_date:
                self.add_error('follow_up_date', 'This field is required when the paid amount is less than the total amount.')
        
        return cleaned_data


class PersonalTrainerForm(forms.ModelForm):
    class Meta:
        model = PersonalTrainer
        fields = ['trainer', 'months', 'trainer_fee', 'gym_charges', 'pt_start_date', 'payment_date', 'discount', 'total_amount', 'paid_amount', 'payment_mode']
        widgets = {
            'trainer': forms.Select(attrs={'class': 'form-control'}),
            'months': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your months'}),
            'trainer_fee': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True, 'placeholder': 'Trainer fee'}),
            'gym_charges': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your gym charges'}),
            'pt_start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'placeholder': 'Select your pt start date'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your discount'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'readonly': True, 'placeholder': 'Total amount'}),
            'paid_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your paid amount'}),
            'payment_mode': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select your payment mode'}),
        }

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super(PersonalTrainerForm, self).__init__(*args, **kwargs)
        if gym:
            self.fields['trainer'].queryset = Trainer.objects.filter(gym=gym)
        
        # Set initial dates to local today if new instance
        if not self.instance.pk:
            self.fields['pt_start_date'].initial = timezone.localdate()
            self.fields['payment_date'].initial = timezone.localdate()


class AssignDietPlanForm(forms.ModelForm):
    class Meta:
        model = AssignDietPlan
        fields = ['diet_plan']

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['diet_plan'].queryset = DietPlan.objects.filter(gym=gym)


class AssignWorkoutPlanForm(forms.ModelForm):
    class Meta:
        model = AssignWorkoutPlan
        fields = ['workout_plan']

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['workout_plan'].queryset = WorkoutPlan.objects.filter(gym=gym)