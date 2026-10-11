from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Renames the duration column to duration_months in the superadmin_subscriptionplan table'

    def handle(self, *args, **kwargs):
        with connection.cursor() as cursor:
            try:
                cursor.execute("ALTER TABLE superadmin_subscriptionplan RENAME COLUMN duration TO duration_months")
                self.stdout.write(self.style.SUCCESS('Successfully renamed duration column to duration_months'))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error renaming column: {e}'))