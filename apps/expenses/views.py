from django.shortcuts import render, redirect, get_object_or_404
from .models import Expense
from .forms import ExpenseForm
from django.db.models import Q
from django.core.paginator import Paginator
from django.conf import settings
from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

# LIST EXPENSES (not deleted)
@login_required
@custom_permission_required('view_expense')
def expenses(request):
    gym = getattr(request, 'gym', None)
    query = request.GET.get('q')
    category = request.GET.get('category')
    payment_mode = request.GET.get('payment_mode')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    expenses_list = Expense.objects.filter(is_deleted=False, gym=gym).order_by('-date')

    # SEARCH
    if query:
        expenses_list = expenses_list.filter(
            Q(category__icontains=query) |
            Q(description__icontains=query) |
            Q(vendor_name__icontains=query)
        )

    # FILTERS
    if category:
        expenses_list = expenses_list.filter(category=category)

    if payment_mode:
        expenses_list = expenses_list.filter(payment_mode=payment_mode)

    if date_from:
        expenses_list = expenses_list.filter(date__gte=date_from)

    if date_to:
        expenses_list = expenses_list.filter(date__lte=date_to)

    # PAGINATION
    paginator = Paginator(expenses_list, settings.ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'expenses/expenses.html', {
        'expenses': page_obj,
        'page_obj': page_obj,
        'categories': Expense.EXPENSE_CATEGORIES,
        'payment_modes': Expense.PAYMENT_MODES,
    })

# ADD EXPENSE
@login_required
@custom_permission_required('add_expense')
def expense_add(request):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.added_by = request.user  # auto assign staff
            expense.gym = gym
            expense.save()
            messages.success(request, 'Expense added successfully.')
            return redirect('expenses')
    else:
        form = ExpenseForm()

    return render(request, 'expenses/expense_form.html', {'form': form})

# EDIT EXPENSE
@login_required
@custom_permission_required('change_expense')
def expense_edit(request, pk):
    gym = getattr(request, 'gym', None)
    expense = Expense.objects.filter(pk=pk, is_deleted=False, gym=gym).first()
    if not expense:
        messages.error(request, 'Expense not found.')
        return redirect('expenses')

    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully.')
            return redirect('expenses')
    else:
        form = ExpenseForm(instance=expense)

    return render(request, 'expenses/expense_form.html', {'form': form})

# SOFT DELETE (Send to Trash)
@require_POST
@login_required
@custom_permission_required('delete_expense')
def expense_delete(request, pk):
    gym = getattr(request, 'gym', None)
    try:
        expense = Expense.objects.filter(pk=pk, gym=gym).first()
        if not expense:
            return JsonResponse({'status': 'error', 'message': 'Expense not found.'}, status=404)
        expense.is_deleted = True
        expense.save()
        messages.success(request, 'Expense moved to trash successfully.')
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# TRASH PAGE
@never_cache
@login_required
@custom_permission_required('view_expense')
def expense_trash(request):
    gym = getattr(request, 'gym', None)
    trash_list = Expense.objects.filter(is_deleted=True, gym=gym).order_by('-date')

    paginator = Paginator(trash_list, settings.ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'expenses/expense_trash.html', {
        'expenses': page_obj,
        'page_obj': page_obj,
    })

# RESTORE FROM TRASH
@login_required
@custom_permission_required('change_expense')
def expense_restore(request, pk):
    gym = getattr(request, 'gym', None)
    expense = Expense.objects.filter(pk=pk, gym=gym).first()
    if not expense:
        messages.error(request, 'Expense not found.')
        return redirect('expense_trash')
    expense.is_deleted = False
    expense.save()
    messages.success(request, 'Expense restored successfully.')
    return redirect('expense_trash')

# PERMANENT DELETE
@login_required
@custom_permission_required('delete_expense')
def expense_delete_permanent(request, pk):
    gym = getattr(request, 'gym', None)
    expense = Expense.objects.filter(pk=pk, gym=gym).first()
    if not expense:
        messages.error(request, 'Expense not found.')
        return redirect('expense_trash')
    expense.delete()
    messages.success(request, 'Expense permanently deleted.')
    return redirect('expense_trash')