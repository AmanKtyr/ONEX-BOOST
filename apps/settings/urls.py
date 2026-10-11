from django.urls import path
from . import views

app_name = 'settings' 

urlpatterns = [
    path('general/', views.generalsetting.as_view(), name='general_settings'),
    path('payment/', views.PaymentSettingView.as_view(), name='payment_setting'),
    path('profile/', views.GymProfileView.as_view(), name='gym_profile'),
    path('subscription/', views.my_subscription_view, name='my_subscription'),
    path('subscription/request-upgrade/', views.request_plan_upgrade, name='request_plan_upgrade'),
]