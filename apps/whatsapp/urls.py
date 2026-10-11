# apps/whatsapp/urls.py
from django.urls import path
from .views import TwilioWebhook, SendEnquiryConfirmationAPI

urlpatterns = [
    # Webhook for receiving WhatsApp messages and events
    path('twilio-webhook/', TwilioWebhook.as_view(), name='twilio_webhook'),
    
    # API endpoint for sending an enquiry confirmation
    path('api/send-enquiry-confirmation/', SendEnquiryConfirmationAPI.as_view(), name='send_enquiry_confirmation_api'),
]