from django.urls import path
from . import views



urlpatterns = [
    path('', views.website_index, name='index'),
    path('terms_of_service/', views.terms_of_service, name='terms_of_service'),
    path('privacy_policy/', views.privacy_policy, name='privacy_policy'),
    path('refund_policy/', views.refund_policy, name='refund_policy'),
    path('blogs/', views.blogs, name='blogs'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    path('blogs/<int:blog_id>/', views.blog_detail, name='blog_detail'),
    path('gym-management-software-in-lucknow/', views.gym_software_lucknow, name='gym_software_lucknow'),
    path('how-to-start-a-gym-in-india/', views.how_to_start_gym, name='how_to_start_gym'),
    path('bmi-calculator/', views.bmi_calculator, name='bmi_calculator'),
    path('about/', views.about, name='about'),
    path('features/', views.features, name='features'),
    path('contact/', views.contact, name='contact'),
    path('pricing/', views.pricing, name='pricing'),
    path('contact-submission/', views.contact_submission, name='contact_submission'),
]