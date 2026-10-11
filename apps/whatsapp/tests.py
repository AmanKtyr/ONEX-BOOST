import urllib.parse
from datetime import date, timedelta
from django.test import TestCase
from django.template import Template, Context
from django.utils import timezone

from apps.superadmin.models import Gym
from apps.members.models import Member, MembershipHistory
from apps.management.models import MembershipPlan
from apps.whatsapp.utils import (
    clean_whatsapp_phone,
    build_whatsapp_url,
    get_expired_membership_message,
    get_expiring_soon_message,
    get_pending_due_message,
    get_member_profile_message,
    get_birthday_message,
    get_enquiry_followup_message,
)
from apps.whatsapp.templatetags.whatsapp_tags import (
    whatsapp_expired_url,
    whatsapp_expiring_soon_url,
    whatsapp_due_url,
    whatsapp_profile_url,
    whatsapp_birthday_url,
    whatsapp_enquiry_url,
)


class WhatsAppUtilitiesTest(TestCase):
    def setUp(self):
        self.gym = Gym.objects.create(
            name="Iron Peak Fitness",
            phone="9876500000"
        )
        self.member = Member.objects.create(
            gym=self.gym,
            first_name="Rahul",
            last_name="Sharma",
            mobile_number="9876543210",
        )
        self.plan = MembershipPlan.objects.create(
            gym=self.gym,
            title="Gold Annual Plan",
            duration="1_year",
            amount=12000
        )
        self.membership_history = MembershipHistory.objects.create(
            gym=self.gym,
            member=self.member,
            plan=self.plan,
            membership_start_date=date(2025, 1, 1),
            total_amount=12000,
            paid_amount=12000,
            status='active'
        )

    def test_clean_whatsapp_phone(self):
        self.assertEqual(clean_whatsapp_phone("9876543210"), "919876543210")
        self.assertEqual(clean_whatsapp_phone("+919876543210"), "919876543210")
        self.assertEqual(clean_whatsapp_phone("91-9876543210"), "919876543210")
        self.assertEqual(clean_whatsapp_phone("+1 202 555 0123"), "12025550123")
        self.assertEqual(clean_whatsapp_phone(""), "")
        self.assertEqual(clean_whatsapp_phone(None), "")

    def test_build_whatsapp_url(self):
        msg = "Hello World! Fitness & Health"
        url = build_whatsapp_url("9876543210", msg)
        self.assertTrue(url.startswith("https://wa.me/919876543210?text="))
        self.assertIn("Fitness%20%26%20Health", url)

    def test_expired_membership_message(self):
        msg = get_expired_membership_message(self.member, self.gym)
        self.assertIn("Rahul Sharma", msg)
        self.assertIn("Gold Annual Plan", msg)
        self.assertIn("Iron Peak Fitness", msg)
        self.assertIn("expired on", msg)
        self.assertIn("renew", msg.lower())

    def test_expiring_soon_message(self):
        msg = get_expiring_soon_message(self.member, self.gym)
        self.assertIn("Rahul Sharma", msg)
        self.assertIn("Gold Annual Plan", msg)
        self.assertIn("Iron Peak Fitness", msg)
        self.assertIn("scheduled to expire on", msg)
        self.assertIn("renew", msg.lower())

    def test_pending_due_message(self):
        msg = get_pending_due_message(self.member, due_amount=1500, gym=self.gym, plan_name="Gold Annual Plan")
        self.assertIn("Rahul Sharma", msg)
        self.assertIn("₹1500", msg)
        self.assertIn("Iron Peak Fitness", msg)
        self.assertIn("pending fee balance", msg)

    def test_member_profile_message_context_aware(self):
        # 1. When expired
        msg = get_member_profile_message(self.member, self.gym)
        self.assertIn("expired", msg.lower())

        # 2. When active and expiring soon (set start date to expire tomorrow)
        self.membership_history.membership_start_date = timezone.localdate() - timedelta(days=364)
        self.membership_history.save()
        msg_soon = get_member_profile_message(self.member, self.gym)
        self.assertIn("scheduled to expire on", msg_soon)

        # 3. When active and with pending dues
        self.membership_history.membership_start_date = timezone.localdate()
        self.membership_history.save()
        msg_due = get_member_profile_message(self.member, self.gym, due_amount=2000)
        self.assertIn("₹2000", msg_due)

        # 4. When active and no dues
        msg_active = get_member_profile_message(self.member, self.gym, due_amount=0)
        self.assertIn("enjoying your workouts", msg_active)

    def test_birthday_message(self):
        today_msg = get_birthday_message(self.member, is_today=True, gym=self.gym)
        self.assertIn("Happy Birthday", today_msg)
        self.assertIn("Rahul Sharma", today_msg)

        adv_msg = get_birthday_message(self.member, is_today=False, gym=self.gym)
        self.assertIn("Advance Happy Birthday", adv_msg)

    def test_template_tags_rendering(self):
        # Expired filter
        url_expired = whatsapp_expired_url(self.member, self.gym)
        self.assertTrue(url_expired.startswith("https://wa.me/919876543210?text="))
        self.assertIn("expired", urllib.parse.unquote(url_expired).lower())

        # Expiring soon filter
        url_soon = whatsapp_expiring_soon_url(self.member, self.gym)
        self.assertTrue(url_soon.startswith("https://wa.me/919876543210?text="))
        self.assertIn("scheduled to expire on", urllib.parse.unquote(url_soon))

        # Profile filter
        url_profile = whatsapp_profile_url(self.member, due_amount=500, gym=self.gym)
        self.assertTrue(url_profile.startswith("https://wa.me/919876543210?text="))

        # Birthday filter
        url_bday = whatsapp_birthday_url(self.member, 'today', self.gym)
        self.assertTrue(url_bday.startswith("https://wa.me/919876543210?text="))
        self.assertIn("Happy Birthday", urllib.parse.unquote(url_bday))

        # Dues filter with membership history object
        self.membership_history.paid_amount = 10000
        self.membership_history.save()
        url_due = whatsapp_due_url(self.membership_history, self.gym)
        self.assertTrue(url_due.startswith("https://wa.me/919876543210?text="))
        self.assertIn("₹2000", urllib.parse.unquote(url_due))

    def test_template_tags_in_django_template(self):
        template_str = (
            "{% load custom_tags %}"
            "<a href=\"{{ member|whatsapp_expired_url:gym }}\">Expired WhatsApp</a>"
            "<a href=\"{{ member|whatsapp_expiring_soon_url:gym }}\">Expiring Soon WhatsApp</a>"
        )
        rendered = Template(template_str).render(Context({'member': self.member, 'gym': self.gym}))
        self.assertIn("https://wa.me/919876543210?text=", rendered)
        self.assertIn("Gold%20Annual%20Plan", rendered)
