from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.members.models import MembershipHistory
from apps.whatsapp.services import WhatsAppService
import logging

logger = logging.getLogger('apps.whatsapp')

class Command(BaseCommand):
    help = 'Sends WhatsApp notifications for memberships expiring today, or in 2/4 days. (at 10 AM refers to intended schedule)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the script without sending real WhatsApp messages or updating database records.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run')
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE: No messages will be sent, no records updated."))

        today = timezone.localdate()
        date_plus_2 = today + timedelta(days=2)
        date_plus_4 = today + timedelta(days=4)
        
        logger.info(f"Running Membership Notifications for {today} (Dry run: {dry_run})")
        whatsapp_service = WhatsAppService()
        
        # 1. Process EXPIRED TODAY (Target date is TODAY)
        # These are memberships whose end date is TODAY.
        self.stdout.write(f"Processing expiry notices (for {today})...")
        expired_count = self.process_notifications(
            target_date=today,
            tracking_field='expiry_notification_sent',
            notification_type='expired',
            whatsapp_service=whatsapp_service,
            dry_run=dry_run
        )
        
        # 2. Process EXPIRING IN 2 DAYS
        self.stdout.write(f"Processing expiring soon notices (in 2 days: {date_plus_2})...")
        soon_2_count = self.process_notifications(
            target_date=date_plus_2,
            tracking_field='reminder_2_days_sent',
            notification_type='soon',
            whatsapp_service=whatsapp_service,
            dry_run=dry_run
        )
        
        # 3. Process EXPIRING IN 4 DAYS
        self.stdout.write(f"Processing expiring soon notices (in 4 days: {date_plus_4})...")
        soon_4_count = self.process_notifications(
            target_date=date_plus_4,
            tracking_field='reminder_4_days_sent',
            notification_type='soon',
            whatsapp_service=whatsapp_service,
            dry_run=dry_run
        )

        message = f'Summary: Expired Today: {expired_count}, 2-day reminder: {soon_2_count}, 4-day reminder: {soon_4_count}'
        if dry_run:
            message = f"[DRY RUN] {message}"
        self.stdout.write(self.style.SUCCESS(message))
        logger.info(f"Done: {message}")

    def process_notifications(self, target_date, tracking_field, notification_type, whatsapp_service, dry_run=False):
        """
        Generic processor for different types of membership notifications.
        """
        # Optimized queryset: select_related for M2O, prefetch_related for O2M (freezes)
        queryset = MembershipHistory.objects.filter(
            **{tracking_field: False},
            is_deleted=False
        ).select_related('member', 'gym', 'plan').prefetch_related('freezes')

        # For reminders, only target currently active plans
        if notification_type == 'soon':
            memberships = queryset.filter(status='active')
        else:
            # For "expired", we can target both active or already inactive (if just marked)
            memberships = queryset.filter(status__in=['active', 'inactive'])

        count = 0
        current_today = timezone.localdate()

        for membership in memberships:
            try:
                # Calculate expiry date including freeze days etc
                membership_expiry = membership.get_end_date()
                
                if membership_expiry == target_date:
                    member = membership.member
                    gym = membership.gym

                    # RENEWAL CHECK: Before sending, see if a newer, active plan exists for this member.
                    # A newer plan indicates the member has already renewed.
                    has_newer_active_plan = MembershipHistory.objects.filter(
                        member=member,
                        status='active',
                        start_date__gt=membership.start_date
                    ).exists()

                    if has_newer_active_plan:
                        logger.info(f"SKIPPING {notification_type} for {member.name} (ID: {member.id}) because they have a newer, active plan.")
                        # Mark as processed even if skipped, to avoid re-processing.
                        if not dry_run:
                            setattr(membership, tracking_field, True)
                            membership.save(update_fields=[tracking_field])
                        continue
                    
                    if not member.mobile_number:
                        logger.warning(f"SKIPPING {member.name}: No mobile number.")
                        continue

                    # Check if gym has WhatsApp messaging enabled
                    if not gym.whatsapp_enabled:
                        logger.info(f"SKIPPING {member.name}: WhatsApp messaging is disabled for gym '{gym.name}'.")
                        continue

                    if dry_run:
                        self.stdout.write(f"   [DRY RUN] Would send {notification_type} to {member.name} ({member.mobile_number})")
                        count += 1
                        continue

                    if notification_type == 'expired':
                        result = whatsapp_service.send_membership_expired(
                            request=None,
                            to_number=member.mobile_number,
                            name=member.name,
                            plan_name=membership.plan.title,
                            expiry_date=membership_expiry.strftime('%d/%m/%Y'),
                            gym_name=gym.name,
                            gym_contact_number=gym.phone or 'N/A',
                            gym_logo_url=gym.logo.url if gym.logo and hasattr(gym.logo, 'url') else None
                        )
                        # Mark as inactive if it was still active
                        if result.get('success') and membership.status == 'active':
                            membership.status = 'inactive'
                            # We'll save this along with the tracking field update
                    else: # 'soon'
                        result = whatsapp_service.send_membership_expiring_soon(
                            request=None,
                            to_number=member.mobile_number,
                            name=member.name,
                            plan_name=membership.plan.title,
                            expiry_date=membership_expiry.strftime('%d/%m/%Y'),
                            gym_name=gym.name,
                            gym_contact_number=gym.phone or 'N/A',
                            gym_logo_url=gym.logo.url if gym.logo and hasattr(gym.logo, 'url') else None
                        )
                    
                    if result.get('success'):
                        setattr(membership, tracking_field, True)
                        # Ensure we save both status and tracking field if needed
                        update_fields = [tracking_field]
                        if notification_type == 'expired' and membership.status == 'inactive':
                            update_fields.append('status')
                            
                        membership.save(update_fields=update_fields)
                        count += 1
                        logger.info(f"SUCCESS: {notification_type} notice sent to {member.name} for date {target_date}")
                    else:
                        logger.error(f"FAILED: Failed to send to {member.name}: {result.get('error')}")
            except Exception as e:
                logger.error(f"ERROR: Error processing membership {membership.id}: {e}", exc_info=True)
        
        return count