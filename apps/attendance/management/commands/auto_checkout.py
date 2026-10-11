from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.attendance.models import MemberAttendance
from datetime import timedelta

class Command(BaseCommand):
    help = 'Automatically checks out members who have been checked in for more than 2 hours.'

    def handle(self, *args, **options):
        two_hours_ago = timezone.now() - timedelta(hours=2)
        
        # Find attendance records for members who are still checked in
        # and whose check-in time is more than 2 hours ago.
        overdue_checkins = MemberAttendance.objects.filter(
            check_out_time__isnull=True,
            check_in_time__lte=two_hours_ago
        )

        count = 0
        for record in overdue_checkins:
            # Set the check-out time to 2 hours after the check-in time
            record.check_out_time = record.check_in_time + timedelta(hours=2)
            record.status = 'outside'
            record.save()
            count += 1

        self.stdout.write(self.style.SUCCESS(f'Successfully checked out {count} overdue members.'))