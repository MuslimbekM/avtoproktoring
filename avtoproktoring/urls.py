"""
URL configuration for avtoproktoring project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
from django.urls import path

from monitoring import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('signup/', views.signup_view, name='signup'),
    path('signin/', views.signin_view, name='signin'),
    path('student/<str:student_id>/', views.get_student, name='get_student'),
    path('home/', views.home_view, name='home'),
    path("natija/", views.exam_results, name="exam_results"),
    path("exam/", views.exam_submission, name="exam_submission"),
    path('login/', views.admin_login, name='login'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('redirect/', views.redirect_based_on_role, name='redirect'),
]
