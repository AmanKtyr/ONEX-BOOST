from django.db import models
from django.contrib.auth.models import User
from apps.superadmin.models import Gym

ROLE_CHOICES = [ 
    ('admin', 'Admin'), 
    ('subadmin', 'Sub Admin'), 
    ('front_desk', 'Front Desk'), 
    ('trainer', 'Trainer'), 
    ('manager', 'Manager'), 
    ('accounts', 'Accounts'), 
    ('inventory', 'Inventory Manager'), 
    ('marketing', 'Marketing / CRM'), 
] 

class SubAdmin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='subadmin')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='subadmin_photos/', blank=True, null=True)
    
    def __str__(self):
        return self.user.username


class SubAdminPermission(models.Model):
    sub_admin = models.ForeignKey(SubAdmin, on_delete=models.CASCADE, related_name='permissions')
    permission_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.sub_admin.user.username} - {self.permission_name}"