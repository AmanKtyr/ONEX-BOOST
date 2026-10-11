from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal
from .models import Item, StockLog, Equipment, Maintenance

class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            'name', 'category', 'sku', 'unit', 'current_stock', 'reorder_level', 'supplier', 
            'purchase_price', 'selling_price', 'expiry_date', 'image', 'description'
        ]
        labels = {
            'current_stock': 'Stock Quantity',
            'reorder_level': 'Low Stock Alert Threshold',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Whey Protein, Yoga Mat', 'style': 'text-transform: capitalize;'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., WP-001 (auto-generated if empty)'}),
            'unit': forms.Select(attrs={'class': 'form-control'}),
            'current_stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 100', 'min': '0'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 5', 'min': '0'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Global Fitness', 'list': 'supplier-list', 'style': 'text-transform: capitalize;'}),
            'purchase_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
            'selling_price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'A brief description of the item'}),
        }

    def __init__(self, *args, **kwargs):
        self.gym = kwargs.pop('gym', None)
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            gym = self.gym or getattr(self.instance, 'gym', None)
            if gym:
                qs = Item.objects.filter(gym=gym, name__iexact=name, is_deleted=False)
                if self.instance and self.instance.pk:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.exists():
                    raise ValidationError(f"An item with the name '{name}' already exists in your inventory.")
            return name.title()
        return name

    def clean_supplier(self):
        supplier = self.cleaned_data.get('supplier')
        if supplier:
            return supplier.strip().title()
        return supplier

    def clean_current_stock(self):
        stock = self.cleaned_data.get('current_stock')
        if stock is not None and stock < 0:
            raise ValidationError("Stock quantity cannot be negative.")
        return stock

    def clean_reorder_level(self):
        level = self.cleaned_data.get('reorder_level')
        if level is not None and level < 0:
            raise ValidationError("Reorder level cannot be negative.")
        return level

    def clean_purchase_price(self):
        price = self.cleaned_data.get('purchase_price')
        if price is not None and price < Decimal('0.00'):
            raise ValidationError("Purchase price cannot be negative.")
        return price

    def clean_selling_price(self):
        price = self.cleaned_data.get('selling_price')
        if price is not None and price < Decimal('0.00'):
            raise ValidationError("Selling price cannot be negative.")
        return price


class StockOutForm(forms.ModelForm):
    class Meta:
        model = StockLog
        fields = [
            'item', 'quantity', 'discount', 'reason', 'issued_to', 
            'phone_number', 'remarks'
        ]
        widgets = {
            'item': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 1', 'min': '1'}),
            'reason': forms.Select(attrs={'class': 'form-control'}),
            'issued_to': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., "John Doe"', 'style': 'text-transform: capitalize;'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 9876543210', 'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57', 'maxlength': '15'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any additional notes...'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['item'].queryset = Item.objects.filter(gym=gym, is_deleted=False)
        self.fields['item'].required = True
        self.fields['quantity'].required = True

    def clean_issued_to(self):
        issued_to = self.cleaned_data.get('issued_to')
        if issued_to:
            return issued_to.strip().title()
        return issued_to

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            phone_number = phone_number.strip()
            if not phone_number.isdigit() or len(phone_number) != 10:
                raise ValidationError("Enter a valid 10-digit mobile number.")
        return phone_number

    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        item = self.cleaned_data.get('item')
        if quantity is not None and quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")
        if item and quantity and quantity > item.current_stock:
            raise ValidationError(f"Not enough stock. Only {item.current_stock} {item.unit} available.")
        return quantity

    def clean_discount(self):
        discount = self.cleaned_data.get('discount')
        if discount is not None and discount < Decimal('0.00'):
            raise ValidationError("Discount cannot be negative.")
        return discount


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = Equipment
        fields = [
            'name', 'category', 'brand', 'model', 'serial_number', 'supplier',
            'purchase_date', 'purchase_cost', 'warranty_period', 'installation_date',
            'location', 'expected_life', 'notes', 'image', 'condition', 'status'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Treadmill, Dumbbell Set'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'brand': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Life Fitness, Precor'}),
            'model': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., T5, 956i'}),
            'serial_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., SN-12345'}),
            'supplier': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Global Fitness', 'list': 'supplier-list'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
            'warranty_period': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2 years'}),
            'installation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Cardio Section, Weight Room'}),
            'expected_life': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 10 years'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Any additional notes...'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].widget.choices = Item.CATEGORY_CHOICES

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            return name.strip().title()
        return name

    def clean_purchase_cost(self):
        cost = self.cleaned_data.get('purchase_cost')
        if cost is not None and cost < Decimal('0.00'):
            raise ValidationError("Purchase cost cannot be negative.")
        return cost


class MaintenanceForm(forms.ModelForm):
    class Meta:
        model = Maintenance
        fields = [
            'equipment', 'maintenance_type', 'issue_description', 'service_date',
            'technician_name', 'cost', 'next_service_date', 'status', 'downtime_days'
        ]
        widgets = {
            'equipment': forms.Select(attrs={'class': 'form-control'}),
            'maintenance_type': forms.Select(attrs={'class': 'form-control'}),
            'issue_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe the issue...'}),
            'service_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'technician_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., John Doe'}),
            'cost': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': '0', 'step': '0.01'}),
            'next_service_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'downtime_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 2', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        gym = kwargs.pop('gym', None)
        super().__init__(*args, **kwargs)
        if gym:
            self.fields['equipment'].queryset = Equipment.objects.filter(gym=gym, is_deleted=False)

    def clean_cost(self):
        cost = self.cleaned_data.get('cost')
        if cost is not None and cost < Decimal('0.00'):
            raise ValidationError("Maintenance cost cannot be negative.")
        return cost

    def clean_downtime_days(self):
        days = self.cleaned_data.get('downtime_days')
        if days is not None and days < 0:
            raise ValidationError("Downtime days cannot be negative.")
        return days