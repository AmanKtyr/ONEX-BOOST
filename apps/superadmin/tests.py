from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.superadmin.models import Gym, SubscriptionPlan, GymSubscription
from apps.billing.models import Payment

class SuperadminSecurityAndBillingTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # Superadmin user
        self.admin_user = User.objects.create_superuser(
            username='superadmin_test',
            email='admin@fitstack.com',
            password='testpassword123'
        )
        
        # Regular user
        self.regular_user = User.objects.create_user(
            username='regular_test',
            email='user@fitstack.com',
            password='userpassword123'
        )
        
        # Create a test Gym
        self.gym = Gym.objects.create(
            name='Test Alpha Gym',
            phone='9876543210',
            email='alpha@gym.com',
            gym_id_prefix='ALPHA'
        )
        
        # Plan
        self.plan = SubscriptionPlan.objects.create(
            name='Standard Annual Plan',
            price=Decimal('10000.00'),
            duration_months=12,
            features='All Features'
        )
        
        # Subscription with 5000 due
        self.sub = GymSubscription.objects.create(
            gym=self.gym,
            subscription=self.plan,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=365),
            total_amount=Decimal('10000.00'),
            paid_amount=Decimal('5000.00'),
            payment_mode='cash'
        )

    def test_unauthenticated_access_blocked(self):
        """Unauthenticated requests to superadmin endpoints must redirect to login."""
        endpoints = [
            reverse('superadmin:dashboard'),
            reverse('superadmin:submit_due'),
            reverse('superadmin:invoice', kwargs={'subscription_id': self.sub.id}),
        ]
        for url in endpoints:
            response = self.client.get(url, secure=True)
            self.assertEqual(response.status_code, 302, f"Failed for {url}")
            self.assertIn('/login/', response.url)

    def test_regular_user_forbidden_from_superadmin(self):
        """Regular non-superadmin users must be redirected away from superadmin."""
        self.client.login(username='regular_test', password='userpassword123')
        session = self.client.session
        session['role'] = 'member'
        session.save()
        
        response = self.client.get(reverse('superadmin:dashboard'), secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_submit_due_pays_in_full_without_none_type_error(self):
        """
        Regression Test: When a payment pays off the remaining due in full,
        submit_due must NOT crash with 'NoneType' object has no attribute 'id',
        must update paid_amount, create Payment, and store open_invoice_id in session.
        """
        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()
        
        post_data = {
            'gym': self.gym.id,
            'amount_to_pay': '5000.00',
            'payment_method': 'upi',
            'notes': 'Paid in full via UPI'
        }
        
        # Submit the full remaining due
        response = self.client.post(reverse('superadmin:submit_due'), post_data, secure=True)
        
        # Should redirect successfully without throwing 500 AttributeError
        self.assertEqual(response.status_code, 302)
        
        # Verify database state
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.paid_amount, Decimal('10000.00'))
        self.assertEqual(self.sub.due_amount, Decimal('0.00'))
        
        # Payment record created
        payment = Payment.objects.filter(gym=self.gym, amount=Decimal('5000.00')).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.payment_mode, 'upi')
        
        # Invoice session set safely
        self.assertEqual(self.client.session.get('open_invoice_id'), self.sub.id)

    def test_submit_due_rejects_overpayment(self):
        """Payments greater than total due must be rejected."""
        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()
        
        post_data = {
            'gym': self.gym.id,
            'amount_to_pay': '6000.00',  # Due is only 5000.00
            'payment_method': 'cash',
            'notes': 'Overpayment attempt'
        }
        
        response = self.client.post(reverse('superadmin:submit_due'), post_data, secure=True)
        self.assertEqual(response.status_code, 302)
        
        # Subscription due unchanged
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.paid_amount, Decimal('5000.00'))
        self.assertEqual(self.sub.due_amount, Decimal('5000.00'))

    def test_gym_list_shows_registered_users_count(self):
        """Gym list endpoint must provide total members, active members, and trainers."""
        from apps.members.models import Member
        from apps.trainers.models import Trainer

        # Create members for the gym
        Member.objects.create(
            gym=self.gym,
            first_name='John',
            last_name='Doe',
            mobile_number='9999911111'
        )
        Member.objects.create(
            gym=self.gym,
            first_name='Jane',
            last_name='Smith',
            mobile_number='9999922222'
        )
        # Create trainer for the gym
        Trainer.objects.create(
            gym=self.gym,
            name='Coach Mike',
            phone='9999933333'
        )

        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()

        response = self.client.get(reverse('superadmin:gym_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registered Users')
        # Check that member count (2) and trainer count (1) appear
        self.assertContains(response, '2 Members')
        self.assertContains(response, '1 Staff')

    def test_create_and_update_subscription_plan_with_quotas(self):
        """Superadmin can create a plan with tier, quotas (max_members, etc.), and feature toggles."""
        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()

        # Add plan with limits
        add_url = reverse('superadmin:add_subscription_plan')
        data = {
            'name': 'Enterprise Growth Plan',
            'plan_tier': 'growth',
            'tagline': 'Engineered for scaling fitness clubs',
            'price': '24999.00',
            'duration_months': 12,
            'color_theme': 'amber',
            'is_popular': True,
            'is_active': True,
            'max_members': 500,
            'max_trainers': 25,
            'max_admins': 5,
            'has_whatsapp_support': True,
            'has_biometric_attendance': True,
            'has_billing_invoicing': True,
            'has_reports_analytics': True,
            'has_crm_leads': True,
            'has_expense_management': True,
            'has_inventory_management': False,
            'has_staff_salary': True,
            'has_diet_workout': True,
            'features': 'Full Access to Growth Modules'
        }
        response = self.client.post(add_url, data)
        self.assertEqual(response.status_code, 302)

        created_plan = SubscriptionPlan.objects.get(name='Enterprise Growth Plan')
        self.assertEqual(created_plan.max_members, 500)
        self.assertEqual(created_plan.max_trainers, 25)
        self.assertEqual(created_plan.max_admins, 5)
        self.assertEqual(created_plan.plan_tier, 'growth')
        self.assertTrue(created_plan.has_whatsapp_support)
        self.assertFalse(created_plan.has_inventory_management)

        # Update the plan to Unlimited members (0)
        update_url = reverse('superadmin:update_subscription_plan', kwargs={'plan_id': created_plan.id})
        data['max_members'] = 0
        data['name'] = 'Enterprise Unlimited Plan'
        response = self.client.post(update_url, data)
        self.assertEqual(response.status_code, 302)

        created_plan.refresh_from_db()
        self.assertEqual(created_plan.max_members, 0)
        self.assertEqual(created_plan.max_members_display, 'Unlimited')
        self.assertEqual(created_plan.name, 'Enterprise Unlimited Plan')

    def test_notification_list_creator_filter_and_display(self):
        """Notification list allows filtering by created_by and displays author info."""
        from apps.superadmin.models import PlatformNotification

        other_admin = User.objects.create_user(
            username='admin_coach_bob',
            email='bob@gym.com',
            password='bobpassword123'
        )

        n1 = PlatformNotification.objects.create(
            title='Alpha System Maintenance',
            message='Server update at midnight',
            notification_type='warning',
            created_by=self.admin_user
        )
        n2 = PlatformNotification.objects.create(
            title='Special Holiday Discount',
            message='Holiday discount for all members',
            notification_type='info',
            created_by=other_admin
        )

        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()

        # 1. Unfiltered request should list both notifications and creator names
        url = reverse('superadmin:notification_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(n1, response.context['notifications'])
        self.assertIn(n2, response.context['notifications'])
        self.assertContains(response, 'superadmin_test')
        self.assertContains(response, 'admin_coach_bob')
        self.assertContains(response, 'Created By')

        # 2. Filter by created_by = 'superadmin' (Unified Superadmin notifications)
        response_superadmin = self.client.get(f"{url}?created_by=superadmin")
        self.assertEqual(response_superadmin.status_code, 200)
        self.assertIn(n1, response_superadmin.context['notifications'])
        self.assertIn(n2, response_superadmin.context['notifications'])
        self.assertContains(response_superadmin, 'Created by Superadmin')
        self.assertContains(response_superadmin, 'Superadmin')

    def test_whatsapp_messages_hub_and_personal_sending(self):
        from apps.whatsapp.models import WhatsAppMessageLog

        self.client.login(username='superadmin_test', password='testpassword123')
        session = self.client.session
        session['role'] = 'superadmin'
        session.save()

        # 1. Access WhatsApp messages hub
        url = reverse('superadmin:whatsapp_messages_hub')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'WhatsApp Message Logs & Direct Chat')

        # Create a failed WhatsApp message log
        failed_log = WhatsAppMessageLog.objects.create(
            recipient_name='Test Lead Alex',
            recipient_phone='9876543210',
            recipient_type='Website Lead',
            message_type='lead',
            message_content='Hello Alex, welcome to FitStack!',
            status='failed',
            error_message='Twilio sandbox unreachable'
        )

        # 2. Access with status filter
        response_failed = self.client.get(f"{url}?status=failed")
        self.assertEqual(response_failed.status_code, 200)
        self.assertContains(response_failed, 'Send with Personal No.')
        self.assertContains(response_failed, 'Test Lead Alex')

        # 3. Mark sent manually
        mark_url = reverse('superadmin:mark_whatsapp_sent_manually', args=[failed_log.id])
        resp_mark = self.client.get(f"{mark_url}?format=json", HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp_mark.status_code, 200)
        failed_log.refresh_from_db()
        self.assertEqual(failed_log.status, 'sent_manually')

        # 4. Direct send endpoint creates log and redirects to wa.me
        direct_url = reverse('superadmin:send_direct_whatsapp_message')
        resp_direct = self.client.post(direct_url, {
            'recipient_name': 'Direct Member Sara',
            'recipient_phone': '9123456789',
            'message_content': 'Hi Sara, checking in on your workout!',
            'action_type': 'open_wa'
        })
        self.assertEqual(resp_direct.status_code, 302)
        self.assertTrue('wa.me' in resp_direct.url)
        self.assertTrue(WhatsAppMessageLog.objects.filter(recipient_name='Direct Member Sara').exists())

        # 5. WhatsApp Conversations API (JSON)
        conv_url = reverse('superadmin:whatsapp_conversations_api')
        resp_conv = self.client.get(conv_url)
        self.assertEqual(resp_conv.status_code, 200)
        conv_data = resp_conv.json()
        self.assertTrue(conv_data['success'])
        self.assertGreater(len(conv_data['conversations']), 0)

        # 6. WhatsApp Thread History API (JSON)
        thread_url = reverse('superadmin:whatsapp_thread_api', args=['9876543210'])
        resp_thread = self.client.get(thread_url)
        self.assertEqual(resp_thread.status_code, 200)
        thread_data = resp_thread.json()
        self.assertTrue(thread_data['success'])
        self.assertIn('contact', thread_data)
        self.assertIn('messages', thread_data)

        # 7. WhatsApp Live Console Send API (Personal WA)
        send_url = reverse('superadmin:whatsapp_send_api')
        resp_send = self.client.post(send_url, {
            'recipient_phone': '9876543210',
            'recipient_name': 'Test Lead Alex',
            'message_content': 'Live console test message',
            'send_method': 'personal_whatsapp'
        })
        self.assertEqual(resp_send.status_code, 200)
        send_data = resp_send.json()
        self.assertTrue(send_data['success'])
        self.assertEqual(send_data['status'], 'sent_manually')
        self.assertIn('wa.me', send_data['whatsapp_url'])



