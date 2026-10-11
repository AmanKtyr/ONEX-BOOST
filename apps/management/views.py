from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import DietPlan, MembershipPlan, WorkoutPlan
from .forms import DietPlanForm, MembershipPlanForm, WorkoutPlanForm
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from apps.login.decorators import custom_permission_required
from django.views.decorators.cache import never_cache

@never_cache
@login_required(login_url='login')
@custom_permission_required('view_membershipplan')
def membership_plans(request):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        form = MembershipPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.gym = gym
            plan.save()
            messages.success(request, 'Membership plan created successfully.')
            return redirect('membership_plans')
    else:
        form = MembershipPlanForm()
    
    plans = MembershipPlan.objects.filter(gym=gym).order_by('-id')
    
    # Search functionality
    query = request.GET.get('q')
    if query:
        plans = plans.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query)
        ).distinct()

    # Pagination
    paginator = Paginator(plans, 10)  # Show 10 plans per page
    page_number = request.GET.get('page')
    plans = paginator.get_page(page_number)

    return render(request, 'management/MembershipPlans/membership_plans.html', {'form': form, 'plans': plans})


@never_cache
@login_required(login_url='login')
@custom_permission_required('change_membershipplan')
def edit_membership_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = MembershipPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        messages.error(request, 'Membership plan not found.')
        return redirect('membership_plans')
    if request.method == 'POST':
        form = MembershipPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Membership plan updated successfully.')
            return redirect('membership_plans')
    else:
        form = MembershipPlanForm(instance=plan)
    return render(request, 'management/MembershipPlans/edit_membership_plan.html', {'form': form})


@never_cache
@login_required(login_url='login')
@custom_permission_required('delete_membershipplan')
def delete_membership_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = MembershipPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        return JsonResponse({'status': 'error', 'message': 'Membership plan not found.'}, status=404)
    if request.method == 'POST':
        try:
            plan.delete()
            return JsonResponse({'status': 'success', 'message': 'Membership plan deleted successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@never_cache
@login_required(login_url='login')
@custom_permission_required('view_dietplan')
def diet_plans(request):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        form = DietPlanForm(request.POST, request.FILES)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.gym = gym
            plan.save()
            messages.success(request, 'Diet plan created successfully.')
            return redirect('diet_plans')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = DietPlanForm()
    
    plans = DietPlan.objects.filter(gym=gym)
    
    # Search functionality
    query = request.GET.get('q')
    if query:
        plans = plans.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        ).distinct()

    # Pagination
    paginator = Paginator(plans, 10)  # Show 10 plans per page
    page_number = request.GET.get('page')
    plans = paginator.get_page(page_number)

    return render(request, 'management/DietPlans/diet_plans.html', {'form': form, 'plans': plans})


@never_cache
def public_diet_plan(request, pk):
    plan = DietPlan.objects.filter(pk=pk).first()
    if not plan:
        return render(request, 'management/DietPlans/public_diet_plan.html', {'plan': None, 'error': 'This diet plan does not exist or has been removed.'})
    request.gym = plan.gym
    return render(request, 'management/DietPlans/public_diet_plan.html', {'plan': plan})


        
@never_cache
@login_required(login_url='login')
@custom_permission_required('change_dietplan')
def edit_diet_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = DietPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        messages.error(request, 'Diet plan not found.')
        return redirect('diet_plans')
    if request.method == 'POST':
        form = DietPlanForm(request.POST, request.FILES, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Diet plan updated successfully.')
            return redirect('diet_plans')
    else:
        form = DietPlanForm(instance=plan)
    return render(request, 'management/DietPlans/edit_diet_plan.html', {'form': form})



@never_cache    
@login_required(login_url='login')
@custom_permission_required('delete_dietplan')
def delete_diet_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = DietPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        return JsonResponse({'status': 'error', 'message': 'Diet plan not found.'}, status=404)
    if request.method == 'POST':
        try:
            plan.delete()
            return JsonResponse({'status': 'success', 'message': 'Diet plan deleted successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})

@never_cache
@login_required(login_url='login')
@custom_permission_required('view_workoutplan')
def workout_plans(request):
    gym = getattr(request, 'gym', None)
    if request.method == 'POST':
        form = WorkoutPlanForm(request.POST, request.FILES)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.gym = gym
            plan.save()
            messages.success(request, 'Workout plan created successfully.')
            return redirect('workout_plans')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = WorkoutPlanForm()
    
    plans = WorkoutPlan.objects.filter(gym=gym)
    
    # Search functionality
    query = request.GET.get('q')
    if query:
        plans = plans.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        ).distinct()

    # Pagination
    paginator = Paginator(plans, 10)  # Show 10 plans per page
    page_number = request.GET.get('page')
    plans = paginator.get_page(page_number)

    return render(request, 'management/WorkoutPlans/workout_plans.html', {'form': form, 'plans': plans})


@never_cache
def public_workout_plan(request, pk):
    plan = WorkoutPlan.objects.filter(pk=pk).first()
    if not plan:
        return render(request, 'management/WorkoutPlans/public_workout_plan.html', {'plan': None, 'error': 'This workout plan does not exist or has been removed.'})
    # Set request.gym so that the template can use it for branding
    request.gym = plan.gym
    return render(request, 'management/WorkoutPlans/public_workout_plan.html', {'plan': plan})

@never_cache
@login_required(login_url='login')
@custom_permission_required('change_workoutplan')
def edit_workout_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = WorkoutPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        messages.error(request, 'Workout plan not found.')
        return redirect('workout_plans')
    if request.method == 'POST':
        form = WorkoutPlanForm(request.POST, request.FILES, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, 'Workout plan updated successfully.')
            return redirect('workout_plans')
    else:
        form = WorkoutPlanForm(instance=plan)
    return render(request, 'management/WorkoutPlans/edit_workout_plan.html', {'form': form})

@never_cache
@login_required(login_url='login')
@custom_permission_required('delete_workoutplan')
def delete_workout_plan(request, pk):
    gym = getattr(request, 'gym', None)
    plan = WorkoutPlan.objects.filter(pk=pk, gym=gym).first()
    if not plan:
        return JsonResponse({'status': 'error', 'message': 'Workout plan not found.'}, status=404)
    if request.method == 'POST':
        try:
            plan.delete()
            return JsonResponse({'status': 'success', 'message': 'Workout plan deleted successfully.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})