from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.superadmin.models import Gym

class Item(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    UNIT_CHOICES = [
        ('kg', 'Kilogram'),
        ('g', 'Gram'),
        ('l', 'Liter'),
        ('ml', 'Milliliter'),
        ('pcs', 'Pieces'),
        ('unit', 'Unit'),
    ]
    CATEGORY_CHOICES = [
    ('supplements', 'Supplements & Nutrition'),
    ('beverages', 'Beverages'),
    ('equipment', 'Gym Equipment (Assets)'),
    ('accessories', 'Gym Accessories'),
    ('cleaning', 'Cleaning & Hygiene'),
    ('medical', 'Medical & First Aid'),
    ('merchandise', 'Merchandise'),
    ('office', 'Office & Stationery'),
    ('maintenance', 'Maintenance & Repair'),
    ('electronics', 'Electronics'),
    ('other', 'Other'),
]


    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    sku = models.CharField(max_length=50, blank=True, null=True)
    current_stock = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    reorder_level = models.PositiveIntegerField(default=0)
    supplier = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='inventory_images/', blank=True, null=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='added_items')
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        unique_together = [['gym', 'name']]


    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.sku:
            # Auto-generate SKU: First 3 letters of name + timestamp
            timestamp = str(int(timezone.now().timestamp()))
            self.sku = f"{self.name[:3].upper()}-{timestamp}"
        super().save(*args, **kwargs)

    @property
    def status(self):
        if self.current_stock <= 0:
            return 'Out of Stock'
        elif self.current_stock <= self.reorder_level:
            return 'Low Stock'
        else:
            return 'In Stock'

class StockLog(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    TRANSACTION_TYPES = [
        ('stock_in', 'Stock In'),
        ('stock_out', 'Stock Out'),
    ]
    REASON_CHOICES = [
        ('sale', 'Sale'),
        ('purchase', 'Purchase'),
        ('internal_use', 'Internal Use'),
        ('damage', 'Damage'),
        ('expired', 'Expired'),
        ('return', 'Return'),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='stock_logs')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    quantity = models.PositiveIntegerField()
    date = models.DateTimeField(default=timezone.now)
    supplier = models.CharField(max_length=100, blank=True, null=True)
    invoice_number = models.CharField(max_length=50, blank=True, null=True)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, blank=True, null=True, default='sale')
    issued_to = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    def __str__(self):
        return f"{self.transaction_type} of {self.quantity} {self.item.name} on {self.date.strftime('%Y-%m-%d')}"

class Equipment(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('under_maintenance', 'Under Maintenance'),
        ('retired', 'Retired'),
    ]

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=100, default='General')
    brand = models.CharField(max_length=100, blank=True, null=True, default='N/A')
    model = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    supplier = models.CharField(max_length=100, blank=True, null=True)
    purchase_date = models.DateField(default=timezone.now)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    warranty_period = models.CharField(max_length=50, blank=True, null=True) # e.g., "2 years"
    installation_date = models.DateField(blank=True, null=True)
    location = models.CharField(max_length=100, blank=True, null=True)
    expected_life = models.CharField(max_length=50, blank=True, null=True) # e.g., "10 years"
    notes = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='equipment_images/', blank=True, null=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='new')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='added_equipment')
    is_deleted = models.BooleanField(default=False)
    


    def __str__(self):
        return self.name

    @property
    def warranty_end_date(self):
        if self.purchase_date and self.warranty_period:
            wp = self.warranty_period.lower().strip()
            if "year" in wp:
                try:
                    years = int(wp.split()[0])
                    return self.purchase_date + timezone.timedelta(days=365 * years)
                except (ValueError, IndexError):
                    return None
            elif "month" in wp:
                try:
                    months = int(wp.split()[0])
                    return self.purchase_date + timezone.timedelta(days=30 * months)
                except (ValueError, IndexError):
                    return None
        return None

class Maintenance(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, null=True)
    MAINTENANCE_TYPES = [
        ('service', 'Service'),
        ('repair', 'Repair'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
    ]

    equipment = models.ForeignKey(Equipment, on_delete=models.CASCADE, related_name='maintenance_logs')
    maintenance_type = models.CharField(max_length=10, choices=MAINTENANCE_TYPES, default='service')
    issue_description = models.TextField()
    service_date = models.DateField()
    technician_name = models.CharField(max_length=100, blank=True, null=True)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    next_service_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    downtime_days = models.PositiveIntegerField(default=0, help_text="Number of days the equipment was out of service.")
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.maintenance_type} for {self.equipment.name} on {self.service_date}"