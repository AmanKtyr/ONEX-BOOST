from django.db import models
from apps.members.models import Member
from apps.trainers.models import Trainer
from apps.superadmin.models import Gym

from django.utils import timezone

class MemberAttendance(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='attendance_records')
    check_in_time = models.DateTimeField(default=timezone.now)
    check_out_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=[('inside', 'Inside'), ('outside', 'Outside')], default='inside')

    def __str__(self):
        return f"{self.member.first_name} {self.member.last_name} - {self.check_in_time.date()}"

    @property
    def duration(self):
        if self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f'{hours}h {minutes}m'
        return None

class TrainerLeave(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='leave_records')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[('approved', 'Approved'), ('pending', 'Pending'), ('rejected', 'Rejected')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    leave_type = models.CharField(max_length=50, choices=[
        ('sick', 'Sick Leave'),
        ('casual', 'Casual Leave'),
        ('earned', 'Earned Leave'),
        ('half_day', 'Half Day Leave'),
        ('maternity', 'Maternity Leave'),
        ('paternity', 'Paternity Leave'),
        ('unpaid', 'Unpaid Leave'),
        ('other', 'Other')
    ], default='casual')
    is_half_day = models.BooleanField(default=False)
    half_day_period = models.CharField(max_length=20, choices=[
        ('first_half', 'First Half'),
        ('second_half', 'Second Half')
    ], blank=True, null=True)
    is_paid = models.BooleanField(default=True)
    admin_notes = models.TextField(blank=True, null=True)
    
    @property
    def duration_days(self):
        if self.is_half_day:
            return 0.5
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.trainer.name} - {self.start_date} to {self.end_date}"

class MemberLeave(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='leave_records')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[('approved', 'Approved'), ('pending', 'Pending'), ('rejected', 'Rejected')], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    leave_type = models.CharField(max_length=50, choices=[
        ('sick', 'Sick Leave'),
        ('casual', 'Casual Leave'),
        ('medical', 'Medical Leave'),
        ('personal', 'Personal Leave'),
        ('other', 'Other')
    ], default='casual')
    admin_notes = models.TextField(blank=True, null=True)
    
    @property
    def duration_days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return f"{self.member.first_name} {self.member.last_name} - {self.start_date} to {self.end_date}"

class TrainerAttendance(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='attendance_records')
    check_in_time = models.DateTimeField(default=timezone.now)
    check_out_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=[('inside', 'Inside'), ('outside', 'Outside')], default='inside')

    def __str__(self):
        return f"{self.trainer.name} - {self.check_in_time.date()}"

    @property
    def duration(self):
        if self.check_out_time:
            delta = self.check_out_time - self.check_in_time
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f'{hours}h {minutes}m'
        return None