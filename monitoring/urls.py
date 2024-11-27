from django.urls import path
from . import views

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


]
