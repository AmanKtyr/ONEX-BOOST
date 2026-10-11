from decimal import Decimal
from datetime import datetime, time, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Q, F, Sum, Count
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import IntegrityError

from apps.login.decorators import custom_permission_required
from .models import Item, StockLog, Equipment, Maintenance
from .forms import ItemForm, StockOutForm, EquipmentForm, MaintenanceForm


def _get_suppliers(gym):
    item_suppliers = Item.objects.filter(gym=gym, is_deleted=False).values_list('supplier', flat=True).distinct()
    equipment_suppliers = Equipment.objects.filter(gym=gym, is_deleted=False).values_list('supplier', flat=True).distinct()
    return sorted([s.strip() for s in set(list(item_suppliers) + list(equipment_suppliers)) if s and s.strip()])


@login_required
@custom_permission_required('view_item')
def inventory_dashboard(request):
    gym = getattr(request, 'gym', None)

    # Date filtering
    start_date_str = request.GET.get('from_date')
    end_date_str = request.GET.get('to_date')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
    else:
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30)

    # Ensure timezone aware range for DateTimeField queries to avoid naive datetime warning
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max))

    # KPI Calculations (Excluding deleted records)
    total_products = Item.objects.filter(gym=gym, is_deleted=False).exclude(category='equipment').count()
    total_equipment = Equipment.objects.filter(gym=gym, is_deleted=False).count()
    low_stock_items = Item.objects.filter(gym=gym, is_deleted=False, current_stock__gt=0, current_stock__lte=F('reorder_level')).count()
    
    stock_out_in_period = StockLog.objects.filter(
        gym=gym,
        transaction_type='stock_out',
        date__range=[start_dt, end_dt]
    ).count()

    # Chart Data
    monthly_stock_usage = StockLog.objects.filter(
        gym=gym,
        transaction_type='stock_out',
        date__range=[start_dt, end_dt]
    ).values('item__name').annotate(total_quantity=Sum('quantity')).order_by('-total_quantity')[:10]

    equipment_status = Equipment.objects.filter(gym=gym, is_deleted=False).values('status').annotate(count=Count('id'))

    # Recent Transactions
    recent_transactions = StockLog.objects.filter(gym=gym, date__range=[start_dt, end_dt]).order_by('-date')[:10]

    context = {
        'gym': gym,
        'total_products': total_products,
        'total_equipment': total_equipment,
        'low_stock_items': low_stock_items,
        'stock_out_in_period': stock_out_in_period,
        'monthly_stock_usage': monthly_stock_usage,
        'equipment_status': equipment_status,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'recent_transactions': recent_transactions,
    }
    return render(request, 'inventory/inventory_dashboard.html', context)


@login_required
@custom_permission_required('view_item')
def all_items(request):
    gym = getattr(request, 'gym', None)
    query = request.GET.get('q')
    category = request.GET.get('category')
    supplier = request.GET.get('supplier')
    stock_status = request.GET.get('status')

    items = Item.objects.filter(gym=gym, is_deleted=False)

    if query:
        query = query.strip()
        items = items.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query)
        )
    
    if category:
        items = items.filter(category__iexact=category)
    
    if supplier:
        items = items.filter(supplier__iexact=supplier)

    if stock_status:
        if stock_status == 'in_stock':
            items = items.filter(current_stock__gt=F('reorder_level'))
        elif stock_status == 'low_stock':
            items = items.filter(current_stock__lte=F('reorder_level'), current_stock__gt=0)
        elif stock_status == 'out_of_stock':
            items = items.filter(current_stock=0)

    # Order and paginate items
    items = items.order_by('-id')
    paginator = Paginator(items, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Filter categories and suppliers for active items only
    active_categories = Item.objects.filter(gym=gym, is_deleted=False).values_list('category', flat=True).distinct()
    active_suppliers = Item.objects.filter(gym=gym, is_deleted=False).values_list('supplier', flat=True).distinct()

    context = {
        'items': page_obj,
        'page_obj': page_obj,
        'categories': [c for c in active_categories if c],
        'suppliers': [s for s in active_suppliers if s],
        'gym': gym,
        'stock_status': stock_status,
    }
    return render(request, 'inventory/all_items.html', context)


@login_required
@custom_permission_required('change_item')
def add_edit_item(request, id=None):
    gym = getattr(request, 'gym', None)
    item = None
    is_new = True

    if id:
        item = Item.objects.filter(id=id, gym=gym, is_deleted=False).first()
        if not item:
            messages.error(request, 'Item not found.')
            return redirect('inventory:all_items')
        is_new = False
        form = ItemForm(request.POST or None, request.FILES or None, instance=item, gym=gym)
    else:
        form = ItemForm(request.POST or None, request.FILES or None, gym=gym)

    if request.method == 'POST':
        if form.is_valid():
            try:
                instance = form.save(commit=False)
                instance.added_by = request.user
                instance.gym = gym
                instance.save()

                # Record initial stock log if this is a newly created item with stock
                if is_new and instance.current_stock > 0:
                    StockLog.objects.create(
                        gym=gym,
                        item=instance,
                        transaction_type='stock_in',
                        quantity=instance.current_stock,
                        purchase_price=instance.purchase_price,
                        selling_price=instance.selling_price,
                        supplier=instance.supplier,
                        reason='purchase',
                        added_by=request.user,
                        remarks='Initial stock recorded on item creation'
                    )

                messages.success(request, f'Item "{instance.name}" saved successfully!')
                return redirect('inventory:all_items')
            except IntegrityError:
                form.add_error('name', f"An item with the name '{request.POST.get('name', '').strip()}' already exists in your inventory.")
        else:
            messages.error(request, 'Please correct the errors below.')

    suppliers = _get_suppliers(gym)
    categories = [c for c in Item.objects.filter(gym=gym, is_deleted=False).values_list('category', flat=True).distinct() if c]

    context = {
        'form': form,
        'suppliers': suppliers,
        'categories': categories,
        'gym': gym,
    }
    return render(request, 'inventory/add_inventory_item.html', context)


@require_POST
@login_required
@custom_permission_required('delete_item')
def delete_item(request, id):
    gym = getattr(request, 'gym', None)
    item = Item.objects.filter(id=id, gym=gym, is_deleted=False).first()
    if not item:
        return JsonResponse({'status': 'error', 'message': 'Item not found.'}, status=404)
    item.is_deleted = True
    item.save()
    messages.success(request, f'Item "{item.name}" deleted successfully.')
    return JsonResponse({'status': 'success', 'message': f'Item "{item.name}" deleted successfully.'})


@login_required
@custom_permission_required('change_item')
def stock_out_view(request, item_id=None):
    gym = getattr(request, 'gym', None)
    items = Item.objects.filter(gym=gym, is_deleted=False)

    if request.method == 'POST':
        form = StockOutForm(request.POST, gym=gym)
        if form.is_valid():
            stock_log = form.save(commit=False)
            stock_log.transaction_type = 'stock_out'
            stock_log.added_by = request.user
            stock_log.gym = gym
            
            item = stock_log.item
            if item.current_stock < stock_log.quantity:
                messages.error(request, f'Not enough stock for {item.name}. Currently available: {item.current_stock} {item.unit}.')
                return redirect('inventory:stock_out')

            item.current_stock -= stock_log.quantity
            item.save()
            
            selling_price = item.selling_price or Decimal('0.00')
            discount = stock_log.discount or Decimal('0.00')
            subtotal = selling_price * stock_log.quantity
            total_amount = max(Decimal('0.00'), subtotal - discount)

            stock_log.selling_price = selling_price
            stock_log.total_amount = total_amount
            stock_log.save()
            
            messages.success(request, f'Successfully stocked out {stock_log.quantity} {item.unit} of {item.name}.')
            return redirect('inventory:stock_log', item_id=item.id)
        else:
            messages.error(request, 'Please correct the errors in the form.')
    else:
        initial_data = {}
        if item_id:
            item = Item.objects.filter(id=item_id, gym=gym, is_deleted=False).first()
            if item:
                initial_data['item'] = item
        form = StockOutForm(initial=initial_data, gym=gym)
    
    context = {
        'form': form,
        'items': items,
        'suppliers': _get_suppliers(gym),
        'gym': gym,
    }
    return render(request, 'inventory/stock_out.html', context)


@login_required
def stock_log_view(request, item_id):
    gym = getattr(request, 'gym', None)
    item = Item.objects.filter(id=item_id, gym=gym).first()
    if not item:
        messages.error(request, 'Item not found.')
        return redirect('inventory:all_items')
    
    logs_qs = StockLog.objects.filter(item=item).order_by('-date')
    paginator = Paginator(logs_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'item': item,
        'logs': page_obj,
        'page_obj': page_obj,
        'gym': gym,
    }
    return render(request, 'inventory/stock_log.html', context)


@login_required
@custom_permission_required('view_equipment')
def all_equipment(request):
    gym = getattr(request, 'gym', None)
    query = request.GET.get('q')
    category = request.GET.get('category')
    status = request.GET.get('status')

    equipments = Equipment.objects.filter(gym=gym, is_deleted=False)

    if query:
        query = query.strip()
        equipments = equipments.filter(
            Q(name__icontains=query) |
            Q(serial_number__icontains=query) |
            Q(model__icontains=query)
        )
    
    if category:
        equipments = equipments.filter(category__iexact=category)

    if status:
        equipments = equipments.filter(status__iexact=status)

    equipments = equipments.order_by('-id')
    paginator = Paginator(equipments, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    active_categories = Equipment.objects.filter(gym=gym, is_deleted=False).values_list('category', flat=True).distinct()

    context = {
        'equipments': page_obj,
        'page_obj': page_obj,
        'categories': [c for c in active_categories if c],
        'gym': gym,
    }
    return render(request, 'inventory/all_equipment.html', context)


@login_required
@custom_permission_required('change_equipment')
def add_edit_equipment(request, id=None):
    gym = getattr(request, 'gym', None)
    equipment = None

    if id:
        equipment = Equipment.objects.filter(id=id, gym=gym, is_deleted=False).first()
        if not equipment:
            messages.error(request, 'Equipment not found.')
            return redirect('inventory:all_equipment')
        form = EquipmentForm(request.POST or None, request.FILES or None, instance=equipment)
    else:
        form = EquipmentForm(request.POST or None, request.FILES or None)

    if request.method == 'POST':
        if form.is_valid():
            instance = form.save(commit=False)
            instance.added_by = request.user
            instance.gym = gym
            instance.save()
            messages.success(request, f'Equipment "{instance.name}" saved successfully!')
            return redirect('inventory:all_equipment')
        else:
            messages.error(request, 'Please correct the errors below.')
    
    categories = [c for c in Item.objects.filter(gym=gym, is_deleted=False).values_list('category', flat=True).distinct() if c]

    context = {
        'form': form,
        'suppliers': _get_suppliers(gym),
        'categories': categories,
        'gym': gym,
    }
    return render(request, 'inventory/add_equipment.html', context)


@require_POST
@login_required
@custom_permission_required('delete_equipment')
def delete_equipment(request, id):
    gym = getattr(request, 'gym', None)
    equipment = Equipment.objects.filter(id=id, gym=gym, is_deleted=False).first()
    if not equipment:
        return JsonResponse({'status': 'error', 'message': 'Equipment not found.'}, status=404)
    equipment.is_deleted = True
    equipment.save()
    messages.success(request, f'Equipment "{equipment.name}" deleted successfully.')
    return JsonResponse({'status': 'success', 'message': f'Equipment "{equipment.name}" deleted successfully.'})


@login_required
def maintenance_log(request):
    gym = getattr(request, 'gym', None)
    form = MaintenanceForm(request.POST or None, gym=gym)
    if request.method == 'POST':
        if form.is_valid():
            maintenance = form.save(commit=False)
            maintenance.added_by = request.user
            maintenance.gym = gym
            maintenance.save()
            messages.success(request, 'Maintenance log added successfully!')
            return redirect('inventory:maintenance_log')
        else:
            messages.error(request, 'Please correct the errors in the maintenance form.')

    logs_qs = Maintenance.objects.filter(gym=gym).order_by('-service_date', '-id')
    paginator = Paginator(logs_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'logs': page_obj,
        'page_obj': page_obj,
        'gym': gym,
    }
    return render(request, 'inventory/maintenance_log.html', context)