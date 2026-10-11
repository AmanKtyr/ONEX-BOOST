from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from apps.superadmin.models import Gym, GymAdmin
from apps.members.models import Member
from apps.trainers.models import Trainer
from apps.attendance.models import MemberAttendance, TrainerAttendance, MemberLeave

class AttendanceTenantIsolationAndSecurityTests(TestCase):
    def setUp(self):
        self.client_public = Client()
        self.client_gymadmin1 = Client()
        self.client_gymadmin2 = Client()

        # Two gyms
        self.gym1 = Gym.objects.create(
            name='Attendance Gym 1',
            phone='9666600001',
            email='gym1@att.com',
            gym_id_prefix='AG1',
            attendance_code_required=False
        )
        self.gym2 = Gym.objects.create(
            name='Attendance Gym 2',
            phone='9666600002',
            email='gym2@att.com',
            gym_id_prefix='AG2',
            attendance_code_required=False
        )

        # Users and GymAdmins
        self.user1 = User.objects.create_user(username='admin_att1', password='password123')
        self.ga1 = GymAdmin.objects.create(user=self.user1, gym=self.gym1)

        self.user2 = User.objects.create_user(username='admin_att2', password='password123')
        self.ga2 = GymAdmin.objects.create(user=self.user2, gym=self.gym2)

        # Log in
        self.client_gymadmin1.login(username='admin_att1', password='password123')
        s1 = self.client_gymadmin1.session
        s1['gym_id'] = self.gym1.id
        s1['role'] = 'gymadmin'
        s1.save()

        self.client_gymadmin2.login(username='admin_att2', password='password123')
        s2 = self.client_gymadmin2.session
        s2['gym_id'] = self.gym2.id
        s2['role'] = 'gymadmin'
        s2.save()

        # Members
        self.member1 = Member.objects.create(
            gym=self.gym1,
            first_name='AttMember',
            last_name='One',
            mobile_number='9666611111',
            email='m1@att.com',
            gender='Male',
            date_of_birth=date(1992, 1, 1),
        )

        self.member2 = Member.objects.create(
            gym=self.gym2,
            first_name='AttMember',
            last_name='Two',
            mobile_number='9666622222',
            email='m2@att.com',
            gender='Female',
            date_of_birth=date(1993, 2, 2),
        )

        # Trainers
        self.trainer1 = Trainer.objects.create(
            gym=self.gym1,
            name='Trainer One',
            phone='9666633331',
            email='t1@att.com',
            trainer_id='TR1001',
            is_active=True
        )

        self.trainer2 = Trainer.objects.create(
            gym=self.gym2,
            name='Trainer Two',
            phone='9666633332',
            email='t2@att.com',
            trainer_id='TR2001',
            is_active=True
        )

        # Leave in Gym 2
        self.leave2 = MemberLeave.objects.create(
            gym=self.gym2,
            member=self.member2,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=2),
            reason='Personal reasons',
            status='pending'
        )

    def test_scan_attendance_member_checkin(self):
        """Member of Gym 1 can check in via Gym 1 QR attendance scan page."""
        url = reverse('attendance:scan_attendance', kwargs={'gym_id': self.gym1.gym_id})
        response = self.client_public.post(url, {'reg_number': self.member1.mobile_number}, secure=True)
        # Should redirect back to scan page
        self.assertEqual(response.status_code, 302)
        # Check attendance record created
        attendance = MemberAttendance.objects.filter(member=self.member1, gym=self.gym1).last()
        self.assertIsNotNone(attendance)
        self.assertEqual(attendance.status, 'inside')

    def test_scan_attendance_cross_gym_blocked(self):
        """Member of Gym 2 scanning at Gym 1 is rejected and not checked in."""
        url = reverse('attendance:scan_attendance', kwargs={'gym_id': self.gym1.gym_id})
        response = self.client_public.post(url, {'reg_number': self.member2.mobile_number}, secure=True)
        # Should re-render scan page with error
        self.assertEqual(response.status_code, 200)
        # Verify no attendance record created
        self.assertFalse(MemberAttendance.objects.filter(member=self.member2, gym=self.gym1).exists())

    def test_trainer_attendance_cross_tenant_quick_checkin_blocked(self):
        """Gym 1 admin cannot quick check-in trainer belonging to Gym 2."""
        url = reverse('attendance:trainer_attendance')
        response = self.client_gymadmin1.post(url, {'quick_checkin_id': self.trainer2.trainer_id}, secure=True)
        self.assertEqual(response.status_code, 302)
        # Verify trainer 2 has no attendance in gym 1 or gym 2
        self.assertFalse(TrainerAttendance.objects.filter(trainer=self.trainer2).exists())

    def test_leave_tenant_isolation(self):
        """Gym 1 admin cannot approve or update leave of Gym 2 member."""
        url = reverse('attendance:update_leave_status', kwargs={'leave_type': 'member', 'leave_id': self.leave2.id, 'status': 'approved'})
        response = self.client_gymadmin1.get(url, secure=True)
        # Should redirect to leave_management with error because leave belongs to gym 2
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('attendance:leave_management'), response.url)
        self.leave2.refresh_from_db()
        self.assertEqual(self.leave2.status, 'pending')
