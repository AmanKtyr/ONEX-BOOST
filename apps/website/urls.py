from django.urls import path
from . import views



from django.views.generic.base import RedirectView

urlpatterns = [
    path('', views.website_index, name='index'),
    path('terms_of_service/', views.terms_of_service, name='terms_of_service'),
    path('privacy_policy/', views.privacy_policy, name='privacy_policy'),
    path('refund_policy/', views.refund_policy, name='refund_policy'),
    path('blogs/', views.blogs, name='blogs'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    path('blogs/<int:blog_id>/', RedirectView.as_view(url='/blogs/gym-management-software-in-lucknow/', permanent=True), name='blog_detail'),
    path('blogs/gym-management-software-in-lucknow/', views.gym_software_lucknow, name='gym_software_lucknow'),
    path('blogs/how-to-start-a-gym-in-india/', RedirectView.as_view(url='/blogs/gym-management-software-in-lucknow/', permanent=True), name='how_to_start_gym'),
    path('gym-management-software-in-lucknow/', RedirectView.as_view(url='/blogs/gym-management-software-in-lucknow/', permanent=True), name='legacy_gym_software_lucknow'),
    path('how-to-start-a-gym-in-india/', RedirectView.as_view(url='/blogs/gym-management-software-in-lucknow/', permanent=True), name='legacy_how_to_start_gym'),
    path('bmi-calculator/', views.bmi_calculator, name='bmi_calculator'),
    path('about/', views.about, name='about'),
    path('features/', views.features, name='features'),
    path('contact/', views.contact, name='contact'),
    path('pricing/', views.pricing, name='pricing'),
    path('modules/', views.modules, name='modules'),
    path('menu/', views.menu, name='menu'),
    path('contact-submission/', views.contact_submission, name='contact_submission'),
]