from django.db import models

class WebsiteContactSubmission(models.Model):
    INQUIRY_CHOICES = [
        ('demo', 'Schedule a Demo'),
        ('pricing', 'Pricing Inquiry'),
        ('support', 'Technical Support'),
        ('partnership', 'Partnership Opportunity'),
        ('other', 'Other Inquiry'),
    ]

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    business_name = models.CharField(max_length=200)
    inquiry_type = models.CharField(max_length=20, choices=INQUIRY_CHOICES)
    referral_source = models.CharField(max_length=50, blank=True, null=True)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.business_name}"

    class Meta:
        ordering = ['-created_at']
