from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth.models import User
from decimal import Decimal
import random
from apps.superadmin.models import Gym

class Trainer(models.Model):
    SPECIALIZATION_CHOICES = [

        # ===== TRAINING SPECIALIZATIONS =====
        ('CROSSFIT', 'CrossFit Trainer'),
        ('PT', 'Personal Trainer'),
        ('ST', 'Strength Training Coach'),
        ('WL', 'Weight Loss Specialist'),
        ('MB', 'Muscle Building Coach'),
        ('FT', 'Functional Training Coach'),
        ('HIIT', 'HIIT Trainer'),
        ('YOGA', 'Yoga Instructor'),
        ('ZUMBA', 'Zumba Instructor'),
        ('CARDIO', 'Cardio Trainer'),
        ('CALISTHENICS', 'Calisthenics Coach'),
        ('MARTIAL', 'Martial Arts Trainer'),
        ('BOXING', 'Boxing Coach'),
        ('PILATES', 'Pilates Instructor'),

        # ===== MEDICAL / WELLNESS =====
        ('REHAB', 'Rehabilitation Specialist'),
        ('PHYSIO', 'Physiotherapist'),
        ('NUTRITION', 'Nutrition Coach / Dietitian'),
        ('SPORTS_DOC', 'Sports Doctor'),
        ('THERAPIST', 'Sports Therapist'),

        # ===== MANAGEMENT / ADMIN =====
        ('GYM_MANAGER', 'Gym Manager'),
        ('BRANCH_MANAGER', 'Branch Manager'),
        ('ADMIN', 'Administrator'),
        ('HR', 'HR Manager'),
        ('ACCOUNTS', 'Accounts Manager'),

        # ===== SALES / FRONT DESK =====
        ('SALES', 'Sales Executive'),
        ('COUNSELLOR', 'Fitness Counsellor'),
        ('FRONT_DESK', 'Front Desk Executive'),
        ('RECEPTIONIST', 'Receptionist'),

        # ===== SUPPORT STAFF =====
        ('MAINTENANCE', 'Maintenance Staff'),
        ('HOUSEKEEPING', 'Housekeeping Staff'),
        ('SECURITY', 'Security Guard'),

        ('OTHER', 'Other'),
    ]

    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='trainer_profile')
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    trainer_id = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=10, blank=True, null=True)
    address = models.TextField(blank=True)
    joining_date = models.DateField(default=timezone.now)
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    personal_training_monthly_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    specialization = models.CharField(max_length=100, choices=SPECIALIZATION_CHOICES, default='CROSSFIT')
    time_slot = models.CharField(max_length=100, blank=True, null=True)
    photo = models.ImageField(upload_to='trainers/photos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def create_or_update_user_account(self, raw_password=None):
        """
        Creates or updates a Django User account linked to this Trainer.
        Returns (user, raw_password).
        """
        from django.contrib.auth.models import User
        if not raw_password:
            phone_suffix = self.phone[-4:] if self.phone and len(self.phone) >= 4 else '1234'
            raw_password = f"Fit@{phone_suffix}"

        username = self.trainer_id
        if not self.user:
            user = User.objects.filter(username=username).first()
            if not user:
                user = User(username=username)
            names = (self.name or '').strip().split(' ', 1)
            user.first_name = names[0]
            user.last_name = names[1] if len(names) > 1 else ''
            user.email = self.email or ''
            user.set_password(raw_password)
            user.save()
            self.user = user
            self.save(update_fields=['user'])
        else:
            if raw_password:
                self.user.set_password(raw_password)
            names = (self.name or '').strip().split(' ', 1)
            self.user.first_name = names[0]
            self.user.last_name = names[1] if len(names) > 1 else ''
            if self.email:
                self.user.email = self.email
            self.user.save()

        return self.user, raw_password

    @property
    def pt_monthly_rate(self):
        return self.personal_training_monthly_amount or Decimal('0.00')

    class Meta:
        unique_together = [['gym', 'phone'], ['gym', 'email']]

@receiver(pre_save, sender=Trainer)
def create_trainer_id(sender, instance, **kwargs):
    if not instance.trainer_id:
        gym_id_part = "GD"  # Default value
        if instance.gym and instance.gym.gym_id_prefix:
            gym_id_part = instance.gym.gym_id_prefix

        present_year = timezone.now().strftime('%y')
        random_number = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        instance.trainer_id = f"{gym_id_part}-TRN-{present_year}-{random_number}"


class TrainerSalary(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft / Review'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ]
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer (NEFT/IMPS)'),
        ('upi', 'UPI / GPay / PhonePe'),
        ('cheque', 'Cheque'),
        ('other', 'Other'),
    ]

    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='trainer_salaries')
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='salary_records')
    month = models.PositiveSmallIntegerField()  # 1 - 12
    year = models.PositiveSmallIntegerField()   # e.g. 2026

    # Base configuration & calendar
    base_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_days = models.PositiveSmallIntegerField(default=30)

    # Attendance Breakdown
    present_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    half_days = models.PositiveSmallIntegerField(default=0)
    paid_leave_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    unpaid_leave_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    absent_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)
    payable_days = models.DecimalField(max_digits=5, decimal_places=1, default=0.0)

    # Financial breakdown
    base_salary_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    pt_clients_count = models.PositiveIntegerField(default=0)
    pt_commission = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    bonus = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    payment_date = models.DateField(null=True, blank=True)
    payment_mode = models.CharField(max_length=30, choices=PAYMENT_MODE_CHOICES, blank=True, null=True)
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_earnings(self):
        return (self.base_salary_earned or Decimal('0.00')) + (self.pt_commission or Decimal('0.00')) + (self.bonus or Decimal('0.00'))

    @property
    def total_deductions(self):
        return self.deductions or Decimal('0.00')

    class Meta:
        unique_together = ('trainer', 'month', 'year')
        ordering = ['-year', '-month', 'trainer__name']

    def __str__(self):
        return f"{self.trainer.name} - {self.month}/{self.year} (₹{self.net_salary})"