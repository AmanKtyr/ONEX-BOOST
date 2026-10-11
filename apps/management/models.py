from django.db import models
from apps.superadmin.models import Gym
from ckeditor.fields import RichTextField

class MembershipPlan(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    DURATION_CHOICES = [
        ('1_day', '1 Day'),
        ('1_week', '1 Week'),
        ('2_weeks', '2 Weeks'),
        ('1_month', '1 Month'),
        ('2_months', '2 Months'),
        ('3_months', '3 Months'),
        ('6_months', '6 Months'),
        ('9_months', '9 Months'),
        ('1_year', '1 Year'),
    ]

    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False, null=True, blank=True)
    duration = models.CharField(max_length=20, choices=DURATION_CHOICES, default='1_month')
    description = models.TextField(blank=True, null=True)
    add_on_days = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        self.offer_price = self.amount - self.discount
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

class DietPlan(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    TARGET_CHOICES = [
        ('weight_loss', 'Weight Loss'),
        ('muscle_gain', 'Muscle Gain'),
        ('maintenance', 'Maintenance'),
        ('fat_loss', 'Fat Loss'),
    ]

    name = models.CharField(max_length=100)
    target = models.CharField(max_length=20, choices=TARGET_CHOICES, default='weight_loss')
    duration_days = models.PositiveIntegerField(default=0)
    description = RichTextField(blank=True)
    image = models.ImageField(upload_to='diet_plans/', blank=True, null=True)
    document = models.FileField(upload_to='diet_plans/docs/', blank=True, null=True, help_text="Upload Image or PDF for Diet Plan Description")
    created_by = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

class WorkoutPlan(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    name = models.CharField(max_length=100)
    duration_days = models.PositiveIntegerField(default=30)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    image = models.ImageField(upload_to='workout_plans/', blank=True, null=True)
    document = models.FileField(upload_to='workout_plans/docs/', blank=True, null=True, help_text="Upload Image or PDF for Workout Plan Description")
    created_by = models.CharField(max_length=100, blank=True, null=True)
    description = RichTextField(blank=True)

    def __str__(self):
        return self.name