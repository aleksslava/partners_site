from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import UserLoginView
from . import views

app_name = "users"

urlpatterns = [
    path("login/", UserLoginView.as_view(), name="login"),
    path("login/diagnostics/", views.login_diagnostics_view, name="login_diagnostics"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("cabinet/", views.user_cabinet_view, name="user_cabinet"),
]
