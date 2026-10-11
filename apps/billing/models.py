from django.db import models
from django.utils import timezone
from apps.members.models import Member, MembershipHistory, PersonalTrainer
from apps.superadmin.models import Gym

class Payment(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    PAYMENT_MODE_CHOICES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('credit_card', 'Credit Card'),
        ('debit_card', 'Debit Card'),
        ('net_banking', 'Net Banking'),
        ('other', 'Other'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    membership_history = models.ForeignKey(MembershipHistory, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    personal_trainer = models.ForeignKey(PersonalTrainer, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(default=timezone.now)
    payment_mode = models.CharField(max_length=50, choices=PAYMENT_MODE_CHOICES, default='cash')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    follow_up_date = models.DateField(blank=True, null=True)
    is_deleted = models.BooleanField(default=False)


    @property
    def is_subscription(self):
        return False