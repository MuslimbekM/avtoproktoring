from django.urls import path
from . import views
from .views import check_face

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('signin/', views.signin_view, name='signin'),
    path('student/<str:student_id>/', views.get_student, name='get_student'),
    path('home/', views.home_view, name='home'),
    path("exam/", views.exam_submission, name="exam_submission"),
    path("natija/", views.exam_results, name="exam_results"),
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
