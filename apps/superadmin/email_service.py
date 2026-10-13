"""
OneX-FitnessEnterprise Outbound Email & SMTP Gateway Service.
Handles dynamic SMTP connection resolution from SystemSetting,
responsive HTML email dispatching, and automated notifications for
Gym onboarding, Admin credentials, and Password recovery.
"""

import logging
import datetime
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.urls import reverse
from django.conf import settings
from .models import SystemSetting

logger = logging.getLogger('apps')


def get_smtp_gateway_config():
    """
    Returns the live SystemSetting instance and derived SMTP parameters.
    """
    setting = SystemSetting.get_settings()
    host = (setting.smtp_host or '').strip()
    port = setting.smtp_port or 587
    user = (setting.smtp_user or '').strip()
    password = setting.smtp_password or ''
    from_email = (setting.smtp_from_email or '').strip() or user or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@OneX-Fitness.com')
    use_tls = bool(setting.smtp_use_tls)
    use_ssl = bool(setting.smtp_use_ssl)

    is_configured = bool(host and user)
    return {
        'setting': setting,
        'host': host,
        'port': port,
        'user': user,
        'password': password,
        'from_email': from_email,
        'use_tls': use_tls,
        'use_ssl': use_ssl,
        'is_configured': is_configured,
        'platform_name': setting.platform_name or 'ONEX BOOST',
        'support_email': setting.support_email or from_email,
        'support_phone': setting.support_phone or '',
        'website_url': setting.website_url or 'http://127.0.0.1:8000',
    }


def get_active_email_connection():
    """
    Constructs an active Django mail connection using the database SMTP settings.
    Falls back to Django default email backend if not configured.
    """
    config = get_smtp_gateway_config()
    if config['is_configured']:
        try:
            return get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=config['host'],
                port=config['port'],
                username=config['user'],
                password=config['password'],
                use_tls=config['use_tls'],
                use_ssl=config['use_ssl'],
                timeout=12,
            ), config
        except Exception as e:
            logger.error(f"[EmailGateway] Failed to build custom SMTP connection: {e}")
            return get_connection(), config

    # Fallback to standard Django connection (e.g. console backend during local dev or settings.py)
    return get_connection(), config


def send_system_email(subject, template_name, context, recipient_list, request=None):
    """
    Renders and sends a multipart HTML/Plain-text email to recipients.
    Injects platform branding, copyright, and support metadata automatically.
    Returns (success: bool, message: str).
    """
    if isinstance(recipient_list, str):
        recipient_list = [recipient_list]

    # Clean recipients
    recipients = [r.strip() for r in recipient_list if r and '@' in r]
    if not recipients:
        logger.warning(f"[EmailGateway] No valid email recipients found for subject '{subject}'.")
        return False, "No valid recipient email address provided."

    connection, config = get_active_email_connection()
    setting = config['setting']

    # Resolve platform base URL
    base_url = config['website_url']
    if request:
        try:
            base_url = request.build_absolute_uri('/')[:-1]
        except Exception:
            pass

    login_url = f"{base_url}{reverse('login')}"

    # Merge standard platform email context
    email_context = {
        'platform_name': config['platform_name'],
        'platform_tagline': setting.tagline or 'Enterprise GYM Management & SaaS Automation',
        'company_name': setting.company_name or config['platform_name'],
        'support_email': config['support_email'],
        'support_phone': config['support_phone'],
        'website_url': base_url,
        'login_url': login_url,
        'current_year': datetime.datetime.now().year,
        'email_title': subject,
        **context
    }

    try:
        html_content = render_to_string(template_name, email_context)
        text_content = strip_tags(html_content)

        formatted_subject = f"[{config['platform_name']}] {subject}"
        from_header = f"{config['platform_name']} <{config['from_email']}>"

        msg = EmailMultiAlternatives(
            subject=formatted_subject,
            body=text_content,
            from_email=from_header,
            to=recipients,
            connection=connection,
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info(f"[EmailGateway] Email successfully dispatched to {recipients} | Subject: '{formatted_subject}'")
        return True, "Email sent successfully."
    except Exception as e:
        error_msg = f"Failed to dispatch email: {str(e)}"
        logger.error(f"[EmailGateway] {error_msg} (Recipients: {recipients})")
        return False, error_msg


# ==============================================================================
# SPECIALIZED BUSINESS EMAIL TRIGGERS
# ==============================================================================

def send_gym_welcome_email(gym, request=None):
    """
    Dispatched when a new Gym facility is added to the OneX-Fitness platform.
    """
    if not gym or not gym.email:
        logger.info(f"[EmailGateway] Gym '{gym}' has no contact email; skipping welcome email.")
        return False, "Gym does not have a registered contact email."

    subject = f"Welcome to OneX-Fitness – {gym.name} is Ready!"
    context = {
        'gym': gym,
        'email_title': subject,
    }
    return send_system_email(
        subject=subject,
        template_name='emails/gym_welcome.html',
        context=context,
        recipient_list=[gym.email],
        request=request
    )


def send_gym_admin_credentials_email(gym_admin, raw_password, request=None):
    """
    Dispatched when an administrator account is provisioned for a gym.
    """
    if not gym_admin or not gym_admin.user or not gym_admin.user.email:
        logger.info(f"[EmailGateway] Gym Admin '{gym_admin}' has no user email; skipping credentials email.")
        return False, "Gym Administrator user has no email address configured."

    user = gym_admin.user
    subject = f"Administrator Credentials for {gym_admin.gym.name}"
    context = {
        'gym': gym_admin.gym,
        'gym_admin': gym_admin,
        'admin_name': gym_admin.name or user.get_full_name() or user.username,
        'username': user.username,
        'password': raw_password,
        'email_title': subject,
    }
    return send_system_email(
        subject=subject,
        template_name='emails/gym_admin_credentials.html',
        context=context,
        recipient_list=[user.email],
        request=request
    )


def send_password_reset_email(user, new_password, gym_name=None, request=None):
    """
    Dispatched when a password reset is performed by superadmin or user recovery.
    """
    if not user or not user.email:
        logger.info(f"[EmailGateway] User '{user}' has no email address; skipping password reset email.")
        return False, "Target user does not have a registered email address."

    subject = "Account Password Reset Notification"
    user_display = user.get_full_name() or user.username
    context = {
        'user_display_name': user_display,
        'username': user.username,
        'temporary_password': new_password,
        'gym_name': gym_name,
        'reset_time': datetime.datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'email_title': subject,
    }
    return send_system_email(
        subject=subject,
        template_name='emails/password_reset.html',
        context=context,
        recipient_list=[user.email],
        request=request
    )


def send_password_changed_email(user, request=None):
    """
    Dispatched when a user successfully updates their password.
    """
    if not user or not user.email:
        return False, "Target user has no email."

    subject = "Security Alert: Password Updated"
    user_display = user.get_full_name() or user.username
    context = {
        'user_display_name': user_display,
        'username': user.username,
        'changed_time': datetime.datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'email_title': subject,
    }
    return send_system_email(
        subject=subject,
        template_name='emails/password_changed.html',
        context=context,
        recipient_list=[user.email],
        request=request
    )
