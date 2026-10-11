from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.members.models import Member
from apps.whatsapp.services import WhatsAppService
import logging

logger = logging.getLogger('apps.whatsapp')

class Command(BaseCommand):
    help = 'Sends WhatsApp birthday wishes to members whose birthday is today at 3 AM'

    def handle(self, *args, **options):
        today = timezone.now()
        current_year = today.year
        
        logger.info(f"🎂 Checking for birthdays on {today.strftime('%d-%m')}")

        # Find members whose birthday month and day match today
        # AND who haven't received a wish this year
        members = Member.objects.filter(
            date_of_birth__month=today.month,
            date_of_birth__day=today.day,
            is_deleted=False
        ).exclude(last_birthday_wish_sent_year=current_year).select_related('gym')

        whatsapp_service = WhatsAppService()
        count = 0

        for member in members:
            try:
                gym = member.gym
                if not gym:
                    continue
                
                # Check if gym has WhatsApp messaging enabled
                if not gym.whatsapp_enabled:
                    self.stdout.write(f"Skipping {member.name}: WhatsApp disabled for gym '{gym.name}'.")
                    continue
                
                self.stdout.write(f"🎉 Sending birthday wish to {member.name} ({member.mobile_number})")
                
                # 1:name, 2:gym_name, 3:contact, 4:logo
                # result = whatsapp_service.send_birthday_wishes(
                #     request=None,
                #     to_number=member.mobile_number,
                #     name=member.name,
                #     gym_name=gym.name,
                #     gym_contact_number=gym.phone or 'N/A',
                #     gym_logo_url=gym.logo.url if gym.logo else None
                # )
                
                # if result.get('success'):
                #     member.last_birthday_wish_sent_year = current_year
                #     member.save(update_fields=['last_birthday_wish_sent_year'])
                #     count += 1
                #     logger.info(f"✅ Birthday wish sent successfully to {member.name}")
                # else:
                #     logger.error(f"❌ Failed to send to {member.name}: {result.get('error')}")
                    
            except Exception as e:
                logger.error(f"💥 Error processing birthday for member {member.id}: {e}")

        self.stdout.write(self.style.SUCCESS(f'Successfully sent {count} birthday wishes today.'))