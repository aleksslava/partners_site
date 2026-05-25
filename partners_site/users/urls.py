from django.urls import path
from django.contrib.auth.views import LogoutView
from .views import UserLoginView
from . import views

app_name = "users"

urlpatterns = [
    path("telegram/", views.embedded_webapp_entry, {"platform": "telegram"}, name="telegram_webapp"),
    path("max/", views.embedded_webapp_entry, {"platform": "max"}, name="max_webapp"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("cabinet/", views.user_cabinet_view, name="user_cabinet"),
    path("customer/changed", views.customer_changed, name="customer_changed"),
]
