from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.superadmin.models import Gym, GymAdmin
from apps.members.models import Member, MembershipHistory, PersonalTrainer
from apps.trainers.models import Trainer
from apps.management.models import MembershipPlan
from apps.billing.models import Payment

class BillingTenantIsolationAndPaymentTests(TestCase):
    def setUp(self):
        self.client1 = Client()
        self.client2 = Client()

        # Two gyms
        self.gym1 = Gym.objects.create(
            name='Billing Gym 1',
            phone='9111111111',
            email='gym1@billing.com',
            gym_id_prefix='BG1'
        )
        self.gym2 = Gym.objects.create(
            name='Billing Gym 2',
            phone='9222222222',
            email='gym2@billing.com',
            gym_id_prefix='BG2'
        )

        # Users & GymAdmins
        self.user1 = User.objects.create_user(username='admin_bg1', password='password123')
        self.gym_admin1 = GymAdmin.objects.create(user=self.user1, gym=self.gym1)

        self.user2 = User.objects.create_user(username='admin_bg2', password='password123')
        self.gym_admin2 = GymAdmin.objects.create(user=self.user2, gym=self.gym2)

        # Logins
        self.client1.login(username='admin_bg1', password='password123')
        s1 = self.client1.session
        s1['gym_id'] = self.gym1.id
        s1.save()

        self.client2.login(username='admin_bg2', password='password123')
        s2 = self.client2.session
        s2['gym_id'] = self.gym2.id
        s2.save()

        # Members
        self.member1 = Member.objects.create(
            gym=self.gym1,
            first_name='Member',
            last_name='One',
            mobile_number='9999900001',
            email='m1@test.com',
            gender='Male',
            date_of_birth=date(1996, 2, 2),
        )

        self.member2 = Member.objects.create(
            gym=self.gym2,
            first_name='Member',
            last_name='Two',
            mobile_number='9999900002',
            email='m2@test.com',
            gender='Female',
            date_of_birth=date(1997, 3, 3),
        )

        # Membership Plans
        self.plan1 = MembershipPlan.objects.create(
            gym=self.gym1,
            title='Plan 1',
            amount=Decimal('5000.00'),
            duration='1_month'
        )

        self.plan2 = MembershipPlan.objects.create(
            gym=self.gym2,
            title='Plan 2',
            amount=Decimal('4000.00'),
            duration='1_month'
        )

        # History with dues
        # Member 1 has 2000 due
        self.history1 = MembershipHistory.objects.create(
            gym=self.gym1,
            member=self.member1,
            plan=self.plan1,
            membership_start_date=date.today(),
            total_amount=Decimal('5000.00'),
            paid_amount=Decimal('3000.00'),
            status='active'
        )

        # Member 2 has 1500 due
        self.history2 = MembershipHistory.objects.create(
            gym=self.gym2,
            member=self.member2,
            plan=self.plan2,
            membership_start_date=date.today(),
            total_amount=Decimal('4000.00'),
            paid_amount=Decimal('2500.00'),
            status='active'
        )

    def test_submit_due_isolation(self):
        """Submit due view in Gym 1 only displays members of Gym 1."""
        response = self.client1.get(reverse('billing:submit_due'), secure=True)
        self.assertEqual(response.status_code, 200)
        members_in_context = response.context['members']
        member_ids = [m.id for m in members_in_context]
        self.assertIn(self.member1.id, member_ids)
        self.assertNotIn(self.member2.id, member_ids)

    def test_pay_due_cross_tenant_blocked(self):
        """Gym 1 admin cannot access pay_due for a member belonging to Gym 2."""
        url = reverse('billing:pay_due_payment', kwargs={'member_id': self.member2.id})
        response = self.client1.get(url, secure=True)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('billing:submit_due'), response.url)

    def test_pay_due_valid_payment(self):
        """Paying due amount in full updates MembershipHistory and creates Payment."""
        url = reverse('billing:pay_due_payment', kwargs={'member_id': self.member1.id})
        post_data = {
            'invoice_type': 'membership',
            'invoice_id': self.history1.id,
            'amount': '2000.00',
            'payment_mode': 'cash',
            'transaction_id': 'TXN123456',
            'comment': 'Paid in full',
        }
        response = self.client1.post(url, post_data, secure=True)
        self.assertEqual(response.status_code, 302)

        # Refresh history1
        self.history1.refresh_from_db()
        self.assertEqual(self.history1.paid_amount, Decimal('5000.00'))
        self.assertEqual(self.history1.due_amount, Decimal('0.00'))

        # Verify Payment record
        payment = Payment.objects.filter(member=self.member1, gym=self.gym1).last()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, Decimal('2000.00'))
        self.assertEqual(payment.gym, self.gym1)

    def test_pay_due_overpayment_rejected(self):
        """Paying more than the outstanding due amount is rejected by form validation."""
        url = reverse('billing:pay_due_payment', kwargs={'member_id': self.member1.id})
        post_data = {
            'invoice_type': 'membership',
            'invoice_id': self.history1.id,
            'amount': '9999.00',  # Due is only 2000
            'payment_mode': 'cash',
        }
        response = self.client1.post(url, post_data, secure=True)
        # Should re-render pay_due_payment with errors
        self.assertEqual(response.status_code, 200)

        # Confirm paid amount has not changed
        self.history1.refresh_from_db()
        self.assertEqual(self.history1.paid_amount, Decimal('3000.00'))

    def test_submit_due_filter_by_due_type(self):
        """Verify submit_due filters members correctly according to due_type (membership, pt, both)."""
        trainer = Trainer.objects.create(
            gym=self.gym1,
            name='Test Trainer',
            phone='9876543210'
        )

        # member3 has only PT due
        member3 = Member.objects.create(
            gym=self.gym1,
            first_name='PT',
            last_name='Member',
            mobile_number='9999900003',
            email='m3@test.com',
            gender='Male',
            date_of_birth=date(1995, 1, 1),
        )
        PersonalTrainer.objects.create(
            gym=self.gym1,
            member=member3,
            trainer=trainer,
            months=1,
            trainer_fee=Decimal('2000.00'),
            gym_charges=Decimal('500.00'),
            pt_start_date=date.today(),
            total_amount=Decimal('2500.00'),
            paid_amount=Decimal('1000.00'),
            status='active'
        )

        # member4 has both Membership due and PT due
        member4 = Member.objects.create(
            gym=self.gym1,
            first_name='Both',
            last_name='Member',
            mobile_number='9999900004',
            email='m4@test.com',
            gender='Female',
            date_of_birth=date(1994, 1, 1),
        )
        MembershipHistory.objects.create(
            gym=self.gym1,
            member=member4,
            plan=self.plan1,
            membership_start_date=date.today(),
            total_amount=Decimal('5000.00'),
            paid_amount=Decimal('2000.00'),
            status='active'
        )
        PersonalTrainer.objects.create(
            gym=self.gym1,
            member=member4,
            trainer=trainer,
            months=1,
            trainer_fee=Decimal('3000.00'),
            gym_charges=Decimal('500.00'),
            pt_start_date=date.today(),
            total_amount=Decimal('3500.00'),
            paid_amount=Decimal('1500.00'),
            status='active'
        )

        # 1. Default (All Dues): member1, member3, member4 are all present
        resp_all = self.client1.get(reverse('billing:submit_due'), secure=True)
        self.assertEqual(resp_all.status_code, 200)
        ids_all = [m.id for m in resp_all.context['members']]
        self.assertIn(self.member1.id, ids_all)
        self.assertIn(member3.id, ids_all)
        self.assertIn(member4.id, ids_all)

        # 2. Filter Membership Due: member1 and member4 should be included, member3 excluded
        resp_mem = self.client1.get(reverse('billing:submit_due'), {'due_type': 'membership'}, secure=True)
        self.assertEqual(resp_mem.status_code, 200)
        ids_mem = [m.id for m in resp_mem.context['members']]
        self.assertIn(self.member1.id, ids_mem)
        self.assertIn(member4.id, ids_mem)
        self.assertNotIn(member3.id, ids_mem)

        # 3. Filter PT Due: member3 and member4 should be included, member1 excluded
        resp_pt = self.client1.get(reverse('billing:submit_due'), {'due_type': 'pt'}, secure=True)
        self.assertEqual(resp_pt.status_code, 200)
        ids_pt = [m.id for m in resp_pt.context['members']]
        self.assertIn(member3.id, ids_pt)
        self.assertIn(member4.id, ids_pt)
        self.assertNotIn(self.member1.id, ids_pt)

        # 4. Filter Both: only member4 should be included
        resp_both = self.client1.get(reverse('billing:submit_due'), {'due_type': 'both'}, secure=True)
        self.assertEqual(resp_both.status_code, 200)
        ids_both = [m.id for m in resp_both.context['members']]
        self.assertIn(member4.id, ids_both)
        self.assertNotIn(self.member1.id, ids_both)
        self.assertNotIn(member3.id, ids_both)

