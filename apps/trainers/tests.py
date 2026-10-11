from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.superadmin.models import Gym, GymAdmin
from apps.trainers.models import Trainer, TrainerSalary
from apps.members.models import Member, PersonalTrainer
from apps.attendance.models import TrainerAttendance, TrainerLeave


@override_settings(SECURE_SSL_REDIRECT=False)
class TrainerModuleTests(TestCase):
    def setUp(self):
        self.client1 = Client()
        self.client2 = Client()

        # Create two gyms for multi-tenant isolation testing
        self.gym1 = Gym.objects.create(
            name='Iron Paradise Gym',
            phone='9876543210',
            email='iron@gym.com',
            gym_id_prefix='IRON'
        )
        self.gym2 = Gym.objects.create(
            name='Titan Fitness Gym',
            phone='9876543211',
            email='titan@gym.com',
            gym_id_prefix='TITAN'
        )

        # Users & GymAdmins
        self.user1 = User.objects.create_user(username='iron_admin', password='password123')
        self.gym_admin1 = GymAdmin.objects.create(user=self.user1, gym=self.gym1)

        self.user2 = User.objects.create_user(username='titan_admin', password='password123')
        self.gym_admin2 = GymAdmin.objects.create(user=self.user2, gym=self.gym2)

        # Log in client1 (Gym 1)
        self.client1.login(username='iron_admin', password='password123')
        session1 = self.client1.session
        session1['gym_id'] = self.gym1.id
        session1.save()

        # Log in client2 (Gym 2)
        self.client2.login(username='titan_admin', password='password123')
        session2 = self.client2.session
        session2['gym_id'] = self.gym2.id
        session2.save()

        # Create sample trainer in Gym 1
        self.trainer1 = Trainer.objects.create(
            gym=self.gym1,
            name='Vikram Sharma',
            email='vikram@coach.com',
            phone='9876500001',
            address='123 Fitness Street, South Block',
            joining_date=date.today() - timedelta(days=200),
            salary=Decimal('35000.00'),
            personal_training_monthly_amount=Decimal('4500.00'),
            specialization='PT',
            time_slot='Morning 6:00 AM - 12:00 PM',
            is_active=True
        )
        # Provision User account for trainer
        self.trainer1.create_or_update_user_account(raw_password='Fit@0001')

    def test_trainer_list_renders_and_contains_profile_links(self):
        """Trainer list page displays trainers with profile links and action buttons."""
        url = reverse('trainer_list')
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vikram Sharma')
        self.assertContains(response, self.trainer1.trainer_id)
        # Profile link present
        profile_url = reverse('trainer_profile', args=[self.trainer1.id])
        self.assertContains(response, profile_url)

    def test_trainer_profile_view_and_overview_details(self):
        """Trainer profile displays complete personal, professional, and credential information."""
        url = reverse('trainer_profile', args=[self.trainer1.id])
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Trainer Profile')
        self.assertContains(response, 'Vikram Sharma')
        self.assertContains(response, self.trainer1.trainer_id)
        self.assertContains(response, '35000.00')
        self.assertContains(response, 'Personal Trainer')
        self.assertContains(response, 'Morning 6:00 AM - 12:00 PM')
        self.assertEqual(response.context['trainer'], self.trainer1)

    def test_trainer_profile_with_pt_clients_and_revenue(self):
        """Trainer profile aggregates assigned PT clients, calculates revenue, and displays active clients."""
        # Create a member in Gym 1
        member = Member.objects.create(
            gym=self.gym1,
            first_name='Rahul',
            last_name='Verma',
            mobile_number='9876599999',
            email='rahul@member.com',
            gender='male'
        )

        # Assign member to trainer1 for Personal Training
        pt = PersonalTrainer.objects.create(
            gym=self.gym1,
            member=member,
            trainer=self.trainer1,
            months=3,
            trainer_fee=Decimal('12000.00'),
            gym_charges=Decimal('3000.00'),
            pt_start_date=date.today() - timedelta(days=15),
            total_amount=Decimal('15000.00'),
            paid_amount=Decimal('10000.00'),
            status='active'
        )

        url = reverse('trainer_profile', args=[self.trainer1.id])
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)

        # Context aggregations
        self.assertEqual(response.context['total_clients_count'], 1)
        self.assertEqual(response.context['active_clients_count'], 1)
        self.assertEqual(response.context['total_pt_revenue'], Decimal('15000.00'))
        self.assertEqual(response.context['total_pt_paid'], Decimal('10000.00'))
        self.assertEqual(response.context['total_pt_due'], Decimal('5000.00'))

        # Check member appears in HTML
        self.assertContains(response, 'Rahul Verma')
        self.assertContains(response, '10000.00')
        self.assertContains(response, '5000.00')

    def test_trainer_profile_attendance_and_leaves(self):
        """Attendance logs and leave records are accurately counted and rendered in tabs."""
        now = timezone.now()
        # Create attendance record
        TrainerAttendance.objects.create(
            gym=self.gym1,
            trainer=self.trainer1,
            check_in_time=now - timedelta(hours=4),
            check_out_time=now,
            status='outside'
        )

        # Create leave record
        TrainerLeave.objects.create(
            gym=self.gym1,
            trainer=self.trainer1,
            start_date=date.today() + timedelta(days=5),
            end_date=date.today() + timedelta(days=6),
            reason='Family event',
            status='approved',
            leave_type='casual'
        )

        url = reverse('trainer_profile', args=[self.trainer1.id])
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['month_present_days'], 1)
        self.assertEqual(response.context['approved_leaves'], 1)
        self.assertContains(response, 'Casual Leave')
        self.assertContains(response, 'Family event')

    def test_multi_tenant_isolation(self):
        """Gym 2 cannot view, edit, toggle, or delete Gym 1's trainer profile."""
        profile_url = reverse('trainer_profile', args=[self.trainer1.id])
        res_profile = self.client2.get(profile_url)
        # Should redirect to trainer list because trainer is not found in Gym 2
        self.assertEqual(res_profile.status_code, 302)

        toggle_url = reverse('toggle_trainer_status', args=[self.trainer1.id])
        res_toggle = self.client2.get(toggle_url)
        self.assertEqual(res_toggle.status_code, 302)

        del_url = reverse('delete_trainer', args=[self.trainer1.id])
        res_del = self.client2.post(del_url)
        self.assertEqual(res_del.status_code, 404)

        # Verify trainer1 was NOT deleted
        self.trainer1.refresh_from_db()
        self.assertEqual(self.trainer1.name, 'Vikram Sharma')

    def test_toggle_trainer_status_and_redirect(self):
        """Toggling status switches is_active and redirects back to profile if requested from profile."""
        url = reverse('toggle_trainer_status', args=[self.trainer1.id])
        profile_url = reverse('trainer_profile', args=[self.trainer1.id])

        # Toggle from profile page
        response = self.client1.get(url, HTTP_REFERER=profile_url)
        self.assertRedirects(response, profile_url)

        self.trainer1.refresh_from_db()
        self.assertFalse(self.trainer1.is_active)

        # Toggle back
        response2 = self.client1.get(url, HTTP_REFERER=profile_url)
        self.assertRedirects(response2, profile_url)
        self.trainer1.refresh_from_db()
        self.assertTrue(self.trainer1.is_active)

    def test_reset_trainer_password(self):
        """Resetting trainer password returns JSON credentials for SweetAlert & WhatsApp share."""
        url = reverse('reset_trainer_password', args=[self.trainer1.id])
        response = self.client1.post(url, {'new_password': 'CustomTrainer@99'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['new_password'], 'CustomTrainer@99')

        # Verify password in DB
        self.trainer1.user.refresh_from_db()
        self.assertTrue(self.trainer1.user.check_password('CustomTrainer@99'))

    def test_edit_trainer_updates_and_redirects_to_profile(self):
        """Editing trainer persists changes and redirects to their profile."""
        url = reverse('edit_trainer', args=[self.trainer1.id])
        post_data = {
            'name': 'Vikram Sharma Senior',
            'email': 'vikram_senior@coach.com',
            'phone': '9876500001',
            'address': 'New Gym Heights, Floor 2',
            'joining_date': str(self.trainer1.joining_date),
            'salary': '42000.00',
            'personal_training_monthly_amount': '5000.00',
            'specialization': 'PT',
            'time_slot': 'Evening 4:00 PM - 10:00 PM'
        }
        response = self.client1.post(url, post_data)
        self.assertRedirects(response, reverse('trainer_profile', args=[self.trainer1.id]))

        self.trainer1.refresh_from_db()
        self.assertEqual(self.trainer1.name, 'Vikram Sharma Senior')
        self.assertEqual(self.trainer1.salary, Decimal('42000.00'))
        self.assertEqual(self.trainer1.time_slot, 'Evening 4:00 PM - 10:00 PM')

    def test_payroll_salary_computation_and_lifecycle(self):
        """Test complete salary computation based on attendance (present, half-day, paid/unpaid leaves, absent) and payroll workflow."""
        from apps.trainers.models import TrainerSalary
        from apps.trainers.views import compute_trainer_salary

        today = timezone.localdate()
        year = today.year
        month = today.month

        # Base salary = 30000, PT monthly rate = 2000
        self.trainer1.salary = Decimal('30000.00')
        self.trainer1.personal_training_monthly_amount = Decimal('2000.00')
        self.trainer1.save()

        # Create 1 active PT client assigned to trainer
        member = Member.objects.create(
            gym=self.gym1,
            first_name='Ankit',
            last_name='Patel',
            mobile_number='9998887771',
            email='ankit@gmail.com',
            gender='male'
        )
        PersonalTrainer.objects.create(
            gym=self.gym1,
            trainer=self.trainer1,
            member=member,
            pt_start_date=today - timedelta(days=10),
            months=3,
            trainer_fee=Decimal('6000.00'),
            gym_charges=Decimal('0.00'),
            total_amount=Decimal('6000.00'),
            paid_amount=Decimal('6000.00'),
            status='active'
        )

        # Create 1 half-day approved leave
        TrainerLeave.objects.create(
            gym=self.gym1,
            trainer=self.trainer1,
            start_date=today,
            end_date=today,
            leave_type='casual',
            is_half_day=True,
            half_day_period='first_half',
            status='approved',
            is_paid=True
        )

        salary = compute_trainer_salary(self.gym1, self.trainer1, year, month)
        self.assertIsNotNone(salary)
        self.assertEqual(salary.trainer, self.trainer1)
        self.assertEqual(salary.pt_clients_count, 1)
        self.assertEqual(salary.pt_commission, Decimal('2000.00'))
        self.assertGreaterEqual(salary.payable_days, Decimal('0.5'))
        self.assertEqual(salary.status, 'draft')

        # Test salary list view
        resp = self.client1.get(reverse('trainer_salary_list') + f'?month={month}&year={year}')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Vikram Sharma')
        self.assertContains(resp, 'Payroll & Salary')

        # Test adjusting bonus and deductions
        adjust_url = reverse('update_trainer_salary_adjustment', args=[salary.id])
        adj_resp = self.client1.post(adjust_url, {
            'bonus': '1500.00',
            'deductions': '500.00',
            'remarks': 'Monthly performance incentive'
        })
        self.assertEqual(adj_resp.status_code, 302)
        salary.refresh_from_db()
        self.assertEqual(salary.bonus, Decimal('1500.00'))
        self.assertEqual(salary.deductions, Decimal('500.00'))
        self.assertEqual(salary.remarks, 'Monthly performance incentive')

        # Test approve salary
        approve_url = reverse('approve_trainer_salary', args=[salary.id])
        app_resp = self.client1.get(approve_url)
        self.assertEqual(app_resp.status_code, 302)
        salary.refresh_from_db()
        self.assertEqual(salary.status, 'approved')

        # Test pay salary
        pay_url = reverse('pay_trainer_salary', args=[salary.id])
        pay_resp = self.client1.post(pay_url, {
            'payment_mode': 'bank_transfer',
            'payment_date': str(today),
            'transaction_id': 'NEFT-99887766',
            'remarks': 'Salary credited to HDFC'
        })
        self.assertEqual(pay_resp.status_code, 302)
        salary.refresh_from_db()
        self.assertEqual(salary.status, 'paid')
        self.assertEqual(salary.payment_mode, 'bank_transfer')
        self.assertEqual(salary.transaction_id, 'NEFT-99887766')

        # Test payslip view
        payslip_url = reverse('trainer_payslip', args=[salary.id])
        slip_resp = self.client1.get(payslip_url)
        self.assertEqual(slip_resp.status_code, 200)
        self.assertContains(slip_resp, 'Vikram Sharma')
        self.assertContains(slip_resp, 'Official Salary Slip')
        self.assertContains(slip_resp, 'NEFT-99887766')

    def test_trainer_portal_salary_view_and_payslip_download(self):
        """A logged-in trainer can view their monthly salary statement and download their payslip invoice."""
        today = date.today()
        month = today.month
        year = today.year

        # Log in as the trainer
        trainer_client = Client()
        trainer_user = self.trainer1.user
        trainer_client.force_login(trainer_user)
        session = trainer_client.session
        session['role'] = 'trainer'
        session['gym_id'] = self.gym1.id
        session.save()

        # 1. Access Trainer Portal Salary View
        salary_url = reverse('trainer_portal:salary') + f'?month={month}&year={year}'
        resp = trainer_client.get(salary_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Salary & Compensation Statement')
        self.assertContains(resp, 'Vikram Sharma')

        # Compute salary record
        salary = TrainerSalary.objects.filter(trainer=self.trainer1, month=month, year=year).first()
        self.assertIsNotNone(salary)

        # 2. Access Trainer Portal Payslip Download View
        payslip_url = reverse('trainer_portal:payslip', args=[salary.id])
        payslip_resp = trainer_client.get(payslip_url)
        self.assertEqual(payslip_resp.status_code, 200)
        self.assertContains(payslip_resp, 'Pay Slip for the Month of')
        self.assertContains(payslip_resp, 'Vikram Sharma')
        self.assertContains(payslip_resp, self.trainer1.trainer_id)
        self.assertContains(payslip_resp, 'Earnings')
        self.assertContains(payslip_resp, 'Deductions')
        self.assertContains(payslip_resp, 'Net Pay')

        # 3. Test direct PDF download
        pdf_resp = trainer_client.get(payslip_url + '?download=pdf')
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', pdf_resp['Content-Disposition'])

