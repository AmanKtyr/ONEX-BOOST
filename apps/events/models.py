from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from apps.superadmin.models import Gym


class Event(models.Model):
    class EventType(models.TextChoices):
        WORKOUT = 'Workout', _('Workout')
        SEMINAR = 'Seminar', _('Seminar')
        COMPETITION = 'Competition', _('Competition')
        OFFER = 'Offer', _('Offer')

    class EventStatus(models.TextChoices):
        UPCOMING = 'Upcoming', _('Upcoming')
        ONGOING = 'Ongoing', _('Ongoing')
        COMPLETED = 'Completed', _('Completed')
        DRAFT = 'Draft', _('Draft')
        PUBLISHED = 'Published', _('Published')

    event_name = models.CharField(max_length=255)
    event_type = models.CharField(
        max_length=20, choices=EventType.choices, default=EventType.WORKOUT)
    description = models.TextField(null=True, blank=True)
    banner_image = models.ImageField(
        upload_to='event_banners/', null=True, blank=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    trainer_name = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    max_participants = models.PositiveBigIntegerField()
    registration_deadline = models.DateTimeField()
    fee_amount =  models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=EventStatus.choices, default=EventStatus.UPCOMING)
    payment_qr_code = models.ImageField(
        upload_to='event_qr_codes/', null=True, blank=True)
    upi_id = models.CharField(max_length=50, null=True, blank=True)
    registered_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='registered_events', blank=True)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.event_name


class EventParticipant(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)
    is_gym_member = models.CharField(max_length=3, choices=(('Yes', 'Yes'), ('No', 'No')))
    current_gym_name = models.CharField(max_length=255, blank=True, null=True)
    fitness_level = models.CharField(max_length=20, choices=(('Beginner', 'Beginner'), ('Intermediate', 'Intermediate'), ('Advanced', 'Advanced'), ('Athlete', 'Athlete')), blank=True, null=True)
    years_of_training = models.PositiveIntegerField(blank=True, null=True)
    emergency_contact_name = models.CharField(max_length=255, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True, null=True)
    medical_conditions = models.TextField(blank=True, null=True)
    injuries = models.TextField(blank=True, null=True)
    consent = models.BooleanField(default=False)
    terms = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, choices=(('UPI', 'UPI'), ('Cash', 'Cash'), ('Card', 'Card'), ('Other', 'Other')), blank=True, null=True, default='UPI')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_screenshot = models.ImageField(upload_to='payment_screenshots/', null=True, blank=True)
    payment_status = models.CharField(max_length=20, default='Pending')
    registration_source = models.CharField(max_length=20, default='Public')
    registered_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    status = models.CharField(max_length=20, default='Registered')

    def __str__(self):
        return f'{self.full_name} - {self.event.event_name}'