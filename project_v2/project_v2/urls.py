from django.urls import path, include
from django.contrib import admin
from django.shortcuts import redirect


def home(request):
    return redirect("login")


urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('auth_system.urls')),  # Подключаем маршруты приложения auth_system
    path('accounts/', include('allauth.urls')),
    path('', home),  # Редирект на страницу входа
]
