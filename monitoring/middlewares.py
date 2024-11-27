from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User

@login_required
def superadmin_required(get_response):
    def middleware(request):
        # Foydalanuvchi login qilganligini va superuser ekanligini tekshirish
        if request.user.is_authenticated and request.user.is_superuser:
            return get_response(request)
        else:
            # Superuser emas bo'lsa, login sahifasiga qaytariladi
            return redirect('login')

    return middleware
