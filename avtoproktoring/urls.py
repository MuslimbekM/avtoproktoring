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
from monitoring.views import check_face

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
    path('check-face/', check_face, name='check_face'),
    path('add_student/', views.add_student, name='add_student'),
    path('delete_student/<str:student_id>/', views.delete_student, name='delete_student'),
    path('add_teacher/', views.add_teacher, name='add_teacher'),
    path('delete_teacher/<str:username>/', views.delete_teacher, name='delete_teacher'),
    path('create_questions/', views.create_questions, name='create_questions'),
    path("create_subject/", views.create_subject, name="create_subject"),
    path("create_exam/", views.create_exam, name="create_exam"),
    path("student_exams/", views.student_exams, name="student_exams"),
    path("exam_results/", views.exam_results, name="exam_results"),

]
