from django.db import models
from apps.superadmin.models import Gym

class Enquiry(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    ]

    SOURCE_CHOICES = [
        ('walk_in', 'Walk-in'),
        ('website', 'Website'),
        ('referral', 'Referral'),
        ('social_media', 'Social Media'),
        ('other', 'Other'),
    ]

    INTERESTED_IN_CHOICES = [
        ('gym', 'Gym'),
        ('zumba', 'Zumba'),
        ('personal_training', 'Personal Training'),
        ('yoga', 'Yoga'),
        ('crossfit', 'CrossFit'),
    ]

    STATUS_CHOICES = [
        ('follow_up', 'Follow-up'),
        ('converted', 'Converted'),
        ('lost', 'Lost'),
    ]

    name = models.CharField(max_length=100)
    mobile_number = models.CharField(max_length=10)
    email = models.EmailField(blank=True, null=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    enquiry_date = models.DateField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='walk_in')
    interested_in = models.CharField(max_length=20, choices=INTERESTED_IN_CHOICES, default='gym')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES , default='follow_up')
    next_follow_up_date = models.DateField(blank=True, null=True)
    # assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='enquiries')
    enquiry_note = models.TextField( null=True, blank=True)

    def __str__(self):
        return self.name

    def get_status_color_class(self):
        if self.status == 'follow_up':
            return 'badge-info'
        elif self.status == 'converted':
            return 'badge-success'
        elif self.status == 'lost':
            return 'badge-danger'
        return ''