import logging
import json
from django.conf import settings
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logger = logging.getLogger('apps.whatsapp')

class TwilioWhatsAppService:
    """
    Twilio-specific WhatsApp service implementation.
    Restored based on log patterns and system requirements.
    """
    
    def __init__(self, gym_id=None):
        self.account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        self.auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        self.from_number = getattr(settings, 'TWILIO_WHATSAPP_NUMBER', None)
        self.content_sid = getattr(settings, 'TWILIO_CONTENT_SID', None)
        
        self.client = None
        if self.account_sid and self.auth_token and self.auth_token != 'YOUR_TWILIO_AUTH_TOKEN':
            try:
                self.client = Client(self.account_sid, self.auth_token)
                logger.info(f"🚀 Twilio WhatsApp Service initialized for gym: {gym_id if gym_id else 'platform'}")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Twilio client: {e}")
        else:
            logger.warning("⚠️ Twilio credentials missing or placeholder in settings.")

    def format_phone_number(self, phone_number):
        """
        Formats a phone number to Twilio's expected whatsapp:+[country][number] format.
        """
        cleaned = str(phone_number).strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not cleaned.startswith('+'):
            if len(cleaned) == 10:
                cleaned = '+91' + cleaned  # Default for India
            elif not cleaned.startswith('whatsapp:'):
                cleaned = '+' + cleaned
        
        formatted = f"whatsapp:{cleaned}" if not cleaned.startswith('whatsapp:') else cleaned
        logger.debug(f"📞 Formatted phone number: {phone_number} -> {formatted}")
        return formatted

    def send_template_message(self, to_number, content_sid=None, content_variables=None, media_url=None, lang_code='en', attempts=3):
        """
        Sends a template message using Twilio Content API.
        """
        if not self.client:
            return {'success': False, 'error': 'Twilio client not initialized'}

        to_formatted = self.format_phone_number(to_number)
        sid = content_sid or self.content_sid
        
        if not sid:
            return {'success': False, 'error': 'Content SID (template) not provided'}

        # Twilio Content API requires compact JSON for content_variables
        if content_variables and isinstance(content_variables, dict):
            try:
                content_variables = json.dumps(content_variables, separators=(',', ':'))
            except Exception as e:
                logger.error(f"Failed to serialize content_variables: {e}")

        for attempt in range(1, attempts + 1):
            try:
                logger.info(f"📤 Sending template message (attempt {attempt}): to={to_formatted}, content_sid={sid}")
                
                # Use ONLY the parameters that worked in the script
                message = self.client.messages.create(
                    from_=self.from_number,
                    to=to_formatted,
                    content_sid=sid,
                    content_variables=content_variables
                )
                
                logger.info(f"✅ Template message sent successfully! SID: {message.sid}")
                return {
                    'success': True,
                    'message_id': message.sid,
                    'status': message.status
                }
            
            except TwilioRestException as e:
                logger.error(f"❌ Twilio API error (attempt {attempt}): {e.msg} (Code: {e.code})")
                if attempt == attempts:
                    return {'success': False, 'error': str(e.msg), 'code': e.code}
            except Exception as e:
                logger.error(f"❌ Unexpected error (attempt {attempt}): {e}")
                if attempt == attempts:
                    return {'success': False, 'error': str(e)}
        
        return {'success': False, 'error': 'Unknown failure after retries'}

    def send_text_message(self, to_number, message_text):
        """
        Sends a standard freeform WhatsApp text message via Twilio API.
        """
        if not self.client:
            return {'success': False, 'error': 'Twilio client not initialized or credentials missing'}
        if not self.from_number:
            return {'success': False, 'error': 'Twilio sender WhatsApp number not configured'}

        to_formatted = self.format_phone_number(to_number)
        try:
            logger.info(f"📤 Sending freeform WhatsApp message: to={to_formatted}")
            message = self.client.messages.create(
                from_=self.from_number,
                to=to_formatted,
                body=message_text
            )
            logger.info(f"✅ WhatsApp message sent! SID: {message.sid}, status: {message.status}")
            return {
                'success': True,
                'message_id': message.sid,
                'status': message.status
            }
        except TwilioRestException as e:
            logger.error(f"❌ Twilio API error: {e.msg} (Code: {e.code})")
            return {'success': False, 'error': str(e.msg), 'code': e.code}
        except Exception as e:
            logger.error(f"❌ Error sending WhatsApp message: {e}")
            return {'success': False, 'error': str(e)}

    def send_enquiry_confirmation(self, to_number, name, gym_name="OneX-Fitness", gym_contact_number=None, logo_url=None):
        """
        Convenience method for enquiry confirmation with optional logo.
        """
        # Variablen structure for Twilio Content API
        # Mapping recovered from common patterns: 1:name, 2:gym_name, 3:contact
        vars_dict = {
            "1": str(name).strip(),
            "2": str(gym_name or "OneX-Fitness").strip(),
            "3": str(gym_contact_number).strip() if gym_contact_number else "N/A",
            "4": str(logo_url or "").strip()
        }
        
        return self.send_template_message(
            to_number=to_number,
            content_sid=getattr(settings, 'TWILIO_CONTENT_SID', None),
            content_variables=vars_dict,
            media_url=logo_url
        )