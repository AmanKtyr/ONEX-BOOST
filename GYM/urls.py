"""
URL configuration for GYM project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from apps.dashboard import views
from django.conf import settings
from django.conf.urls.static import static
from .views import help_view, debug, sitemap_view, robots_view

handler404 = 'GYM.views.handler404'


urlpatterns = [
    path('', include('apps.website.urls')),
    path('', include('apps.login.urls')),
    path('admin/', admin.site.urls),
    path('superadmin/', include(('apps.superadmin.urls', 'superadmin'))),
    path('dashboard/', include('apps.dashboard.urls')),
    path('dashboard', views.dashboard, name="dashboard"),
    path('attendance/', include('apps.attendance.urls')),
    path('members/', include('apps.members.urls')),
    path('trainers/', include('apps.trainers.urls')),
    path('enquiry/', include('apps.enquiry.urls')),
    path('billing/', include('apps.billing.urls')),
    path('management/', include('apps.management.urls')),
    path('expenses/', include('apps.expenses.urls')),
    path('settings/', include(('apps.settings.urls', 'settings'), namespace='settings')),
    path('business_report/', include('apps.business_report.urls')),
    path('events/', include('apps.events.urls')),
    path('inventory/', include('apps.inventory.urls')),
    path('whatsapp/', include('apps.whatsapp.urls')),
    path('notifications/', include(('apps.superadmin.notification_urls', 'notifications'), namespace='notifications')),
    path('portal/member/', include(('apps.member_portal.urls', 'member_portal'), namespace='member_portal')),
    path('portal/trainer/', include(('apps.trainer_portal.urls', 'trainer_portal'), namespace='trainer_portal')),
    path('member-portal/', include(('apps.member_portal.urls', 'member_portal_alias'))),
    path('trainer-portal/', include(('apps.trainer_portal.urls', 'trainer_portal_alias'))),
    path('help/', help_view, name='help'),
    path('debug/', debug, name='debug'),
]

# ── Dev-only preview URLs (DEBUG=True only) ──────────────────────────────────
if settings.DEBUG:
    urlpatterns += [
        path('preview/404/', lambda request: __import__('django.shortcuts', fromlist=['render']).render(request, '404.html', status=200), name='preview_404'),
    ]
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)