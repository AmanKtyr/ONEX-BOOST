import os
import sys
from io import StringIO
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

from apps.members.models import Member, MembershipHistory
from apps.management.models import MembershipPlan
from apps.superadmin.models import Gym


class Command(BaseCommand):
    help = 'Runs the whatsapp notifications test script.'

    def handle(self, *args, **options):
        self.stdout.write("Setting up test data...")
        self.setup_test_data()
        self.stdout.write("Running test...")
        self.run_test()
        self.stdout.write("Cleaning up test data...")
        self.cleanup_test_data()

    def setup_test_data(self):
        """Creates the necessary objects for testing."""
        today = timezone.now().date()
        # Create a dummy Gym
        gym, _ = Gym.objects.get_or_create(name="Test Gym", defaults={"gym_id_prefix": "TTG"})

        # Create a dummy MembershipPlan
        plan, _ = MembershipPlan.objects.get_or_create(
            title="Test Plan",
            defaults={"amount": 100, "duration": "30_days"}
        )

        # --- Test Case 1: Membership Expired Today ---
        member_expired, _ = Member.objects.get_or_create(
            mobile_number="+919999999991",
            defaults={"first_name": "Test User", "last_name": "Expired", "gym": gym}
        )
        MembershipHistory.objects.create(
            member=member_expired, plan=plan, gym=gym, membership_start_date=today - timedelta(days=30),
            total_amount=100, paid_amount=100, status='active',
            # This membership expired today relative to a 30-day plan
            reminder_4_days_sent=True, # Assume previous reminders were sent
            reminder_2_days_sent=True,
            expiry_notification_sent=False # Crucial: not yet sent
        )

        # --- Test Case 2: Membership Expiring in 2 Days ---
        member_expiring_2, _ = Member.objects.get_or_create(
            mobile_number="+919999999992",
            defaults={"first_name": "Test User", "last_name": "2 Days", "gym": gym}
        )
        MembershipHistory.objects.create(
            member=member_expiring_2, plan=plan, gym=gym, membership_start_date=today - timedelta(days=28), # 30-day plan, expires in 2 days
            total_amount=100, paid_amount=100, status='active',
            reminder_4_days_sent=True, # Assume 4-day reminder was sent
            reminder_2_days_sent=False, # Crucial: 2-day not yet sent
            expiry_notification_sent=False
        )

        # --- Test Case 3: Membership Expiring in 4 Days ---
        member_expiring_4, _ = Member.objects.get_or_create(
            mobile_number="+919999999993",
            defaults={"first_name": "Test User", "last_name": "4 Days", "gym": gym}
        )
        MembershipHistory.objects.create(
            member=member_expiring_4, plan=plan, gym=gym, membership_start_date=today - timedelta(days=26), # 30-day plan, expires in 4 days
            total_amount=100, paid_amount=100, status='active',
            reminder_4_days_sent=False, # Crucial: 4-day not yet sent
            reminder_2_days_sent=False,
            expiry_notification_sent=False
        )

    def run_test(self):
        """Runs the management command in dry-run mode and checks the output."""
        out = StringIO()
        call_command('send_membership_reminders', '--dry-run', stdout=out)
        output = out.getvalue()

        self.stdout.write("\n--- Command Output ---")
        self.stdout.write(output)
        self.stdout.write("----------------------\n")

        # Verification checks
        expired_check = "(Dry-run) Would send expiry notification to Test User Expired" in output
        soon_2_day_check = "(Dry-run) Would send 2-day reminder to Test User 2 Days" in output
        soon_4_day_check = "(Dry-run) Would send 4-day reminder to Test User 4 Days" in output

        if expired_check:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] ✅ Expired Today logic verified."))
        else:
            self.stdout.write(self.style.ERROR("[FAILURE] ❌ Expired Today logic failed."))

        if soon_2_day_check:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] ✅ 2-Day Reminder logic verified."))
        else:
            self.stdout.write(self.style.ERROR("[FAILURE] ❌ 2-Day Reminder logic failed."))

        if soon_4_day_check:
            self.stdout.write(self.style.SUCCESS("[SUCCESS] ✅ 4-Day Reminder logic verified."))
        else:
            self.stdout.write(self.style.ERROR("[FAILURE] ❌ 4-Day Reminder logic failed."))

    def cleanup_test_data(self):
        """Deletes the objects created for testing."""
        Member.objects.filter(first_name="Test User").delete()
        Gym.objects.filter(name="Test Gym").delete()
        MembershipPlan.objects.filter(title="Test Plan").delete()