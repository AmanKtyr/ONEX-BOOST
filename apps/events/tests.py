from datetime import timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from apps.superadmin.models import Gym, GymAdmin
from apps.events.models import Event, EventParticipant

class EventSecurityAndTenantIsolationTests(TestCase):
    def setUp(self):
        self.client1 = Client()
        self.client2 = Client()

        # Two gyms
        self.gym1 = Gym.objects.create(
            name='Events Gym 1',
            phone='9555500001',
            email='gym1@events.com',
            gym_id_prefix='EV1'
        )
        self.gym2 = Gym.objects.create(
            name='Events Gym 2',
            phone='9555500002',
            email='gym2@events.com',
            gym_id_prefix='EV2'
        )

        # Users and GymAdmins
        self.user1 = User.objects.create_user(username='admin_ev1', password='password123')
        self.ga1 = GymAdmin.objects.create(user=self.user1, gym=self.gym1)

        self.user2 = User.objects.create_user(username='admin_ev2', password='password123')
        self.ga2 = GymAdmin.objects.create(user=self.user2, gym=self.gym2)

        # Log in
        self.client1.login(username='admin_ev1', password='password123')
        s1 = self.client1.session
        s1['gym_id'] = self.gym1.id
        s1.save()

        self.client2.login(username='admin_ev2', password='password123')
        s2 = self.client2.session
        s2['gym_id'] = self.gym2.id
        s2.save()

        # Events
        now = timezone.now()
        self.event1 = Event.objects.create(
            gym=self.gym1,
            event_name='Crossfit Challenge Gym1',
            event_type='Workout',
            start_date=now + timedelta(days=1),
            end_date=now + timedelta(days=1, hours=2),
            registration_deadline=now + timedelta(hours=12),
            max_participants=50,
            fee_amount=Decimal('500.00'),
            status='Upcoming'
        )

        self.event2 = Event.objects.create(
            gym=self.gym2,
            event_name='Yoga Workshop Gym2',
            event_type='Seminar',
            start_date=now + timedelta(days=2),
            end_date=now + timedelta(days=2, hours=3),
            registration_deadline=now + timedelta(days=1),
            max_participants=30,
            fee_amount=Decimal('300.00'),
            status='Upcoming'
        )

        self.participant2 = EventParticipant.objects.create(
            event=self.event2,
            full_name='Participant In Gym2',
            mobile_number='9888800002',
            payment_status='Pending'
        )

    def test_tenant_isolation_cancel_event(self):
        """Gym 1 admin cannot cancel event of Gym 2."""
        url = reverse('events:cancel_event', kwargs={'event_id': self.event2.id})
        response = self.client1.post(url, secure=True)
        # Should redirect to event_list because event is not found for Gym 1
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('events:event_list'), response.url)
        # Verify event in Gym 2 was NOT deleted
        self.assertTrue(Event.objects.filter(id=self.event2.id).exists())

    def test_tenant_isolation_edit_event(self):
        """Gym 1 admin cannot access or edit event of Gym 2."""
        url = reverse('events:edit_event', kwargs={'event_id': self.event2.id})
        response = self.client1.get(url, secure=True)
        # Should redirect to event_list
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('events:event_list'), response.url)

    def test_tenant_isolation_update_payment_status(self):
        """Gym 1 admin cannot update payment status for Gym 2 event participant."""
        url = reverse('events:update_payment_status', kwargs={'registration_id': self.participant2.id})
        response = self.client1.post(url, {'status': 'Successful'}, secure=True)
        # Should redirect to all_event_registrations because record is not found for Gym 1
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('events:all_event_registrations'), response.url)
        self.participant2.refresh_from_db()
        self.assertEqual(self.participant2.payment_status, 'Pending')

    def test_cancel_event_valid(self):
        """Gym 1 admin can cancel their own event."""
        url = reverse('events:cancel_event', kwargs={'event_id': self.event1.id})
        response = self.client1.post(url, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('events:event_list'), response.url)
        # Verify event was deleted
        self.assertFalse(Event.objects.filter(id=self.event1.id).exists())
