from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from apps.superadmin.models import Gym, GymAdmin
from apps.login.models import SubAdmin, SubAdminPermission

class SubAdminSecurityAndPermissionTests(TestCase):
    def setUp(self):
        self.client_subadmin = Client()
        self.client_gymadmin1 = Client()
        self.client_gymadmin2 = Client()

        # Two gyms
        self.gym1 = Gym.objects.create(
            name='Login Test Gym 1',
            phone='9333333331',
            email='gym1@login.com',
            gym_id_prefix='LG1'
        )
        self.gym2 = Gym.objects.create(
            name='Login Test Gym 2',
            phone='9333333332',
            email='gym2@login.com',
            gym_id_prefix='LG2'
        )

        # Gym Admins
        self.user_ga1 = User.objects.create_user(username='ga1', password='password123')
        self.ga1 = GymAdmin.objects.create(user=self.user_ga1, gym=self.gym1)

        self.user_ga2 = User.objects.create_user(username='ga2', password='password123')
        self.ga2 = GymAdmin.objects.create(user=self.user_ga2, gym=self.gym2)

        # Subadmin in Gym 1 with NO permissions initially
        self.user_sub = User.objects.create_user(username='subadmin1', password='password123', email='sub1@gym.com')
        self.subadmin1 = SubAdmin.objects.create(
            user=self.user_sub,
            gym=self.gym1,
            phone_number='9444444441'
        )

        # Subadmin in Gym 2
        self.user_sub2 = User.objects.create_user(username='subadmin2', password='password123', email='sub2@gym.com')
        self.subadmin2 = SubAdmin.objects.create(
            user=self.user_sub2,
            gym=self.gym2,
            phone_number='9444444442'
        )

        # Login clients
        self.client_subadmin.login(username='subadmin1', password='password123')
        s_sub = self.client_subadmin.session
        s_sub['gym_id'] = self.gym1.id
        s_sub['role'] = 'subadmin'
        s_sub.save()

        self.client_gymadmin1.login(username='ga1', password='password123')
        s_ga1 = self.client_gymadmin1.session
        s_ga1['gym_id'] = self.gym1.id
        s_ga1['role'] = 'gymadmin'
        s_ga1.save()

    def test_subadmin_without_permission_denied(self):
        """SubAdmin without view_member permission is redirected away with denial warning."""
        response = self.client_subadmin.get(reverse('member_list'), secure=True)
        # Should redirect to dashboard
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dashboard'), response.url)

    def test_subadmin_ajax_permission_denied_returns_403(self):
        """SubAdmin without permission making an AJAX request receives a JSON 403."""
        response = self.client_subadmin.get(
            reverse('member_list'),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            secure=True
        )
        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertTrue(data.get('permission_denied'))

    def test_subadmin_with_permission_granted(self):
        """SubAdmin with view_member permission can access member_list."""
        SubAdminPermission.objects.create(sub_admin=self.subadmin1, permission_name='view_member')
        response = self.client_subadmin.get(reverse('member_list'), secure=True)
        self.assertEqual(response.status_code, 200)

    def test_gymadmin_cannot_delete_subadmin_of_another_gym(self):
        """GymAdmin 1 cannot delete SubAdmin belonging to Gym 2."""
        url = reverse('delete_subadmin', kwargs={'sub_admin_id': self.subadmin2.id})
        response = self.client_gymadmin1.post(url, secure=True)
        # delete_subadmin returns 404 or error redirect when gym doesn't match
        self.assertIn(response.status_code, [302, 404])
        # Verify subadmin 2 was not deleted
        self.assertTrue(SubAdmin.objects.filter(id=self.subadmin2.id).exists())
