from django.shortcuts import render

# Create your views here.

from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy


class UserLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True