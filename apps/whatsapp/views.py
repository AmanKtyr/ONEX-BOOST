# apps/whatsapp/views.py
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import json
import logging

# Import the singleton service instance
from .services import WhatsAppService

logger = logging.getLogger('apps.whatsapp')

@method_decorator(csrf_exempt, name='dispatch')
class TwilioWebhook(View):
    """
    Handles incoming webhook events from Twilio WhatsApp.
    Captures incoming messages from gym members/leads and records them as received messages.
    """
    def post(self, request):
        from django.utils import timezone
        from apps.whatsapp.models import WhatsAppMessageLog
        from apps.members.models import Member
        from apps.enquiry.models import Enquiry
        from apps.website.models import WebsiteContactSubmission
        from apps.superadmin.models import Gym

        data = request.POST
        from_raw = data.get('From', '')  # e.g. whatsapp:+919876543210
        body = data.get('Body', '')
        message_sid = data.get('MessageSid', '')
        
        # Clean phone digits
        phone_digits = ''.join(c for c in str(from_raw) if c.isdigit())
        phone_10 = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits

        sender_name = "Incoming WhatsApp Contact"
        sender_type = "Inbound Lead/Member"
        gym_obj = None

        # 1. Lookup in Member
        member = Member.objects.filter(mobile_number__icontains=phone_10).select_related('gym').first()
        if member:
            sender_name = member.name
            sender_type = "Gym Member"
            gym_obj = member.gym
        else:
            # 2. Lookup in Enquiry
            enquiry = Enquiry.objects.filter(mobile_number__icontains=phone_10).select_related('gym').first()
            if enquiry:
                sender_name = enquiry.name
                sender_type = "Gym Enquiry"
                gym_obj = enquiry.gym
            else:
                # 3. Lookup in Website Leads
                lead = WebsiteContactSubmission.objects.filter(phone__icontains=phone_10).first()
                if lead:
                    sender_name = f"{lead.first_name} {lead.last_name}"
                    sender_type = "Website Lead"
                else:
                    # 4. Lookup in Gyms
                    gym = Gym.objects.filter(phone__icontains=phone_10).first()
                    if gym:
                        sender_name = gym.name
                        sender_type = "Gym Admin"
                        gym_obj = gym

        # Save received message to log
        if body or from_raw:
            WhatsAppMessageLog.objects.create(
                gym=gym_obj,
                direction='inbound',
                status='received',
                recipient_name=sender_name,
                recipient_phone=phone_digits or from_raw,
                recipient_type=sender_type,
                message_type='inbound_reply',
                message_content=body,
                provider='twilio',
                provider_message_id=message_sid,
                sent_at=timezone.now()
            )
            logger.info(f"📥 Recorded Inbound WhatsApp Message from {sender_name} ({from_raw}): {body}")

        # Example auto-reply logic
        text = str(body).lower()
        if any(keyword in text for keyword in ['enquiry', 'interested', 'membership', 'hi', 'hello']):
            logger.info(f"Auto-replying to {from_raw} (Twilio) based on keywords.")
            whatsapp_service = WhatsAppService(gym_id=gym_obj.id if gym_obj else None)
            whatsapp_service.send_enquiry_confirmation(
                request=request,
                to_number=from_raw,
                name=sender_name,
                gym_name=gym_obj.name if gym_obj else "ONEX BOOST",
                gym_contact_number=gym_obj.phone if gym_obj else None
            )
            
        return HttpResponse('OK', status=200)

@method_decorator(csrf_exempt, name='dispatch')
class SendEnquiryConfirmationAPI(View):
    """
    An API endpoint to manually trigger the sending of an enquiry confirmation.
    Expects a JSON payload with 'phone_number' and optional 'name'.
    """
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            phone_number = data.get('phone_number')
            name = data.get('name', 'Valued Customer')
            
            if not phone_number:
                return JsonResponse({'error': 'phone_number is required'}, status=400)
            
            whatsapp_service = WhatsAppService()
            result = whatsapp_service.send_enquiry_confirmation(
                request=request,
                to_number=phone_number,
                name=name,
                gym_name="ONEX BOOST",
                gym_contact_number=None
            )
            
            if result.get('success'):
                return JsonResponse(result)
            else:
                return JsonResponse(result, status=500)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"API Error sending confirmation: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class SendTestMessage(View):
    """API endpoint to send test message"""
    
    def post(self, request):
        try:
            if not request.body:
                return JsonResponse({'error': 'Empty request body'}, status=400)
            
            data = json.loads(request.body)
            
            phone_number = data.get('phone_number')
            message = data.get('message', 'Test message from ONEX BOOST GYM')
            
            if not phone_number:
                return JsonResponse({'error': 'Phone number required'}, status=400)
            
            whatsapp_service = WhatsAppService()
            result = whatsapp_service.send_test_message(phone_number, message)
            
            if result.get('success'):
                return JsonResponse({
                    'success': True,
                    'message': 'Test message sent',
                    'message_id': result.get('message_id')
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': result.get('error')
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error: {e}")
            return JsonResponse({'error': str(e)}, status=500)

class WhatsAppHealthCheck(View):
    """Simplified health check for Twilio"""
    
    def get(self, request):
        whatsapp_service = WhatsAppService()
        initialized = whatsapp_service.twilio.client is not None
        
        return JsonResponse({
            'status': 'healthy' if initialized else 'degraded',
            'backend': 'twilio',
            'connected': initialized
        })