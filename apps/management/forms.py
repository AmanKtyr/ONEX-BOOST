from django import forms
from .models import DietPlan, MembershipPlan, WorkoutPlan
from ckeditor.widgets import CKEditorWidget

class WorkoutPlanForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorWidget(), required=False)
    class Meta:
        model = WorkoutPlan
        exclude = ['gym']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter workout plan name'}),
            'duration_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 30'}),
            'difficulty': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select difficulty'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'document': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,application/pdf'}),
            'created_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter creator name'}),
        }


class MembershipPlanForm(forms.ModelForm):
    class Meta:
        model = MembershipPlan
        exclude = ['gym']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your title'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your amount'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your discount'}),
            'duration': forms.Select(attrs={'class': 'form-control', 'placeholder': 'Select your duration'}),
            'add_on_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter your add-on days'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter your description'}),
        }

class DietPlanForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorWidget(), required=False)
    class Meta:
        model = DietPlan
        exclude = ['gym']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter diet plan name (e.g., Keto Diet)'}),
            'target': forms.Select(attrs={'class': 'form-control'}),
            'duration_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 30'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'document': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,application/pdf'}),
            'created_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter creator name (e.g., Dr. Smith)'}),
        }