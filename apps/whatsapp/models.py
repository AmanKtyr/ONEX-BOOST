from django.db import models
from django.contrib.auth import get_user_model
import urllib.parse
from apps.superadmin.models import Gym

User = get_user_model()

class WhatsAppConfig(models.Model):
    gym = models.OneToOneField(Gym, on_delete=models.CASCADE, related_name='whatsapp_config')
    whatsapp_business_account_id = models.CharField(max_length=255, blank=True, null=True)
    phone_number_id = models.CharField(max_length=255, blank=True, null=True)
    access_token = models.CharField(max_length=255, blank=True, null=True)
    api_version = models.CharField(max_length=10, default='v19.0')

    def __str__(self):
        return f"WhatsApp Config for {self.gym.name}"


class WhatsAppMessageLog(models.Model):
    DIRECTION_CHOICES = (
        ('outbound', 'Sent / Outgoing'),
        ('inbound', 'Received / Incoming'),
    )

    STATUS_CHOICES = (
        ('sent', 'Sent / Delivered'),
        ('received', 'Received / Inbound'),
        ('failed', 'Failed / Not Sent'),
        ('pending', 'Pending'),
        ('sent_manually', 'Sent with Personal WhatsApp'),
    )

    MESSAGE_TYPE_CHOICES = (
        ('enquiry', 'Enquiry Follow-up'),
        ('broadcast', 'Broadcast Announcement'),
        ('lead', 'Website Lead Contact'),
        ('renewal', 'Subscription / Fee Renewal'),
        ('welcome', 'Welcome Onboarding'),
        ('reminder', 'General Reminder'),
        ('direct_chat', 'Direct Personal Chat'),
        ('inbound_reply', 'Incoming Customer Message'),
        ('custom', 'Custom Message'),
    )

    gym = models.ForeignKey(Gym, on_delete=models.SET_NULL, null=True, blank=True, related_name='whatsapp_logs')
    direction = models.CharField(max_length=15, choices=DIRECTION_CHOICES, default='outbound')
    recipient_name = models.CharField(max_length=150, help_text="Name of recipient or sender")
    recipient_phone = models.CharField(max_length=30, help_text="Phone number")
    recipient_type = models.CharField(max_length=50, blank=True, default="Lead/Contact")
    
    message_type = models.CharField(max_length=30, choices=MESSAGE_TYPE_CHOICES, default='custom')
    message_content = models.TextField(help_text="Message text sent or received")
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True, null=True, help_text="Failure reason if delivery failed")
    
    provider = models.CharField(max_length=50, default='twilio', help_text="e.g. twilio, personal_whatsapp")
    provider_message_id = models.CharField(max_length=150, blank=True, null=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_whatsapp_messages')
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "WhatsApp Message Log"
        verbose_name_plural = "WhatsApp Message Logs"

    def __str__(self):
        return f"[{self.direction.upper()}] {self.recipient_name} ({self.recipient_phone}) - {self.status}"

    @property
    def is_inbound(self):
        return self.direction == 'inbound' or self.status == 'received'

    @property
    def clean_phone(self):
        """Returns clean numeric phone digits for WhatsApp URL"""
        phone = ''.join(c for c in str(self.recipient_phone) if c.isdigit())
        if len(phone) == 10:
            phone = '91' + phone
        return phone

    @property
    def whatsapp_url(self):
        encoded_msg = urllib.parse.quote(self.message_content or '')
        return f"https://wa.me/{self.clean_phone}?text={encoded_msg}"

    @property
    def direct_chat_url(self):
        return f"https://wa.me/{self.clean_phone}"