from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from apps.superadmin.models import Gym, GymAdmin
from apps.inventory.models import Item, StockLog, Equipment, Maintenance


@override_settings(SECURE_SSL_REDIRECT=False)
class InventoryModuleTests(TestCase):
    def setUp(self):
        self.client1 = Client()
        self.client2 = Client()

        # Create two gyms for multi-tenant testing
        self.gym1 = Gym.objects.create(
            name='Alpha Fitness',
            phone='9876543210',
            email='alpha@gym.com',
            gym_id_prefix='ALPHA'
        )
        self.gym2 = Gym.objects.create(
            name='Beta Fitness',
            phone='9876543211',
            email='beta@gym.com',
            gym_id_prefix='BETA'
        )

        # Users and GymAdmins
        self.user1 = User.objects.create_user(username='admin_alpha', password='password123')
        self.gym_admin1 = GymAdmin.objects.create(user=self.user1, gym=self.gym1)

        self.user2 = User.objects.create_user(username='admin_beta', password='password123')
        self.gym_admin2 = GymAdmin.objects.create(user=self.user2, gym=self.gym2)

        # Log in client1
        self.client1.login(username='admin_alpha', password='password123')
        session1 = self.client1.session
        session1['gym_id'] = self.gym1.id
        session1.save()

        # Log in client2
        self.client2.login(username='admin_beta', password='password123')
        session2 = self.client2.session
        session2['gym_id'] = self.gym2.id
        session2.save()

        # Create sample items for gym1
        self.item1 = Item.objects.create(
            gym=self.gym1,
            name='Whey Protein 1kg',
            category='supplements',
            sku='WHEY-001',
            unit='pcs',
            current_stock=25,
            reorder_level=5,
            supplier='Optimum Nutrition',
            purchase_price=Decimal('2000.00'),
            selling_price=Decimal('2800.00'),
            added_by=self.user1
        )

        self.item2 = Item.objects.create(
            gym=self.gym1,
            name='BCAA Energy Drink',
            category='beverages',
            sku='BCAA-001',
            unit='pcs',
            current_stock=2,  # Low stock (<= 5)
            reorder_level=5,
            supplier='Fast&Up',
            purchase_price=Decimal('100.00'),
            selling_price=Decimal('150.00'),
            added_by=self.user1
        )

        # Create sample equipment for gym1
        self.equip1 = Equipment.objects.create(
            gym=self.gym1,
            name='Commercial Treadmill',
            category='equipment',
            brand='Life Fitness',
            model='LF-95T',
            serial_number='SN-TR-9901',
            supplier='Fitness Solutions',
            purchase_date=date.today() - timedelta(days=100),
            purchase_cost=Decimal('150000.00'),
            warranty_period='2 years',
            location='Cardio Section',
            condition='good',
            status='active',
            added_by=self.user1
        )

    def test_inventory_dashboard_kpis_and_render(self):
        """Test dashboard renders successfully with correct KPIs and excludes deleted records."""
        url = reverse('inventory:dashboard')
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inventory Dashboard')
        # Total products = 2 (item1 and item2)
        self.assertEqual(response.context['total_products'], 2)
        # Total equipment = 1
        self.assertEqual(response.context['total_equipment'], 1)
        # Low stock items = 1 (item2 has 2 <= reorder_level 5)
        self.assertEqual(response.context['low_stock_items'], 1)

    def test_all_items_page_and_filtering(self):
        """Test item listing, search, status filtering, and pagination context."""
        url = reverse('inventory:all_items')
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Whey Protein 1kg')
        self.assertContains(response, 'BCAA Energy Drink')
        self.assertTrue(hasattr(response.context['items'], 'paginator'))

        # Search filter
        search_res = self.client1.get(url, {'q': 'Whey'})
        self.assertContains(search_res, 'Whey Protein 1kg')
        self.assertNotContains(search_res, 'BCAA Energy Drink')

        # Status filter for low_stock
        low_res = self.client1.get(url, {'status': 'low_stock'})
        self.assertContains(low_res, 'BCAA Energy Drink')
        self.assertNotContains(low_res, 'Whey Protein 1kg')

    def test_add_item_with_initial_stock_logs_stock_in(self):
        """Creating an item with initial stock must record a stock_in transaction log."""
        url = reverse('inventory:add_item')
        post_data = {
            'name': 'Creatine Monohydrate',
            'category': 'supplements',
            'sku': 'CREA-001',
            'unit': 'pcs',
            'current_stock': 15,
            'reorder_level': 3,
            'supplier': 'MuscleBlaze',
            'purchase_price': '600.00',
            'selling_price': '900.00',
            'expiry_date': '',
            'description': 'Pure micronized creatine'
        }
        response = self.client1.post(url, post_data)
        self.assertEqual(response.status_code, 302)

        created_item = Item.objects.get(gym=self.gym1, name='Creatine Monohydrate')
        self.assertEqual(created_item.current_stock, 15)

        # Verify initial StockLog was generated
        log = StockLog.objects.filter(item=created_item, transaction_type='stock_in').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.quantity, 15)
        self.assertEqual(log.purchase_price, Decimal('600.00'))

    def test_duplicate_item_name_validation(self):
        """Prevent duplicate item names within the same gym with a user-friendly form error."""
        url = reverse('inventory:add_item')
        post_data = {
            'name': 'Whey Protein 1kg',  # Already exists in gym1
            'category': 'supplements',
            'sku': 'NEW-SKU-001',
            'unit': 'pcs',
            'current_stock': 10,
            'reorder_level': 2,
            'supplier': 'Supplier X',
            'purchase_price': '500.00',
            'selling_price': '800.00',
        }
        response = self.client1.post(url, post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'name', "An item with the name 'Whey Protein 1kg' already exists in your inventory.")

    def test_delete_item_soft_deletes_and_excludes_from_views(self):
        """Soft-deleting an item marks is_deleted=True and excludes it from dashboard & lists."""
        url = reverse('inventory:delete_item', args=[self.item1.id])
        response = self.client1.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')

        self.item1.refresh_from_db()
        self.assertTrue(self.item1.is_deleted)

        # Excluded from all_items
        list_res = self.client1.get(reverse('inventory:all_items'))
        self.assertNotIn(self.item1, list_res.context['items'])
        self.assertEqual(len(list_res.context['items']), 1)

        # Excluded from dashboard KPI count
        dash_res = self.client1.get(reverse('inventory:dashboard'))
        self.assertEqual(dash_res.context['total_products'], 1)

    def test_stock_out_operation_and_validation(self):
        """Stocking out reduces stock, creates StockLog, and rejects insufficient stock."""
        url = reverse('inventory:stock_out')
        # 1. Attempt stocking out more than available (item1 stock is 25, requesting 30)
        invalid_post = {
            'item': self.item1.id,
            'quantity': 30,
            'discount': '0.00',
            'reason': 'sale',
            'issued_to': 'John Member',
            'phone_number': '9876543210',
            'remarks': 'Test sale'
        }
        res_invalid = self.client1.post(url, invalid_post)
        self.assertEqual(res_invalid.status_code, 200)
        self.assertFormError(res_invalid.context['form'], 'quantity', 'Not enough stock. Only 25 pcs available.')

        # 2. Valid stock out of 5 units with Rs 100 discount
        valid_post = {
            'item': self.item1.id,
            'quantity': 5,
            'discount': '100.00',
            'reason': 'sale',
            'issued_to': 'John Member',
            'phone_number': '9876543210',
            'remarks': 'Valid sale'
        }
        res_valid = self.client1.post(url, valid_post)
        self.assertEqual(res_valid.status_code, 302)

        self.item1.refresh_from_db()
        self.assertEqual(self.item1.current_stock, 20)  # 25 - 5

        # Check stock log entry and total calculation (5 * 2800 - 100 = 13900)
        log = StockLog.objects.filter(item=self.item1, transaction_type='stock_out').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.quantity, 5)
        self.assertEqual(log.total_amount, Decimal('13900.00'))

    def test_stock_log_view_and_pagination(self):
        """Stock log view displays transaction history for a specific item."""
        # Create a log entry
        StockLog.objects.create(
            gym=self.gym1,
            item=self.item1,
            transaction_type='stock_out',
            quantity=2,
            selling_price=Decimal('2800.00'),
            total_amount=Decimal('5600.00'),
            added_by=self.user1
        )
        url = reverse('inventory:stock_log', args=[self.item1.id])
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Stock Log:')
        self.assertContains(response, 'Whey Protein 1kg')
        self.assertTrue(hasattr(response.context['logs'], 'paginator'))

    def test_all_equipment_view_and_delete(self):
        """Equipment list page renders equipment, model, location, and soft-delete works."""
        url = reverse('inventory:all_equipment')
        response = self.client1.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Commercial Treadmill')
        self.assertContains(response, 'LF-95T')  # Model field
        self.assertContains(response, 'Cardio Section')  # Location field
        self.assertTrue(hasattr(response.context['equipments'], 'paginator'))

        # Soft delete equipment
        del_url = reverse('inventory:delete_equipment', args=[self.equip1.id])
        del_res = self.client1.post(del_url)
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json()['status'], 'success')

        self.equip1.refresh_from_db()
        self.assertTrue(self.equip1.is_deleted)

        # Excluded from list
        list_after = self.client1.get(url)
        self.assertNotIn(self.equip1, list_after.context['equipments'])
        self.assertEqual(len(list_after.context['equipments']), 0)

    def test_maintenance_log_creation_and_listing(self):
        """Test creating an equipment maintenance log and viewing it."""
        url = reverse('inventory:maintenance_log')
        post_data = {
            'equipment': self.equip1.id,
            'maintenance_type': 'service',
            'issue_description': 'Belt alignment and lubrication',
            'service_date': str(date.today()),
            'technician_name': 'Robert Tech',
            'cost': '1500.00',
            'next_service_date': str(date.today() + timedelta(days=90)),
            'status': 'completed',
            'downtime_days': 1
        }
        res_post = self.client1.post(url, post_data)
        self.assertEqual(res_post.status_code, 302)

        m_log = Maintenance.objects.filter(equipment=self.equip1).first()
        self.assertIsNotNone(m_log)
        self.assertEqual(m_log.technician_name, 'Robert Tech')
        self.assertEqual(m_log.cost, Decimal('1500.00'))

        res_get = self.client1.get(url)
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Belt alignment and lubrication')
        self.assertTrue(hasattr(res_get.context['logs'], 'paginator'))

    def test_tenant_isolation(self):
        """Gym 2 cannot see Gym 1's items or equipment."""
        # Gym 2 tries to view all items
        res = self.client2.get(reverse('inventory:all_items'))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, 'Whey Protein 1kg')

        # Gym 2 tries to delete Gym 1's item
        del_res = self.client2.post(reverse('inventory:delete_item', args=[self.item1.id]))
        self.assertEqual(del_res.status_code, 404)

        # Gym 2 tries to delete Gym 1's equipment
        del_eq = self.client2.post(reverse('inventory:delete_equipment', args=[self.equip1.id]))
        self.assertEqual(del_eq.status_code, 404)
