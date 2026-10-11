from django import forms

from .models import WebsiteContactSubmission


class WebsiteContactSubmissionForm(forms.ModelForm):
    class Meta:
        model = WebsiteContactSubmission
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone',
            'business_name',
            'inquiry_type',
            'referral_source',
            'message',
        )

    def clean_first_name(self):
        return self.cleaned_data['first_name'].strip()

    def clean_last_name(self):
        return self.cleaned_data['last_name'].strip()

    def clean_phone(self):
        return self.cleaned_data['phone'].strip()

    def clean_business_name(self):
        return self.cleaned_data['business_name'].strip()

    def clean_referral_source(self):
        referral_source = self.cleaned_data.get('referral_source')
        return referral_source.strip() if referral_source else None

    def clean_message(self):
        return self.cleaned_data['message'].strip()
