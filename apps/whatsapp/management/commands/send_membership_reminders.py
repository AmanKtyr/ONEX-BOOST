import logging
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db.models import F
from apps.members.models import MembershipHistory, PersonalTrainer
from apps.whatsapp.services import WhatsAppService
from apps.superadmin.notifications import (
    notify_membership_expiring,
    notify_membership_expired,
    notify_pt_expiring
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sends membership and trainer expiry reminders via WhatsApp and in-app platform notifications."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate sending reminders without actually sending them or updating the database.',
        )

    def handle(self, *args, **options):
        today = date.today()
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Running in --dry-run mode for: {today}"))
        else:
            self.stdout.write(f"Running membership & trainer expiry reminders for: {today}")

        # ==========================================
        # 1. PROCESS MEMBERSHIP EXPIRY REMINDERS
        # ==========================================
        active_memberships = MembershipHistory.objects.filter(
            status='active',
            is_deleted=False
        ).select_related('member', 'gym', 'plan')

        total_membership_reminders = 0
        service = WhatsAppService()

        for membership in active_memberships:
            member = membership.member
            gym = membership.gym
            end_date = membership.get_end_date()
            if not end_date:
                continue

            days_until_expiry = (end_date - today).days

            try:
                # 4-Day Reminder
                if days_until_expiry == 4 and not membership.reminder_4_days_sent:
                    if dry_run:
                        self.stdout.write(f"(Dry-run) 4-day reminder for {member.name}")
                        total_membership_reminders += 1
                    else:
                        # In-App Platform Notification
                        notify_membership_expiring(member=member, history=membership, days_left=4)

                        # WhatsApp message
                        if gym and gym.whatsapp_enabled and member.mobile_number:
                            service.send_membership_expiring_soon(
                                request=None, to_number=member.mobile_number, name=member.name,
                                plan_name=membership.plan.title, expiry_date=end_date.strftime('%d/%m/%Y'),
                                gym_name=gym.name, gym_contact_number=gym.phone,
                                gym_logo_url=gym.logo.url if gym.logo else None
                            )

                        membership.reminder_4_days_sent = True
                        membership.save(update_fields=['reminder_4_days_sent'])
                        total_membership_reminders += 1
                        self.stdout.write(self.style.SUCCESS(f"Sent 4-day reminder to {member.name}"))

                # 2-Day Urgent Reminder
                elif days_until_expiry == 2 and not membership.reminder_2_days_sent:
                    if dry_run:
                        self.stdout.write(f"(Dry-run) 2-day reminder for {member.name}")
                        total_membership_reminders += 1
                    else:
                        # In-App Platform Notification
                        notify_membership_expiring(member=member, history=membership, days_left=2)

                        # WhatsApp message
                        if gym and gym.whatsapp_enabled and member.mobile_number:
                            service.send_membership_expiring_soon(
                                request=None, to_number=member.mobile_number, name=member.name,
                                plan_name=membership.plan.title, expiry_date=end_date.strftime('%d/%m/%Y'),
                                gym_name=gym.name, gym_contact_number=gym.phone,
                                gym_logo_url=gym.logo.url if gym.logo else None
                            )

                        membership.reminder_2_days_sent = True
                        membership.save(update_fields=['reminder_2_days_sent'])
                        total_membership_reminders += 1
                        self.stdout.write(self.style.SUCCESS(f"Sent 2-day reminder to {member.name}"))

                # Expiration Notice (Expired today or overdue)
                elif days_until_expiry <= 0 and not membership.expiry_notification_sent:
                    if dry_run:
                        self.stdout.write(f"(Dry-run) Expiry notification for {member.name}")
                        total_membership_reminders += 1
                    else:
                        # In-App Platform Notification
                        notify_membership_expired(member=member, history=membership)

                        # WhatsApp message
                        if gym and gym.whatsapp_enabled and member.mobile_number:
                            service.send_membership_expired(
                                request=None, to_number=member.mobile_number, name=member.name,
                                plan_name=membership.plan.title, expiry_date=end_date.strftime('%d/%m/%Y'),
                                gym_name=gym.name, gym_contact_number=gym.phone,
                                gym_logo_url=gym.logo.url if gym.logo else None
                            )

                        membership.expiry_notification_sent = True
                        membership.save(update_fields=['expiry_notification_sent'])
                        total_membership_reminders += 1
                        self.stdout.write(self.style.SUCCESS(f"Sent expiry notification to {member.name}"))

            except Exception as e:
                self.stderr.write(f"Error processing membership {membership.id}: {e}")

        # ==========================================
        # 2. PROCESS PERSONAL TRAINING EXPIRY REMINDERS
        # ==========================================
        active_pts = PersonalTrainer.objects.filter(
            status='active',
            is_deleted=False
        ).select_related('member', 'trainer', 'gym')

        total_pt_reminders = 0

        for pt in active_pts:
            member = pt.member
            trainer = pt.trainer
            end_date = pt.get_end_date()
            if not end_date:
                continue

            days_until_expiry = (end_date - today).days

            try:
                # 4-Day, 2-Day, or Expired PT Alerts
                if days_until_expiry in (4, 2, 0):
                    if dry_run:
                        self.stdout.write(f"(Dry-run) PT reminder ({days_until_expiry}d left) for {member.name} (Coach {trainer.name})")
                        total_pt_reminders += 1
                    else:
                        notify_pt_expiring(member=member, pt_assignment=pt, days_left=max(0, days_until_expiry))
                        total_pt_reminders += 1
                        self.stdout.write(self.style.SUCCESS(f"Sent PT reminder ({days_until_expiry}d left) for {member.name}"))

            except Exception as e:
                self.stderr.write(f"Error processing PT assignment {pt.id}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Finished processing reminders. Membership reminders: {total_membership_reminders}, PT reminders: {total_pt_reminders}"
            )
        )